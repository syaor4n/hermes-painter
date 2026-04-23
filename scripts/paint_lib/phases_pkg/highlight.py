"""Phase 9: Highlight stroke plan (Phase 7). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _morph_params_at, _track_phase


NAME = "highlight"


def run(ctx: PipelineContext) -> None:
    """Run highlight_stroke_plan. Gate: ctx.use_highlights."""
    from ..core import post

    if not ctx.use_highlights:
        ctx.highlight_strokes = 0
        ctx.highlight_candidates = 0
        return

    _morph_params = _morph_params_at(ctx, "highlight")
    _phase_contrast = _morph_params.get("contrast_boost", ctx.contrast_boost)

    hl_args = {
        'mask_path': ctx.mask_path, 'seed': ctx.seed + 6,
        **ctx.finishing_shared,
        'contrast_boost': _phase_contrast,
    }
    if ctx.grayscale:
        hl_args['warm_tint'] = 0.0

    highlight_plan = post('highlight_stroke_plan', hl_args)
    ctx.highlight_candidates = highlight_plan.get('candidates', 0)

    if highlight_plan['strokes']:
        post('draw_strokes', {'strokes': highlight_plan['strokes'],
                              'reasoning': 'Phase 7 · highlights'})
        ctx.highlight_strokes = highlight_plan['n']
        _track_phase('highlights', ctx)
