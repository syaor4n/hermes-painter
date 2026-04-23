"""Collaborative painters — paint_duet orchestrator.

Two named painter personas alternate critique-and-correct turns on one
canvas, producing a painting that reads as a dialogue. See
docs/superpowers/specs/2026-04-22-collaborative-painters-design.md.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PERSONAS_DIR = _REPO_ROOT / "personas"

from . import morph

try:
    _src = _REPO_ROOT / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from painter.failures import DETECTORS as _FAILURE_DETECTORS
    VALID_FAILURE_MODES = {
        fn.__name__.replace("detect_", "").upper()
        for fn in _FAILURE_DETECTORS
    }
except Exception:
    VALID_FAILURE_MODES = {
        "TOO_DARK_OUTLINES", "SUBJECT_LOST_IN_BG", "MUDDY_UNDERPAINT",
        "OVER_RENDERED_BG", "UNDER_COVERED", "OVER_RENDERED_FG",
        "HARD_BANDING", "DIRECTION_MISMATCH",
    }

DEFAULT_CORRECTION_BUDGET = {
    "max_cells_per_turn": 6,
    "stroke_width": 3,
    "alpha": 0.55,
    "avoid_cells_painted_by_other": True,
}


@dataclass
class Persona:
    """One painter voice. Loaded from personas/<name>/persona.yaml."""
    name: str
    style_mode: str
    description: str = ""
    signature_essay: str = ""
    skills_tags: list[str] = field(default_factory=list)
    cares_about: dict[str, float] = field(default_factory=dict)
    correction_budget: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_CORRECTION_BUDGET)
    )
    source_path: str | None = None


@dataclass
class TurnResult:
    """One turn's outcome — either opening, correct, reject, or pass."""
    turn: int
    persona: str
    action: str   # "opening" | "correct" | "reject" | "pass"
    ssim: float | None
    n_strokes: int
    cells_painted: list[tuple[int, int]]
    findings: list[dict] | None = None
    snapshot_id: str | None = None
    rejected_reason: str | None = None


PERSONAS: dict[str, Persona] = {}


def _warn(msg: str) -> None:
    print(f"[duet] {msg}", file=sys.stderr)


