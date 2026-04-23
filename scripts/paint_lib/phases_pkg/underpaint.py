"""Phase 3: Underpainting (Phase 1 of the canvas build). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _warn


NAME = "underpaint"


def run(ctx: PipelineContext) -> None:
    """Dispatch to the correct underpainting style; draw strokes; handle style_schedule interleave."""
    from ..core import post, safe_phase
    from ..styles import (
        layered_underpainting,
        layered_underpainting_segmented,
        pointillism_underpainting,
        tenebrism_underpainting,
        van_gogh_underpainting,
        engraving_underpainting,
    )

    grid = ctx.grid
    cw = ctx.cell_w
    ch = ctx.cell_h

    # --- segmented path ---
    strokes = None
    if ctx.use_segmentation:
        try:
            pal = post('get_palette', {'n': 6})
            weights = [c.get('weight', 0) for c in pal.get('colors', [])]
            if weights:
                top_w = max(weights)
                top2 = sum(sorted(weights, reverse=True)[:2])
                if top_w > 0.40 or top2 > 0.68:
                    ctx.n_segments = min(ctx.n_segments, 4)
                    if ctx.verbose:
                        print(f'  (capping n_segments to {ctx.n_segments} — palette dominated)')
        except Exception as exc:
            _warn("palette_analysis", exc)

        seg = safe_phase(
            'segment_regions',
            lambda: post('segment_regions', {'n_segments': int(ctx.n_segments)}),
            fallback=None, verbose=ctx.verbose,
        )
        if seg is None:
            ctx.use_segmentation = False
        else:
            from PIL import Image as _PILImage
            import numpy as _np
            regions = seg.get('regions', [])
            ctx.segmentation_info = {
                'n_regions': seg.get('n_regions'),
                'path': seg.get('path'),
            }
            label_img = _PILImage.open(seg['path'])
            labels_arr = _np.asarray(label_img)
            fine = post('sample_grid', {'gx': 48, 'gy': 48})
            fine_grid_seg = fine.get('grid')
            strokes = layered_underpainting_segmented(
                regions, labels_arr, cw, ch,
                seed=ctx.seed, contrast_boost=ctx.contrast_boost,
                complementary_shadow=ctx.complementary_shadow,
                fine_grid=fine_grid_seg,
            )
            if ctx.verbose:
                print(f'  segmentation: {len(regions)} regions + 48×48 fine-grid accent override')

    # --- non-segmented path ---
    if not ctx.use_segmentation:
        if ctx.style_mode == 'van_gogh':
            strokes = van_gogh_underpainting(
                grid, cw, ch, ctx.direction_grid,
                seed=ctx.seed, contrast_boost=ctx.contrast_boost,
                complementary_shadow=ctx.complementary_shadow,
            )
        elif ctx.style_mode == 'engraving':
            strokes = engraving_underpainting(grid, cw, ch, seed=ctx.seed)
        elif ctx.style_mode == 'pointillism':
            fine = post('sample_grid', {'gx': 64, 'gy': 64})
            fine_grid = fine['grid']
            strokes = pointillism_underpainting(
                grid, cw, ch, seed=ctx.seed,
                contrast_boost=ctx.contrast_boost,
                complementary_shadow=ctx.complementary_shadow,
                fine_grid=fine_grid,
            )
        elif ctx.style_mode == 'tenebrism':
            fine = post('sample_grid', {'gx': 64, 'gy': 64})
            fine_grid_cg = fine['grid']
            strokes = tenebrism_underpainting(
                grid, cw, ch, seed=ctx.seed,
                contrast_boost=ctx.contrast_boost,
                fine_grid=fine_grid_cg,
            )
        else:
            strokes = layered_underpainting(
                grid, cw, ch, seed=ctx.seed, direction=ctx.direction,
                direction_grid=ctx.direction_grid,
                contrast_boost=ctx.contrast_boost,
                complementary_shadow=ctx.complementary_shadow,
            )

    # --- Phase 2: atmospheric fog (prepended before draw, matching original) ---
    # In the original pipeline the fog stroke was inserted at index 0 of strokes
    # before the single draw_strokes call that covered Phase 1+2 together.
    # Only fires when fog_hint is set and style is not pointillism/engraving.
    if (ctx.fog_hint and ctx.style_mode not in ('pointillism', 'engraving')):
        _fog_w = len(grid[0]) * cw if grid and grid[0] else 512
        _fog_h = len(grid) * ch if grid else 512
        strokes.insert(0, {
            'type': 'fog',
            'x': 0, 'y': 0, 'w': _fog_w, 'h': _fog_h,
            'color': ctx.fog_hint['color'],
            'alpha': ctx.fog_hint['alpha'],
            'direction': ctx.fog_hint['direction'],
            'fade': ctx.fog_hint['fade'],
        })

    # --- style_schedule interleave ---
    if ctx.style_schedule is not None:
        from .. import morph as _morph
        _under_t = _morph.PHASE_T["underpaint"]
        if _under_t > 0.0:
            _end_gen = _morph.STYLE_DISPATCH[ctx.style_schedule["end"]]
            _end_style = ctx.style_schedule["end"]
            if _end_style == "van_gogh":
                _end_strokes = _end_gen(
                    grid, cw, ch, ctx.direction_grid,
                    seed=ctx.seed + 1,
                    contrast_boost=ctx.contrast_boost,
                    complementary_shadow=ctx.complementary_shadow,
                )
            elif _end_style == "engraving":
                _end_strokes = _end_gen(grid, cw, ch, seed=ctx.seed + 1)
            else:
                _end_strokes = _end_gen(
                    grid, cw, ch,
                    seed=ctx.seed + 1,
                    direction=ctx.direction,
                    direction_grid=ctx.direction_grid,
                    contrast_boost=ctx.contrast_boost,
                    complementary_shadow=ctx.complementary_shadow,
                )
            strokes = _morph.interleave_strokes(strokes, _end_strokes, _under_t, seed=ctx.seed)

    post('draw_strokes', {'strokes': strokes, 'reasoning': 'Phase 1 · underpainting'})
    ctx.underpaint_strokes = len(strokes)
