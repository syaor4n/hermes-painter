"""Shared helpers used by multiple phase modules. Copied from pipeline.py
during the phase refactor (CODE_REVIEW P2.11). The originals in pipeline.py
stay in place until the thinning commit that removes all inlined phase
bodies — both copies coexist during the intermediate extraction tasks."""
from __future__ import annotations
import random as _random
import sys
from pathlib import Path

from ._context import PipelineContext


def _warn(phase: str, exc: BaseException) -> None:
    print(f"[pipeline] {phase} failed: {type(exc).__name__}: {exc}",
          file=sys.stderr)


def _lost_and_found(strokes: list[dict], seed: int = 0,
                     p_sharp: float = 0.30, p_faded: float = 0.20,
                     sharp_mult: float = 1.15, faded_mult: float = 0.35) -> list[dict]:
    """Randomize contour alpha so 30% look razor-sharp, 50% medium, 20% lost.
    Copy of pipeline.py::_lost_and_found (pre-refactor).
    """
    r = _random.Random(seed)
    out = []
    for s in strokes:
        s2 = dict(s)
        base = float(s2.get("alpha", 0.6))
        roll = r.random()
        if roll < p_sharp:
            s2["alpha"] = min(1.0, base * sharp_mult)
        elif roll < p_sharp + (1.0 - p_sharp - p_faded):
            s2["alpha"] = base
        else:
            s2["alpha"] = max(0.15, base * faded_mult)
        out.append(s2)
    return out


def _morph_params_at(ctx: PipelineContext, phase_name: str) -> dict:
    """Return blended parameter overrides for `phase_name`, or {} if no schedule."""
    if ctx.style_schedule is None:
        return {}
    from .. import morph as _morph
    t = _morph.PHASE_T[phase_name]
    return _morph.blend_params(ctx.style_schedule["start"],
                                ctx.style_schedule["end"], t)


def _track_phase(name: str, ctx: PipelineContext) -> None:
    """Update ctx.phase_deltas with per-phase SSIM delta."""
    from ..core import track_phase
    ctx.current_score = track_phase(name, ctx.phase_deltas,
                                     ctx.target_path, ctx.current_score)


def _build_result_dict(ctx: PipelineContext, *,
                        extras: dict | None = None) -> dict:
    """Assemble the dict that auto_paint returns, from ctx's state."""
    result = {
        "strategy": ctx.strategy,
        "saliency": ctx.saliency_info,
        "image_type": ctx.image_type,
        "style_mode": ctx.style_mode,
        "underpaint_strokes": ctx.underpaint_strokes,
        "edge_strokes": ctx.edge_strokes,
        "fill_strokes": ctx.fill_strokes,
        "mid_detail_strokes": ctx.mid_detail_strokes,
        "fine_detail_strokes": ctx.fine_detail_strokes,
        "contour_strokes": ctx.contour_strokes,
        "contour_components": ctx.contour_components,
        "highlight_strokes": ctx.highlight_strokes,
        "highlight_candidates": ctx.highlight_candidates,
        "impasto_strokes": ctx.impasto_strokes,
        "face_detail_strokes": ctx.face_detail_strokes,
        "sculpt_strokes": ctx.sculpt_strokes,
        "dense_sculpt_strokes": ctx.dense_sculpt_strokes,
        "critique_strokes": ctx.critique_strokes,
        "edge_density": ctx.edge_density,
        "edge_budget": ctx.edge_budget,
        "coverage": ctx.coverage,
        "final_score": ctx.final_score,
        "regression": ctx.regression,
        "phase_deltas": ctx.phase_deltas,
        "mask_used": ctx.mask_path is not None,
        "applied_skills": ctx.applied_skills,
        "effective_params": ctx.effective_params,
        "style_schedule": ctx.style_schedule,
        "phase_blends": ctx.phase_blends,
        "reflection_path": ctx.reflection_path,
        "journal_path": ctx.journal_path,
    }
    if extras:
        result.update(extras)
    return result


# painterly_spread is imported from paint_lib.core where it already lives.
# Re-export here for phase modules that need it.
from ..core import painterly_spread  # noqa: E402, F401
