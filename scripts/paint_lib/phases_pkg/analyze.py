"""Phase 1: Target classification and analysis. Part of the CODE_REVIEW P2.11 phase split.

Split into two sub-functions:
  run_pre(ctx)  — called before skill_feedback: classifies image, fetches strategy,
                  computes saliency. No parameter-sensitive work.
  run_post(ctx) — called after skill_feedback: detects grayscale, samples grid,
                  builds direction field. These depend on the final style_mode and
                  contrast_boost (which skill_feedback may have changed).
"""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _warn


NAME = "analyze"


def run_pre(ctx: PipelineContext) -> None:
    """Classify target, fetch analysis strategy, compute saliency mask.

    Must run BEFORE skill_feedback because image_type is needed to scope skills.
    """
    from ..core import post, safe_phase

    load_info = post('load_target', {'path': ctx.target_path}) or {}
    ctx.image_type = (load_info.get('classification') or {}).get('type', 'balanced')

    analysis = post('analyze_target', {})
    ctx.strategy = analysis['strategy']
    grid_size = ctx.strategy['grid_size']
    ctx.direction = ctx.strategy['direction']
    ctx.fog_hint = ctx.strategy['suggested_fog']
    ctx.edge_density = float((analysis.get('edges') or {}).get('density', 0.0))

    # Adaptive grid: dark/high_contrast scenes get one tier up
    if ctx.image_type in ('dark', 'high_contrast'):
        _tier_up = {16: 24, 24: 32, 32: 32}
        grid_size = _tier_up.get(grid_size, grid_size)
    ctx.grid_size = grid_size

    # Saliency mask
    ctx.mask_path = None
    ctx.saliency_info = None
    if ctx.use_saliency:
        saliency_info = safe_phase(
            'saliency_mask',
            lambda: post('saliency_mask', {}),
            fallback={}, verbose=ctx.verbose,
        ) or {}
        ctx.saliency_info = saliency_info
        if (saliency_info.get('separability', 0) > 0.18
                and 0.05 < saliency_info.get('fg_fraction', 0) < 0.8):
            ctx.mask_path = saliency_info.get('path')


def run_post(ctx: PipelineContext) -> None:
    """Detect grayscale, sample grid, build direction field.

    Must run AFTER skill_feedback because style_mode (van_gogh check) and
    contrast_boost (grayscale scaling) may have been updated by skill effects.
    """
    from ..core import post, sample_grid, _to_luma, detect_grayscale_target

    # Grayscale detection (engraving sets this to True in skill_feedback)
    if ctx.grayscale is None:
        ctx.grayscale = detect_grayscale_target(ctx.target_path)
    if ctx.grayscale:
        ctx.contrast_boost = ctx.contrast_boost * 0.5
        ctx.complementary_shadow = 0.0

    if ctx.verbose:
        sal = 'Y' if ctx.mask_path else 'N'
        gray_flag = ' · grayscale' if ctx.grayscale else ''
        print(
            f'  auto: grid={ctx.grid_size}, dir={ctx.direction}, '
            f'fog={"Y" if ctx.fog_hint else "N"}, '
            f'saliency={sal}, complexity={ctx.strategy["complexity"]}{gray_flag}'
        )

    # Sample grid
    grid, cw, ch = sample_grid(ctx.grid_size, ctx.grid_size)
    if ctx.grayscale:
        grid = [[_to_luma(c) for c in row] for row in grid]
    ctx.grid = grid
    ctx.cell_w = cw
    ctx.cell_h = ch

    # Direction field (for use_local_direction and van_gogh)
    ctx.direction_grid = None
    if ctx.use_local_direction or ctx.style_mode == 'van_gogh':
        df = post('direction_field_grid', {
            'grid_size': min(16, ctx.grid_size),
            'coherence_floor': 0.08,
        })
        ctx.direction_grid = df['grid']


def run(ctx: PipelineContext) -> None:
    """Full analyze phase (pre + post). Only use when skill_feedback is not called."""
    run_pre(ctx)
    run_post(ctx)
