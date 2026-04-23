"""Phase 5: Edge stroke plan (Phase 3). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _morph_params_at, _track_phase


NAME = "edge"


def run(ctx: PipelineContext) -> None:
    """Run edge_stroke_plan and draw edge strokes."""
    from ..core import post, track_phase

    _morph_params_at(ctx, "edge")  # advance t; result unused (edge_plan has no morph params)

    edge_plan = post('edge_stroke_plan', {
        'max_strokes': 'auto', 'min_length': 10, 'width': 3, 'alpha': 0.7,
        'sample_every': 2, 'seed': ctx.seed + 1,
    })
    ctx.edge_budget = edge_plan.get('auto_budget')

    if edge_plan['strokes']:
        post('draw_strokes', {'strokes': edge_plan['strokes'],
                              'reasoning': 'Phase 3 · edges'})
        ctx.edge_strokes = edge_plan['n']
        _track_phase('edges', ctx)
