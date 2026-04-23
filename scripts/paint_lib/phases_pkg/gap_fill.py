"""Phase 6: Gap fill (Phase 4). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _morph_params_at, _track_phase


NAME = "gap_fill"


def run(ctx: PipelineContext) -> None:
    """Fill canvas gaps when coverage < 95%."""
    from ..core import post
    from ..phases import fill_gaps_with_grid

    _morph_params = _morph_params_at(ctx, "gap_detail")

    gaps = post('dump_gaps', {})
    ctx.gaps_coverage = gaps['coverage']

    if gaps['coverage'] < 0.95:
        if ctx.verbose:
            print(f'  coverage {gaps["coverage"]:.1%} < 95% → gap-fill pass')
        fill_plan = fill_gaps_with_grid(ctx.grid, ctx.cell_w, ctx.cell_h, seed=ctx.seed + 2)
        if fill_plan:
            post('draw_strokes', {'strokes': fill_plan, 'reasoning': 'Phase 4 · gap-fill'})
            ctx.fill_strokes = len(fill_plan)
            _track_phase('gap_fill', ctx)
        gaps = post('dump_gaps', {})
        ctx.gaps_coverage = gaps['coverage']
