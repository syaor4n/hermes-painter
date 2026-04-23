"""Unit tests for demo_memory_arc.make_sandbox / build_side_by_side / write_summary."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from demo_memory_arc import make_sandbox


def test_make_sandbox_creates_layout(tmp_path: Path):
    paths = make_sandbox(tmp_path / "mem_arc")

    # Required subdirs + file
    assert paths["skills_dir"].is_dir()
    assert paths["reflections_dir"].is_dir()
    assert paths["runs_dir"].is_dir()
    assert paths["logs_dir"].is_dir()
    assert paths["journal_path"].is_file()
    assert paths["journal_path"].read_text() == ""


def test_make_sandbox_copies_style_signature(tmp_path: Path):
    """If the real skills/style/signature.md exists, it's copied into the sandbox
    so the painter's voice stays constant. If it doesn't exist, make_sandbox
    silently succeeds (no crash)."""
    paths = make_sandbox(tmp_path / "mem_arc")

    sig_src = ROOT / "skills" / "style" / "signature.md"
    sig_dst = paths["skills_dir"] / "style" / "signature.md"

    if sig_src.exists():
        assert sig_dst.is_file()
        assert sig_dst.read_text() == sig_src.read_text()
    else:
        # If the real signature is missing, we still expect the style/ subdir
        # layout to be OK (or absent). No crash is the contract.
        assert True


def test_make_sandbox_is_idempotent(tmp_path: Path):
    """Calling make_sandbox twice on the same path succeeds both times."""
    root = tmp_path / "mem_arc"
    make_sandbox(root)
    # Second call should not raise (mkdir with exist_ok semantics).
    paths = make_sandbox(root)
    assert paths["skills_dir"].is_dir()


from demo_memory_arc import build_side_by_side


def _synth_png(path: Path, color: tuple[int, int, int], size: int = 512):
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    Image.fromarray(arr, mode="RGB").save(path)


def test_build_side_by_side_produces_panel(tmp_path: Path):
    target = tmp_path / "target.png"
    cold = tmp_path / "cold.png"
    primed = tmp_path / "primed.png"
    out = tmp_path / "side_by_side.png"

    _synth_png(target, (255, 0, 0))
    _synth_png(cold, (0, 255, 0))
    _synth_png(primed, (0, 0, 255))

    build_side_by_side(target, cold, primed, out, header="test header")

    assert out.is_file()
    img = Image.open(out).convert("RGB")
    # Three 512 panels + separators → at least 3 * 512 = 1536 wide
    assert img.width >= 1536
    # Sample pixels from each panel to confirm ordering target | cold | primed
    arr = np.asarray(img)
    # First panel center
    assert arr[arr.shape[0] // 2, 256].tolist() == [255, 0, 0]
    # Second panel center (target_w + gap + 256)
    mid2 = 512 + (img.width - 3 * 512) // 2 + 256
    assert arr[arr.shape[0] // 2, mid2].tolist() == [0, 255, 0]
    # Third panel center
    mid3 = 2 * (512 + 16) + 256
    assert arr[arr.shape[0] // 2, mid3].tolist() == [0, 0, 255]


from demo_memory_arc import write_summary


def test_write_summary_json_shape(tmp_path: Path):
    summary = {
        "ts": "2026-04-22T15:30:21Z",
        "target": "targets/masterworks/great_wave.jpg",
        "image_type": "high_contrast",
        "style_mode": "van_gogh",
        "seed": 42,
        "sandbox_path": str(tmp_path / "sbox"),
        "priming": {"k_requested": 5, "k_used": 3, "targets": ["a.jpg"], "note": None},
        "cold": {"ssim": 0.42, "n_strokes": 2000, "applied_skills": [],
                  "effective_params": {"contrast_boost": 0.25}, "elapsed_s": 48.0},
        "primed": {"ssim": 0.44, "n_strokes": 2000, "applied_skills": ["x"],
                    "effective_params": {"contrast_boost": 0.34}, "elapsed_s": 51.0},
        "delta": {"ssim": 0.02, "applied_skills_count": 1,
                   "effective_params": {"contrast_boost": 0.09}},
        "promoted": [],
    }
    out = tmp_path / "summary.json"
    write_summary(summary, out)
    assert out.is_file()
    loaded = json.loads(out.read_text())
    # Round-trip preserves keys
    assert loaded["target"] == summary["target"]
    assert loaded["cold"]["applied_skills"] == []
    assert loaded["delta"]["ssim"] == 0.02