def _validate_persona_file(path: Path) -> Persona | None:
    """Parse + validate one persona.yaml. Return Persona or None (logs warn)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        _warn(f"{path.name}: read failed: {e}")
        return None

    try:
        data = morph._parse_yaml(text)
    except Exception as e:
        _warn(f"{path.name}: parse failed: {e}")
        return None

    return _validate_persona_dict(data, source_path=path)


def _validate_persona_dict(data: dict, source_path: Path | None = None) -> Persona | None:
    """Shared validation — used by file loader and inline dict constructor."""
    name = str(data.get("name", "")).strip()
    if not name:
        _warn(f"{source_path or 'inline'}: empty or missing 'name'")
        return None

    style_mode = data.get("style_mode")
    if style_mode not in morph.STYLE_DEFAULTS:
        _warn(f"{name}: unknown style_mode {style_mode!r} "
              f"(known: {sorted(morph.STYLE_DEFAULTS)})")
        return None

    cares_raw = data.get("cares_about") or {}
    if not isinstance(cares_raw, dict):
        _warn(f"{name}: cares_about must be a dict")
        return None
    cares_about: dict[str, float] = {}
    for k, v in cares_raw.items():
        if k not in VALID_FAILURE_MODES:
            _warn(f"{name}: unknown failure mode {k!r} in cares_about "
                  f"(valid: {sorted(VALID_FAILURE_MODES)})")
            return None
        try:
            w = float(v)
        except (TypeError, ValueError):
            _warn(f"{name}: non-numeric weight {v!r} for {k}")
            return None
        if not (0.0 <= w <= 2.0):
            _warn(f"{name}: weight {w} for {k} clamped to [0, 2]")
            w = max(0.0, min(2.0, w))
        cares_about[k] = w

    budget_raw = data.get("correction_budget") or {}
    if not isinstance(budget_raw, dict):
        _warn(f"{name}: correction_budget must be a dict")
        return None
    budget = dict(DEFAULT_CORRECTION_BUDGET)
    budget.update(budget_raw)
    try:
        mc = int(budget.get("max_cells_per_turn", 6))
    except (TypeError, ValueError):
        _warn(f"{name}: max_cells_per_turn must be an int")
        return None
    if not (1 <= mc <= 20):
        _warn(f"{name}: max_cells_per_turn {mc} out of [1, 20]")
        return None
    budget["max_cells_per_turn"] = mc

    return Persona(
        name=name,
        style_mode=str(style_mode),
        description=str(data.get("description", "")).strip(),
        signature_essay=str(data.get("signature_essay", "")).strip(),
        skills_tags=list(data.get("skills_tags") or []),
        cares_about=cares_about,
        correction_budget=budget,
        source_path=str(source_path) if source_path else None,
    )


def _register_persona_from_file(path: Path, override_existing: bool = False) -> bool:
    p = _validate_persona_file(path)
    if p is None:
        return False
    if p.name in PERSONAS and not override_existing:
        _warn(f"{p.name}: already registered — refusing to shadow built-in")
        return False
    PERSONAS[p.name] = p
    return True


def _load_personas() -> None:
    """Scan personas/ + $PERSONAS_PATH. Called once at import time."""
    dirs: list[Path] = []
    if _PERSONAS_DIR.exists():
        dirs.append(_PERSONAS_DIR)
    for extra in os.environ.get("PERSONAS_PATH", "").split(":"):
        extra = extra.strip()
        if extra:
            dirs.append(Path(extra))

    for d in dirs:
        if not d.is_dir():
            continue
        for subdir in sorted(d.iterdir()):
            pfile = subdir / "persona.yaml"
            if pfile.exists():
                _register_persona_from_file(pfile)


_load_personas()


# --- Taste filter -------------------------------------------------------

def _style_affinity(target_rgb, style_mode: str) -> float:
    """Return [0, 1]: how much this persona's style naturally fits this cell.

    Rule-based hand-tuned mapping from target HSV to style preference.
    Higher = this persona's style would "claim" this cell in a critique.
    """
    import colorsys
    r, g, b = (float(c) / 255.0 for c in target_rgb[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    if style_mode == "van_gogh":
        warm_weight = 1.0 if (h < 0.15 or h > 0.85) else 0.3
        return max(0.0, min(1.0, warm_weight * (0.3 + 0.7 * s)))
    if style_mode == "tenebrism":
        return max(0.0, min(1.0, abs(v - 0.5) * 2.0))
    if style_mode == "pointillism":
        value_fit = 1.0 - abs(v - 0.5) * 2.0
        return max(0.0, min(1.0, value_fit * (0.3 + 0.7 * s)))
    if style_mode == "engraving":
        return max(0.0, min(1.0, 1.0 - s))
    return 0.5


def _pick_cells_by_affinity(regions, persona: Persona, avoid: set,
                             budget: int) -> list[dict]:
    """Score each region by persona's taste; return top `budget`.

    Mutates `avoid` — adds the picked cells' grid keys so subsequent turns
    don't immediately overwrite.
    """
    if budget <= 0:
        return []
    picks = []
    for cell in regions:
        key = (cell["x"] // 64, cell["y"] // 64)
        if key in avoid:
            continue
        affinity = _style_affinity(cell["target_rgb"], persona.style_mode)
        error = float(cell.get("error", 0.0))
        score = 0.6 * affinity + 0.4 * error
        picks.append((cell, score, key))
    picks.sort(key=lambda p: p[1], reverse=True)
    selected = picks[:budget]
    for _, _, key in selected:
        avoid.add(key)
    return [p[0] for p in selected]


# --- Interop helpers — thin indirection over core.post so tests can mock.

def _post(tool: str, payload: dict | None = None) -> dict:
    from . import core
    return core.post(tool, payload or {})


def _auto_paint(target: str, **kwargs) -> dict:
    from .pipeline import auto_paint
    return auto_paint(target, **kwargs)


def _current_ssim(target: str, post_fn=None) -> float | None:
    """Fetch canvas from /api/state and score against target. None on failure."""
    try:
        _src = _REPO_ROOT / "src"
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        from painter.critic import score as _score
        from .core import _read_canvas_bytes
        _post("dump_canvas", {})
        target_bytes = Path(target).read_bytes()
        canvas_bytes = _read_canvas_bytes()
        if canvas_bytes is None:
            return None
        result = _score(target_bytes, canvas_bytes, with_detail=False)
        return float(result.get("ssim", 0.0))
    except Exception as e:
        _warn(f"_current_ssim failed: {e}")
        return None


def _copy_canvas(dst: Path) -> None:
    """Snapshot the current viewer canvas to `dst`.

    Reads the canvas bytes from /api/state (base64) rather than copying the
    shared /tmp/painter_canvas.png dump. Eliminates cross-session
    contamination risk when multiple paint processes share /tmp.
    """
    from .core import _read_canvas_bytes

    try:
        canvas_bytes = _read_canvas_bytes()
    except Exception as e:
        _warn(f"_copy_canvas: fetch canvas failed: {e}")
        return
    if canvas_bytes is None:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(canvas_bytes)


def _persona_cell_mask(cells: list[dict], out_dir: Path,
                       turn_index: int, canvas_size: int = 512) -> Path:
    """Write a PIL mask PNG restricting strokes to the picked cells."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (canvas_size, canvas_size), 0)
    d = ImageDraw.Draw(img)
    for c in cells:
        x, y = int(c["x"]), int(c["y"])
        w, h = int(c["w"]), int(c["h"])
        d.rectangle([x, y, x + w, y + h], fill=255)
    mask_path = out_dir / f"mask_turn_{turn_index:02d}.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(mask_path)
    return mask_path


