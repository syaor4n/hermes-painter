"""Phase 13: Final score + regression alert + coverage. Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

import sys
from pathlib import Path

from ._context import PipelineContext
from ._shared import _warn


NAME = "score"


def run(ctx: PipelineContext) -> None:
    """Compute final SSIM score, regression alert, and coverage."""
    from ..core import post, _regression_alert, _read_canvas_bytes

    post('dump_canvas', {})

    try:
        _here2 = Path(__file__).resolve().parent.parent.parent
        _src2 = _here2.parent / 'src'
        if str(_src2) not in sys.path:
            sys.path.insert(0, str(_src2))
        from painter.critic import score as _score
        target_bytes = Path(ctx.target_path).read_bytes()
        canvas_bytes = _read_canvas_bytes()
        if canvas_bytes is None:
            ctx.final_score = None
        else:
            ctx.final_score = _score(target_bytes, canvas_bytes)
    except Exception as exc:
        _warn("final_score", exc)
        ctx.final_score = None

    ctx.regression = None
    if ctx.final_score:
        ctx.regression = _regression_alert(ctx.target_path, ctx.final_score, verbose=ctx.verbose)

    # Record coverage from last gap measurement
    ctx.coverage = ctx.gaps_coverage
