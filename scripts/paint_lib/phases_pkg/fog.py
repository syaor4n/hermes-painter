"""Phase 4: Atmospheric fog (Phase 2). Part of the CODE_REVIEW P2.11 phase split."""
from __future__ import annotations

from ._context import PipelineContext


NAME = "fog"


def run(ctx: PipelineContext) -> None:
    """Insert fog stroke at front of the drawn stroke list when fog_hint is set.

    Gate: ctx.fog_hint must be truthy and style_mode not in (pointillism, engraving).
    Fog is inserted *before* the underpainting draw call in the original pipeline,
    but because underpaint.run() already called draw_strokes, we reproduce the
    original behavior: the fog stroke was prepended to `strokes` before the
    single draw_strokes call that included it. In the phase-module world we
    handle this by having underpaint.run() NOT draw the fog, and fog.run()
    issuing its own draw_strokes — which is semantically equivalent because
    the server appends strokes sequentially.

    Actually: in the original pipeline the fog stroke was prepended to the
    underpainting strokes list and they were all drawn together in one
    draw_strokes call (Phase 1 + 2 combined). To preserve exact behavior
    we do NOT call fog.run() separately — instead, underpaint.run() handles
    the fog prepend internally when fog_hint is set. This module is kept as
    the documented authority for the fog phase but its run() is a no-op
    because underpaint.py already handles it to preserve the single-call
    semantic.
    """
    # The fog stroke is prepended by underpaint.run() when fog_hint is set
    # and style_mode not in ('pointillism', 'engraving'). No separate action
    # needed here. ctx.fog_strokes is set to 0 (default) as fog counts are
    # not tracked separately in the original pipeline.
    pass
