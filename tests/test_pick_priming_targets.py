"""Unit tests for scripts/demo_memory_arc.pick_priming_targets.

Uses synthetic PNGs generated on the fly so the test is fully
deterministic and doesn't depend on what's checked into targets/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from demo_memory_arc import pick_priming_targets


def _make_img(path: Path, *, brightness: int, contrast_noise: int,
              saturation_gap: int, warmth_red: int):
    """Create a 64x64 PNG with controllable mean/std/sat/warmth."""
    rng = np.random.default_rng(seed=brightness)
    base = np.full((64, 64, 3), brightness, dtype=np.int16)
    base[..., 0] += warmth_red
    base[..., 2] -= warmth_red
    noise = rng.integers(-contrast_noise, contrast_noise + 1, size=(64, 64, 1))
    base += noise
    base[..., 0] += saturation_gap
    arr = np.clip(base, 0, 255).astype(np.uint8)
    Image.fromarray(arr, mode="RGB").save(path)


def test_picks_same_image_type(tmp_path: Path):
    """Priming candidates must share the final target's classified image_type."""
    final = tmp_path / "final.jpg"
    _make_img(final, brightness=150, contrast_noise=70, saturation_gap=40, warmth_red=15)

    cand_dir = tmp_path / "candidates"
    cand_dir.mkdir()
    # Five same-type-ish
    for i in range(5):
        _make_img(cand_dir / f"same_{i}.jpg", brightness=150 + i * 2,
                  contrast_noise=70, saturation_gap=40, warmth_red=15 + i)
    # Three obviously-different (dark)
    for i in range(3):
        _make_img(cand_dir / f"dark_{i}.jpg", brightness=40,
                  contrast_noise=10, saturation_gap=5, warmth_red=0)

    picks = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[cand_dir], diversity_threshold=0.0,
    )
    # All picks are same-type candidates (not dark_*)
    assert len(picks) >= 1
    for p in picks:
        assert "same_" in p.name, f"unexpected cross-type pick: {p}"


def test_excludes_final_target(tmp_path: Path):
    """The final target is never returned as a priming pick even if it's in candidate_dirs."""
    final = tmp_path / "final.jpg"
    _make_img(final, brightness=150, contrast_noise=70, saturation_gap=40, warmth_red=15)
    # Also put a copy in the candidates dir (same content -> same features -> would be #1 pick if included)
    for i in range(4):
        _make_img(tmp_path / f"same_{i}.jpg", brightness=150 + i,
                  contrast_noise=70, saturation_gap=40, warmth_red=15)

    picks = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[tmp_path], diversity_threshold=0.0,
    )
    resolved_final = final.resolve()
    for p in picks:
        assert p.resolve() != resolved_final


def test_diversity_threshold_rejects_near_duplicates(tmp_path: Path):
    """Candidates that are too close to an already-picked one are skipped."""
    final = tmp_path / "final.jpg"
    _make_img(final, brightness=150, contrast_noise=70, saturation_gap=40, warmth_red=15)
    # Two distinct profiles, three clones each
    for i in range(3):
        _make_img(tmp_path / f"clone_a_{i}.jpg", brightness=151,
                  contrast_noise=70, saturation_gap=40, warmth_red=15)
    for i in range(3):
        _make_img(tmp_path / f"clone_b_{i}.jpg", brightness=155,
                  contrast_noise=72, saturation_gap=45, warmth_red=18)

    picks = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[tmp_path], diversity_threshold=0.3,
    )
    # With high diversity threshold, at most 2 unique-profile picks from these 6.
    assert len(picks) <= 2


def test_returns_fewer_when_sparse(tmp_path: Path):
    """If fewer than k same-type candidates exist, return what's available — no cross-type fill."""
    final = tmp_path / "final.jpg"
    _make_img(final, brightness=150, contrast_noise=70, saturation_gap=40, warmth_red=15)
    # Only 2 same-type
    for i in range(2):
        _make_img(tmp_path / f"same_{i}.jpg", brightness=152 + i,
                  contrast_noise=70, saturation_gap=40, warmth_red=15)
    # 5 very-dark
    for i in range(5):
        _make_img(tmp_path / f"dark_{i}.jpg", brightness=30 + i,
                  contrast_noise=5, saturation_gap=2, warmth_red=0)

    picks = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[tmp_path], diversity_threshold=0.0,
    )
    assert len(picks) <= 2, f"expected ≤2 same-type picks, got {len(picks)}"


def test_deterministic(tmp_path: Path):
    """Two invocations with the same inputs return the same picks in the same order."""
    final = tmp_path / "final.jpg"
    _make_img(final, brightness=150, contrast_noise=70, saturation_gap=40, warmth_red=15)
    for i in range(6):
        _make_img(tmp_path / f"c_{i}.jpg", brightness=150 + i * 3,
                  contrast_noise=70, saturation_gap=40, warmth_red=15 + i)

    picks_1 = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[tmp_path], diversity_threshold=0.0,
    )
    picks_2 = pick_priming_targets(
        final, style_mode="van_gogh", k=5,
        candidate_dirs=[tmp_path], diversity_threshold=0.0,
    )
    assert [p.name for p in picks_1] == [p.name for p in picks_2]
