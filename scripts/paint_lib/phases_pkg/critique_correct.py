"""Phase 12: Critique-correct rounds (Phase 8). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext
from ._shared import _morph_params_at


NAME = "critique_correct"


def run(ctx: PipelineContext) -> None:
    """Run critique_correct if critique_rounds > 0."""
    from ..phases import critique_correct as _critique_correct

    _morph_params_at(ctx, "finish")  # advance t; no params threaded into critique_correct

    if ctx.critique_rounds > 0:
        ctx.critique_strokes = _critique_correct(
            n_rounds=ctx.critique_rounds, seed=ctx.seed, verbose=ctx.verbose
        )
