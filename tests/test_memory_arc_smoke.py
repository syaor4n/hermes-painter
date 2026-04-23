"""End-to-end smoke test for demo_memory_arc.py.

Runs the real isolated stack on alt ports (28080/28765 — distinct from the
demo's defaults so it doesn't collide with a hand-run demo). Skipped when
Playwright+Chromium isn't launchable, or when pil-only rendering isn't
viable in this environment.

The test asserts the end-to-end invariants:
  - Both PNGs exist after the run
  - summary.json has cold.applied_skills == []
  - The user's real skills/ and journal.jsonl were not mutated
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int | None:
    """Return an ephemeral localhost port, or None if binding isn't allowed.

    Restricted test environments (some sandboxes, locked-down CI) refuse
    socket binds. Return None instead of raising so the caller can
    pytest.skip with a clear reason.
    """
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    except (PermissionError, OSError):
        return None


def _hash_dir(path: Path) -> str:
    """Stable hash of all files under path (names + content)."""
    if not path.exists():
        return "<missing>"
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pil_renderer_available() -> tuple[bool, str]:
    try:
        from PIL import Image  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, f"PIL not available: {e}"


def test_end_to_end_smoke(tmp_path: Path):
    """Run demo_memory_arc.py --clean-sandbox against a small target and check artifacts."""
    ok, reason = _pil_renderer_available()
    if not ok:
        pytest.skip(f"PIL unavailable — {reason}")

    # Pick a small masterwork so the run is fast.
    target = ROOT / "targets" / "masterworks" / "rothko_purple_white_red.jpg"
    if not target.exists():
        pytest.skip(f"target not in repo: {target}")

    out_dir = tmp_path / "arc_out"
    viewer_port = _free_port()
    tools_port = _free_port()
    if viewer_port is None or tools_port is None:
        pytest.skip("cannot bind ephemeral localhost port — restricted environment")

    # Snapshot user library + journal BEFORE.
    skills_hash_before = _hash_dir(ROOT / "skills")
    journal_hash_before = _hash_file(ROOT / "journal.jsonl")
    reflections_hash_before = _hash_dir(ROOT / "reflections")

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "demo_memory_arc.py"),
            "--target", str(target),
            "--out-dir", str(out_dir),
            "--viewer-port", str(viewer_port),
            "--tools-port", str(tools_port),
            "--clean-sandbox",
            "--seed", "3",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,  # 15 min hard ceiling — realistically ~5-7 min
    )

    # Accept exit 0 (full success) or 1 (soft-fail: fewer than 5 priming
    # candidates available for this target's image_type bucket). 2/3 are
    # real failures.
    if r.returncode not in (0, 1):
        pytest.fail(
            f"demo_memory_arc.py failed with exit {r.returncode}\n"
            f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
        )

    assert (out_dir / "run_cold.png").is_file(), "run_cold.png not produced"
    assert (out_dir / "run_primed.png").is_file(), "run_primed.png not produced"
    assert (out_dir / "side_by_side.png").is_file(), "side_by_side.png not produced"
    assert (out_dir / "summary.json").is_file(), "summary.json not produced"

    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["cold"]["applied_skills"] == [], (
        f"invariant broken: cold paint applied skills: {summary['cold']['applied_skills']}"
    )

    # User's real library MUST be untouched.
    assert _hash_dir(ROOT / "skills") == skills_hash_before, \
        "user's skills/ directory was mutated by the demo"
    assert _hash_file(ROOT / "journal.jsonl") == journal_hash_before, \
        "user's journal.jsonl was mutated by the demo"
    assert _hash_dir(ROOT / "reflections") == reflections_hash_before, \
        "user's reflections/ directory was mutated by the demo"
