"""Phase 7: Mid and fine detail (Phase 5a/5b). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _morph_params_at, _track_phase, painterly_spread


NAME = "detail"


def run(ctx: PipelineContext) -> None:
    """Run mid-detail and fine-detail passes. Skip for van_gogh style."""
    from ..core import post

    # Build finishing_shared from ctx (must be done after gap_fill sets gaps_coverage)
    focus_center = None
    focus_radius = 200.0
    if ctx.saliency_info and ctx.saliency_info.get('bbox'):
        bx, by, bw, bh = ctx.saliency_info['bbox']
        focus_center = [bx + bw // 2, by + bh // 2]
        focus_radius = max(100.0, 0.6 * max(bw, bh))
    ctx.finishing_shared = {
        'contrast_boost': ctx.contrast_boost,
        'width_jitter': True,
        'focus_center': focus_center,
        'focus_radius': focus_radius,
        'focus_falloff': 0.30,
    }

    # Phase 5a: mid-detail
    _morph_params = _morph_params_at(ctx, "gap_detail")
    _phase_contrast = _morph_params.get("contrast_boost", ctx.contrast_boost)

    mid_plan = post('detail_stroke_plan', {
        'max_strokes': 'auto', 'percentile': 94, 'width': 1, 'alpha': 0.45,
        'min_length': 6, 'sample_every': 1, 'color_source': 'contrast',
        'mask_path': ctx.mask_path, 'mask_threshold': 0.25, 'seed': ctx.seed + 3,
        **ctx.finishing_shared,
        'contrast_boost': _phase_contrast,
    })

    # Phase 5b: fine-detail
    _morph_params = _morph_params_at(ctx, "detail_fine")
    _phase_contrast = _morph_params.get("contrast_boost", ctx.contrast_boost)

    fine_plan = post('detail_stroke_plan', {
        'max_strokes': 'auto', 'percentile': 96.0, 'width': 1, 'alpha': 0.70,
        'min_length': 4, 'sample_every': 1, 'color_source': 'target',
        'mask_path': ctx.mask_path, 'mask_threshold': 0.20, 'seed': ctx.seed + 4,
        **ctx.finishing_shared,
        'contrast_boost': _phase_contrast,
    })

    ctx.mid_detail_strokes = mid_plan['n']
    ctx.fine_detail_strokes = fine_plan['n']

    if mid_plan['strokes'] and ctx.style_mode != 'van_gogh':
        mid_strokes = mid_plan['strokes']
        if ctx.painterly_details:
            mid_strokes = painterly_spread(mid_strokes,
                                           halo_width_mult=3.0, halo_alpha=0.08,
                                           anchor_alpha_scale=0.75)
        post('draw_strokes', {
            'strokes': mid_strokes,
            'reasoning': 'Phase 5a · mid-detail (painterly)' if ctx.painterly_details else 'Phase 5a · mid-detail',
        })
        _track_phase('mid_detail', ctx)

    if fine_plan['strokes'] and ctx.style_mode != 'van_gogh':
        fine_strokes = fine_plan['strokes']
        if ctx.painterly_details:
            fine_strokes = painterly_spread(fine_strokes,
                                            halo_width_mult=2.8, halo_alpha=0.10,
                                            anchor_alpha_scale=0.75)
        post('draw_strokes', {
            'strokes': fine_strokes,
            'reasoning': 'Phase 5b · fine-detail (painterly)' if ctx.painterly_details else 'Phase 5b · fine-detail',
        })
        _track_phase('fine_detail', ctx)