# --- Turn orchestration -------------------------------------------------

def _turn_opening(target: str, persona: Persona, seed: int,
                   out_dir: Path, verbose: bool = False) -> TurnResult:
    if verbose:
        print(f"[duet] turn 1 · {persona.name} · opening")
    result = _auto_paint(target, seed=seed, verbose=False,
                         style_mode=persona.style_mode)
    ssim = (result.get("final_score") or {}).get("ssim")
    n_strokes = sum(int(result.get(k, 0) or 0) for k in (
        "underpaint_strokes", "edge_strokes", "mid_detail_strokes",
        "fine_detail_strokes", "contour_strokes", "highlight_strokes",
    ))
    snap = _post("snapshot", {})
    snap_id = snap.get("id") if isinstance(snap, dict) else None
    _post("dump_canvas", {})
    _copy_canvas(out_dir / f"turn_01_{persona.name}.png")
    return TurnResult(
        turn=1, persona=persona.name, action="opening",
        ssim=float(ssim) if ssim is not None else None,
        n_strokes=n_strokes, cells_painted=[],
        findings=None, snapshot_id=snap_id,
    )


def _turn_correction(target: str, persona: Persona, avoid: set,
                      turn_index: int, seed: int, out_dir: Path,
                      verbose: bool = False) -> TurnResult:
    if verbose:
        print(f"[duet] turn {turn_index} · {persona.name}")

    # Step 1: critique
    critique = _post("critique_canvas", {})
    raw_findings = critique.get("findings", []) if isinstance(critique, dict) else []
    weighted_findings = [
        {**f, "weight": float(persona.cares_about.get(f.get("mode", ""), 0.0))}
        for f in raw_findings
    ]

    # Step 2: scan
    regions_resp = _post("get_regions", {"top": 12})
    regions = regions_resp.get("regions", []) if isinstance(regions_resp, dict) else []

    # Step 3: taste filter
    budget = int(persona.correction_budget.get("max_cells_per_turn", 6))
    picked = _pick_cells_by_affinity(regions, persona, avoid, budget=budget)
    if not picked:
        return TurnResult(
            turn=turn_index, persona=persona.name, action="pass",
            ssim=_current_ssim(target), n_strokes=0, cells_painted=[],
            findings=weighted_findings, snapshot_id=None,
        )

    # Step 4: pre-snapshot + pre-ssim
    pre_snap = _post("snapshot", {})
    pre_snap_id = pre_snap.get("id") if isinstance(pre_snap, dict) else None
    pre_ssim = _current_ssim(target)

    # Step 5: apply
    mask_path = _persona_cell_mask(picked, out_dir, turn_index)
    plan = _post("sculpt_correction_plan", {
        "cell_size": 8,
        "error_threshold": 20,
        "mask_path": str(mask_path),
        "max_strokes": budget * 40,
        "stroke_width": int(persona.correction_budget.get("stroke_width", 3)),
        "alpha": float(persona.correction_budget.get("alpha", 0.55)),
        "seed": turn_index * 17 + seed,
    })
    strokes = plan.get("strokes", []) if isinstance(plan, dict) else []
    if strokes:
        _post("draw_strokes", {
            "strokes": strokes,
            "reasoning": f"turn {turn_index} · {persona.name} · "
                          f"{len(picked)} cells",
        })

    # Step 6: accept or reject
    post_ssim = _current_ssim(target)
    action = "correct"
    rejected_reason: str | None = None
    if (pre_ssim is not None and post_ssim is not None and
            post_ssim < pre_ssim - 0.01):
        _post("restore", {"id": pre_snap_id})
        action = "reject"
        rejected_reason = "ssim_regressed"
        out_ssim = pre_ssim
        n_applied = 0
        applied_cells: list[tuple[int, int]] = []
    else:
        out_ssim = post_ssim
        n_applied = len(strokes)
        applied_cells = [(c["x"] // 64, c["y"] // 64) for c in picked]

    _post("dump_canvas", {})
    _copy_canvas(out_dir / f"turn_{turn_index:02d}_{persona.name}.png")

    return TurnResult(
        turn=turn_index, persona=persona.name, action=action,
        ssim=out_ssim, n_strokes=n_applied, cells_painted=applied_cells,
        findings=weighted_findings, snapshot_id=pre_snap_id,
        rejected_reason=rejected_reason,
    )


# --- Artifact writers ---------------------------------------------------

def _write_journal(path: Path, target: str, personas: list,
                   turns: list[TurnResult], reason: str, max_turns: int) -> None:
    """Human-readable turn-by-turn dialogue."""
    persona_names = [p.name if hasattr(p, "name") else str(p) for p in personas]
    lines = [
        f"# Duet — {Path(target).stem}",
        "",
        f"**Personas:** {' × '.join(persona_names)}  ·  "
        f"**Turns:** {len(turns)} of {max_turns} max  ·  "
        f"**Reason:** {reason}",
        "",
        "---",
        "",
    ]
    for tr in turns:
        lines.append(f"### Turn {tr.turn} — {tr.persona} · {tr.action}")
        lines.append("")
        if tr.findings:
            bits = [f"{f.get('mode', '?')} (severity {f.get('severity', '?')}, w={f.get('weight', 0):.1f})"
                    for f in tr.findings[:3]]
            lines.append("Critique surfaced: " + ", ".join(bits))
        if tr.action == "opening":
            lines.append(f"Opening paint — {tr.n_strokes} strokes, SSIM {tr.ssim or 0:.3f}.")
        elif tr.action == "correct":
            lines.append(f"Painted {tr.n_strokes} strokes across {len(tr.cells_painted)} cells.")
            lines.append(f"SSIM: {tr.ssim or 0:.3f}.")
        elif tr.action == "reject":
            lines.append(f"Attempted correction, SSIM regressed; rolled back via snapshot.")
            lines.append(f"Reason: {tr.rejected_reason}.")
        elif tr.action == "pass":
            lines.append("No cells matched this persona's affinity threshold — skipped.")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_trace(path: Path, turns: list[TurnResult]) -> None:
    import json
    lines = []
    for tr in turns:
        d = {
            "turn": tr.turn, "persona": tr.persona, "action": tr.action,
            "ssim": tr.ssim, "n_strokes": tr.n_strokes,
            "cells_painted": tr.cells_painted,
            "findings": tr.findings,
            "snapshot_id": tr.snapshot_id,
            "rejected_reason": tr.rejected_reason,
        }
        lines.append(json.dumps(d, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary(path: Path, personas: list, turns: list[TurnResult],
                    reason: str, early_stopped: bool) -> None:
    import json
    persona_names = [p.name if hasattr(p, "name") else str(p) for p in personas]
    summary = {
        "personas": persona_names,
        "n_turns": len(turns),
        "reason": reason,
        "early_stopped": early_stopped,
        "per_turn_ssim": [tr.ssim for tr in turns],
        "final_ssim": turns[-1].ssim if turns else None,
        "actions": [tr.action for tr in turns],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


# --- Main entry ---------------------------------------------------------

def paint_duet(
    target: str,
    personas: list | None = None,
    max_turns: int = 6,
    seed: int = 42,
    out_dir=None,
    verbose: bool = True,
) -> dict:
    """Run a two-persona duet on the given target.

    See docs/superpowers/specs/2026-04-22-collaborative-painters-design.md
    for the full semantics.
    """
    # Validation
    max_turns = max(2, min(20, int(max_turns)))
    if personas is None:
        personas = ["van_gogh_voice", "tenebrist_voice"]

    resolved: list[Persona] = []
    for p in personas:
        if isinstance(p, str):
            if p not in PERSONAS:
                raise ValueError(f"unknown persona: {p!r} "
                                  f"(known: {sorted(PERSONAS)})")
            resolved.append(PERSONAS[p])
        elif isinstance(p, dict):
            pobj = _validate_persona_dict(p, source_path=None)
            if pobj is None:
                raise ValueError(f"invalid inline persona: {p}")
            resolved.append(pobj)
        else:
            raise ValueError(f"persona must be str or dict, got {type(p).__name__}")

    if len(resolved) != 2:
        raise ValueError(f"paint_duet requires exactly 2 personas, "
                         f"got {len(resolved)}")

    # Output directory
    if out_dir is None:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        basename = Path(target).stem
        out_dir = _REPO_ROOT / "runs" / f"duet_{basename}_{ts}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load target (best-effort — tolerate offline / test environments)
    try:
        _post("clear", {})
        _post("load_target", {"path": target})
    except Exception:
        pass

    # Turn 1: opening
    turns: list[TurnResult] = [
        _turn_opening(target, resolved[0], seed=seed,
                       out_dir=out_dir, verbose=verbose)
    ]

    # Turns 2+: alternating corrections
    avoid: set = set()
    plateau = 0
    early_stopped = False
    reason = "max_turns"
    for i in range(2, max_turns + 1):
        persona = resolved[(i - 1) % 2]
        tr = _turn_correction(
            target, persona, avoid, turn_index=i, seed=seed,
            out_dir=out_dir, verbose=verbose,
        )
        turns.append(tr)

        prev_ssim = turns[-2].ssim
        cur_ssim = tr.ssim
        if (prev_ssim is not None and cur_ssim is not None
                and abs(cur_ssim - prev_ssim) < 0.005):
            plateau += 1
        elif tr.action == "pass":
            plateau += 1
        else:
            plateau = 0
        if plateau >= 2:
            early_stopped = True
            reason = "converged_early"
            break

    # Final artifacts
    _post("dump_canvas", {})
    _copy_canvas(out_dir / "canvas.png")
    _write_journal(out_dir / "duet_journal.md", target, resolved, turns,
                    reason=reason, max_turns=max_turns)
    _write_trace(out_dir / "trace.jsonl", turns)
    _write_summary(out_dir / "summary.json", resolved, turns,
                    reason=reason, early_stopped=early_stopped)

    return {
        "canvas_path": str(out_dir / "canvas.png"),
        "journal_path": str(out_dir / "duet_journal.md"),
        "trace_path": str(out_dir / "trace.jsonl"),
        "turns": [tr.__dict__ for tr in turns],
        "final_ssim": turns[-1].ssim or 0.0,
        "early_stopped": early_stopped,
        "reason": reason,
        "personas_used": [p.name for p in resolved],
    }
