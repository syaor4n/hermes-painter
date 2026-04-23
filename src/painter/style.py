"""Painter's persistent style signature.

This is the file the agent writes about itself. It is NOT a parameter file —
it is a short essay in the first person describing what the painter
optimizes for, what it avoids, and how its style is evolving.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import skills as _skills

STYLE_DIR = _skills.SKILLS_DIR / "style"
SIGNATURE_PATH = STYLE_DIR / "signature.md"

DEFAULT_SIGNATURE = """# My painting style

## What I optimize for
- Recognizable forms over pixel fidelity
- Warm shadows, cool highlights
- Visible brushwork that reads as intentional, not noisy

## What I avoid
- Muddy palettes (I prefer 5–7 colors with clear value separation)
- Over-detailed backgrounds that compete with the focal point
- Smooth gradients where a gestural stroke would do

## My evolution
- This file is updated by me after every N runs.
"""


def read() -> str:
    """Return the current signature body; create a default one if missing."""
    if not SIGNATURE_PATH.exists():
        STYLE_DIR.mkdir(parents=True, exist_ok=True)
        SIGNATURE_PATH.write_text(DEFAULT_SIGNATURE, encoding="utf-8")
    return SIGNATURE_PATH.read_text(encoding="utf-8")


def update(new_body: str, *, append_evolution: str | None = None) -> None:
    """Overwrite the signature, optionally appending a dated line under "My evolution"."""
    STYLE_DIR.mkdir(parents=True, exist_ok=True)
    body = new_body.strip()
    if append_evolution:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        line = f"- {stamp}: {append_evolution.strip()}"
        if "## My evolution" in body:
            body = body.replace(
                "## My evolution",
                f"## My evolution\n{line}",
                1,
            )
        else:
            body += f"\n\n## My evolution\n{line}\n"
    SIGNATURE_PATH.write_text(body + "\n", encoding="utf-8")


def append_evolution_line(note: str) -> None:
    """Shortcut: keep the rest of the signature, just add an evolution line."""
    body = read()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = f"- {stamp}: {note.strip()}"
    if "## My evolution" in body:
        body = body.replace(
            "## My evolution",
            f"## My evolution\n{line}",
            1,
        )
    else:
        body += f"\n\n## My evolution\n{line}\n"
    SIGNATURE_PATH.write_text(body, encoding="utf-8")
