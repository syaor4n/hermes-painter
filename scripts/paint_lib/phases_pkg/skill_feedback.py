"""Phase 2: Apply skill effects to bias pipeline parameters. Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext


NAME = "skill_feedback"


def run(ctx: PipelineContext) -> None:
    """Read skills scoped to ctx.image_type, apply dimensional_effects deltas."""
    from ..core import apply_skill_effects

    ctx.applied_skills = []
    ctx.effective_params = None

    if not ctx.apply_feedback:
        return

    _base_kwargs = {
        'contrast_boost': ctx.contrast_boost,
        'complementary_shadow': ctx.complementary_shadow,
        'critique_rounds': ctx.critique_rounds,
        'painterly_details': ctx.painterly_details,
    }
    eff_style, eff_kw, effective_params, applied_skills = apply_skill_effects(
        ctx.image_type, ctx.style_mode, _base_kwargs
    )
    ctx.style_mode = eff_style
    ctx.contrast_boost = eff_kw['contrast_boost']
    ctx.complementary_shadow = eff_kw['complementary_shadow']
    ctx.critique_rounds = eff_kw['critique_rounds']
    ctx.painterly_details = eff_kw['painterly_details']
    ctx.effective_params = effective_params
    ctx.applied_skills = applied_skills

    if ctx.verbose and applied_skills:
        deltas = effective_params['deltas']
        print(
            f'  feedback[{ctx.image_type}]: {len(applied_skills)} skill(s) · '
            f'Δcontrast={deltas["contrast_boost"]:+.2f} '
            f'Δcomp_shadow={deltas["complementary_shadow"]:+.2f} '
            f'Δcritique={deltas["critique_rounds"]:+d} '
            f'painterly={ctx.painterly_details}'
        )

    # Style-specific parameter overrides (applied after skill deltas)
    if ctx.style_mode == 'engraving':
        ctx.grayscale = True
        ctx.complementary_shadow = 0.0
        ctx.use_highlights = False
    elif ctx.style_mode == 'van_gogh':
        ctx.complementary_shadow = max(ctx.complementary_shadow, 0.18)
    elif ctx.style_mode == 'pointillism':
        ctx.complementary_shadow = max(ctx.complementary_shadow, 0.20)
        ctx.use_highlights = False
    elif ctx.style_mode == 'tenebrism':
        ctx.complementary_shadow = 0.0
