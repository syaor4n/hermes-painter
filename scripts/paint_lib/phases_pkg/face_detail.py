"""Phase 10: Face detail (Phase 7.8). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _warn, _track_phase


NAME = "face_detail"


def run(ctx: PipelineContext) -> None:
    """Detect faces and draw fine correction strokes over them.

    Gate: use_face_detail AND style_mode not in (engraving, pointillism, tenebrism).
    Respects style_schedule budget scaling via PHASE_T["highlight"].
    """
    from ..core import post

    _face_budget_scale = 1.0
    if ctx.style_schedule is not None:
        from .. import morph as _morph
        _face_budget_scale = 1.0 - _morph.PHASE_T["highlight"]
    if _face_budget_scale < 0.1:
        _face_budget_scale = 0.0

    if not ctx.use_face_detail:
        return
    if ctx.style_mode in ('engraving', 'pointillism', 'tenebrism'):
        return
    if _face_budget_scale <= 0.0:
        return

    try:
        df = post('detect_faces', {'min_size': 60})
        faces = df.get('faces') or []
        if faces:
            fp = post('face_detail_plan', {
                'faces': faces,
                'padding': 0.18,
                'cell_size': 4,
                'error_threshold': 18,
                'max_strokes_per_face': int(240 * _face_budget_scale),
                'alpha': 0.75,
                'seed': ctx.seed + 14,
            })
            if fp.get('strokes'):
                post('draw_strokes', {
                    'strokes': fp['strokes'],
                    'reasoning': f'Phase 7.8 · face detail (n_faces={len(faces)})',
                })
                ctx.face_detail_strokes = fp['n']
                _track_phase('face_detail', ctx)
    except Exception as exc:
        _warn("face_detail", exc)
