"""Tool-server handlers for the duet feature.

Exposes two tools:
  - paint_duet: run a two-persona collaborative painting
  - list_personas: enumerate registered personas (built-in + community)
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._common import _REPO_ROOT, _safe_path, PathNotAllowed

_SCRIPTS = _REPO_ROOT / "scripts"


def _lazy_import_duet():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    from paint_lib import duet as _duet
    return _duet


def tool_paint_duet(args: dict) -> dict:
    """Run a two-persona critique-and-correct duet on a target."""
    duet = _lazy_import_duet()

    target_raw = args.get("target")
    if not target_raw:
        return {"error": "missing required arg: target"}

    try:
        target_path = _safe_path(target_raw)
    except PathNotAllowed as exc:
        return {"error": str(exc)}

    personas = args.get("personas")
    max_turns = int(args.get("max_turns", 6))
    seed = int(args.get("seed", 42))
    out_dir = args.get("out_dir")

    try:
        result = duet.paint_duet(
            str(target_path),
            personas=personas,
            max_turns=max_turns,
            seed=seed,
            out_dir=out_dir,
            verbose=False,
        )
        return result
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_list_personas(args: dict) -> dict:
    """Return all registered personas (built-in under personas/ plus any
    under $PERSONAS_PATH)."""
    duet = _lazy_import_duet()
    entries = []
    personas_root = (_REPO_ROOT / "personas").resolve()
    for name, p in sorted(duet.PERSONAS.items()):
        kind = "builtin"
        if p.source_path:
            try:
                Path(p.source_path).resolve().relative_to(personas_root)
            except ValueError:
                kind = "community"
        entries.append({
            "name": p.name,
            "style_mode": p.style_mode,
            "description": p.description,
            "kind": kind,
            "source_path": p.source_path or "",
            "cares_about": p.cares_about,
            "correction_budget": p.correction_budget,
        })
    return {"personas": entries, "count": len(entries)}
