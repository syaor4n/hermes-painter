"""The PAINTER_SKILLS_DIR / PAINTER_JOURNAL_PATH / PAINTER_REFLECTIONS_DIR
env-var overrides must be honored at import time, not cached across processes.

We use subprocess for each check because Python's import system caches
module-level constants inside the current process. A child process is the
only way to observe the read-at-import behavior the orchestrator relies on.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _run_py(code: str, env_extra: dict[str, str]) -> str:
    """Run `python -c code` with env_extra merged into the child env.

    Returns the child's stdout (stripped). Raises CalledProcessError with
    stderr visible if the child exits non-zero.
    """
    import os
    env = {**os.environ, **env_extra, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def test_skills_dir_override_is_honored(tmp_path: Path):
    """Setting PAINTER_SKILLS_DIR makes skills.SKILLS_DIR resolve there."""
    sandbox = tmp_path / "sandbox_skills"
    sandbox.mkdir()
    out = _run_py(
        "from painter.skills import SKILLS_DIR; print(SKILLS_DIR)",
        {"PAINTER_SKILLS_DIR": str(sandbox)},
    )
    assert out == str(sandbox)


def test_skills_dir_default_when_unset():
    """Without PAINTER_SKILLS_DIR, SKILLS_DIR is the repo's skills/ directory."""
    # Make sure any parent-shell override doesn't leak in.
    import os
    env = {k: v for k, v in os.environ.items() if k != "PAINTER_SKILLS_DIR"}
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run(
        [sys.executable, "-c", "from painter.skills import SKILLS_DIR; print(SKILLS_DIR)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = ROOT / "skills"
    assert r.stdout.strip() == str(expected)


def test_journal_path_override_is_honored(tmp_path: Path):
    """Setting PAINTER_JOURNAL_PATH makes journal.JOURNAL_PATH resolve there."""
    sandbox = tmp_path / "sandbox_journal.jsonl"
    out = _run_py(
        "from painter.journal import JOURNAL_PATH; print(JOURNAL_PATH)",
        {"PAINTER_JOURNAL_PATH": str(sandbox)},
    )
    assert out == str(sandbox)


def test_journal_path_default_when_unset():
    """Without PAINTER_JOURNAL_PATH, JOURNAL_PATH is the repo's journal.jsonl."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "PAINTER_JOURNAL_PATH"}
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run(
        [sys.executable, "-c",
         "from painter.journal import JOURNAL_PATH; print(JOURNAL_PATH)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = ROOT / "journal.jsonl"
    assert r.stdout.strip() == str(expected)


def test_reflections_dir_override_is_honored(tmp_path: Path):
    """Setting PAINTER_REFLECTIONS_DIR makes tools._common._REFLECTIONS_DIR resolve there."""
    sandbox = tmp_path / "sandbox_reflections"
    sandbox.mkdir()
    out = _run_py(
        "from painter.tools._common import _REFLECTIONS_DIR; print(_REFLECTIONS_DIR)",
        {"PAINTER_REFLECTIONS_DIR": str(sandbox)},
    )
    assert out == str(sandbox)


def test_reflections_dir_default_when_unset():
    """Without PAINTER_REFLECTIONS_DIR, _REFLECTIONS_DIR is the repo's reflections/ directory."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "PAINTER_REFLECTIONS_DIR"}
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run(
        [sys.executable, "-c",
         "from painter.tools._common import _REFLECTIONS_DIR; print(_REFLECTIONS_DIR)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = ROOT / "reflections"
    assert r.stdout.strip() == str(expected)


def test_style_dir_follows_skills_dir_override(tmp_path: Path):
    """Setting PAINTER_SKILLS_DIR also reroutes painter.style.STYLE_DIR."""
    sandbox = tmp_path / "sandbox_skills"
    sandbox.mkdir()
    out = _run_py(
        "from painter.style import STYLE_DIR, SIGNATURE_PATH; "
        "print(STYLE_DIR); print(SIGNATURE_PATH)",
        {"PAINTER_SKILLS_DIR": str(sandbox)},
    )
    lines = out.splitlines()
    assert lines[0] == str(sandbox / "style")
    assert lines[1] == str(sandbox / "style" / "signature.md")


def test_style_dir_default_when_unset():
    """Without PAINTER_SKILLS_DIR, STYLE_DIR is the repo's skills/style directory."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "PAINTER_SKILLS_DIR"}
    env["PYTHONPATH"] = str(ROOT / "src")
    r = subprocess.run(
        [sys.executable, "-c", "from painter.style import STYLE_DIR; print(STYLE_DIR)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = ROOT / "skills" / "style"
    assert r.stdout.strip() == str(expected)
