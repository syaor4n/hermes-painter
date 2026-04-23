"""Phase 8: Contour stroke plan (Phase 6). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _lost_and_found, _morph_params_at, _track_phase, painterly_spread


NAME = "contour"


def run(ctx: PipelineContext) -> None:
    """Run contour_stroke_plan with lost-and-found alpha randomisation."""
    from ..core import post

    _morph_params = _morph_params_at(ctx, "contour")
    _phase_contrast = _morph_params.get("contrast_boost", ctx.contrast_boost)

    contour_args = {
        'sigma': 1.8, 'min_length': 12, 'max_strokes': 'auto',
        'width': 2, 'alpha': 0.60, 'color_source': 'contrast',
        'stroke_type': 'bezier', 'simplify_tolerance': 1.2,
        'mask_path': ctx.mask_path, 'mask_boost': 2.5,
        'skip_short_fraction': 0.40, 'seed': ctx.seed + 5,
        'painterly': True,
        **ctx.finishing_shared,
        'contrast_boost': _phase_contrast,
    }
    if ctx.style_mode == 'van_gogh':
        contour_args['width'] = 3
        contour_args['alpha'] = 0.80
        contour_args['skip_short_fraction'] = 0.25
        contour_args['sigma'] = 2.2
        contour_args['painterly'] = True

    contour_plan = post('contour_stroke_plan', contour_args)
    ctx.contour_components = contour_plan.get('n_components', 0)

    if contour_plan['strokes']:
        contour_strokes_list = contour_plan['strokes']
        if ctx.style_mode != 'van_gogh':
            contour_strokes_list = _lost_and_found(contour_strokes_list, seed=ctx.seed + 11)
        if ctx.painterly_details and ctx.style_mode != 'van_gogh':
            contour_strokes_list = painterly_spread(contour_strokes_list,
                                                    halo_width_mult=2.5, halo_alpha=0.08,
                                                    anchor_alpha_scale=0.80)
        post('draw_strokes', {
            'strokes': contour_strokes_list,
            'reasoning': 'Phase 6 · contours (lost-and-found)' if ctx.style_mode != 'van_gogh' else 'Phase 6 · contours',
        })
        ctx.contour_strokes = len(contour_strokes_list)
        _track_phase('contours', ctx)
