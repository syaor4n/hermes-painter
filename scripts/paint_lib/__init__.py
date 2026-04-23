"""Reusable painting primitives driven by the Hermes tool server.

Public API is flat — existing imports continue to work:

    from paint_lib import auto_paint, auto_paint_best_of
    from paint_lib import post, sample_grid, score_current_canvas
    from paint_lib import layered_underpainting, ...

Submodules:
  - core     : HTTP tool call, color math, scoring, phase tracking
  - styles   : underpainting variants (one per style_mode)
  - phases   : critique_correct, fill_gaps_with_grid
  - pipeline : auto_paint + auto_paint_best_of (target-driven)
"""
from .core import (
    post,
    _regression_alert,
    score_current_canvas,
    track_phase,
    safe_phase,
    sample_cell,
    sample_grid,
    _hex_to_rgb,
    _rgb_to_hex,
    _apply_contrast_boost,
    _to_luma,
    _bezier_sample_pts,
    _canvas_area_from_result,
    _apply_complementary_shadow,
    detect_grayscale_target,
    painterly_spread,
)
from .styles import (
    layered_underpainting,
    layered_underpainting_segmented,
    pointillism_underpainting,
    tenebrism_underpainting,
    van_gogh_underpainting,
    engraving_underpainting,
)
from .phases import critique_correct, fill_gaps_with_grid
from .pipeline import auto_paint, auto_paint_best_of

__all__ = [
    'post',
    'score_current_canvas',
    'track_phase',
    'safe_phase',
    'sample_cell',
    'sample_grid',
    'detect_grayscale_target',
    'painterly_spread',
    'layered_underpainting',
    'layered_underpainting_segmented',
    'pointillism_underpainting',
    'tenebrism_underpainting',
    'van_gogh_underpainting',
    'engraving_underpainting',
    'critique_correct',
    'fill_gaps_with_grid',
    'auto_paint',
    'auto_paint_best_of',
]
