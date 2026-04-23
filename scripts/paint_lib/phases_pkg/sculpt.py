"""Phase 11: Sculpt correction plan (Phase 8a). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _warn, _track_phase


NAME = "sculpt"


def run(ctx: PipelineContext) -> None:
    """Dense per-cell error correction on the saliency region.

    Gate: mask_path present AND style_mode not in (engraving, pointillism).

    Also runs the edge-density-triggered fine-detail pass (Phase 8b) when
    edge_density > 0.12 on dark/high_contrast targets — this lives here
    because it logically follows face_detail and precedes critique_correct,
    matching the original pipeline ordering.
    """
    from ..core import post

    # Phase 8b: edge-density-triggered fine-detail pass
    if (ctx.edge_density > 0.12
            and ctx.image_type in ('dark', 'high_contrast')
            and ctx.style_mode not in ('engraving', 'pointillism')):
        try:
            extra = post('detail_stroke_plan', {
                'max_strokes': 250,
                'percentile': 90.0,
                'width': 1, 'alpha': 0.65,
                'min_length': 3, 'sample_every': 1,
                'color_source': 'target',
                'seed': ctx.seed + 15,
            })
            if extra.get('strokes'):
                post('draw_strokes', {
                    'strokes': extra['strokes'],
                    'reasoning': f'Phase 8b · fine-structure detail (ed={ctx.edge_density:.2f})',
                })
                ctx.dense_sculpt_strokes = extra['n']
                _track_phase('dense_detail', ctx)
        except Exception as exc:
            _warn("dense_detail", exc)

    # Phase 8a: sculpt correction
    if not ctx.mask_path:
        return
    if ctx.style_mode in ('engraving', 'pointillism'):
        return

    _sculpt_params = {
        'dark':          {'error_threshold': 32, 'max_strokes': 150, 'alpha': 0.40},
        'muted':         {'error_threshold': 30, 'max_strokes': 180, 'alpha': 0.45},
        'bright':        {'error_threshold': 22, 'max_strokes': 300, 'alpha': 0.55},
        'high_contrast': {'error_threshold': 22, 'max_strokes': 300, 'alpha': 0.55},
        'balanced':      {'error_threshold': 22, 'max_strokes': 300, 'alpha': 0.55},
    }
    p = _sculpt_params.get(ctx.image_type, _sculpt_params['balanced'])

    try:
        sp = post('sculpt_correction_plan', {
            'cell_size': 8,
            'error_threshold': p['error_threshold'],
            'mask_path': ctx.mask_path,
            'mask_threshold': 0.30,
            'max_strokes': p['max_strokes'],
            'stroke_width': 4,
            'alpha': p['alpha'],
            'seed': ctx.seed + 13,
        })
        if sp.get('strokes'):
            post('draw_strokes', {
                'strokes': sp['strokes'],
                'reasoning': f'Phase 8a · sculpt correction (n={sp["n"]})',
            })
            ctx.sculpt_strokes = sp['n']
            _track_phase('sculpt', ctx)
    except Exception as exc:
        _warn("sculpt", exc)
