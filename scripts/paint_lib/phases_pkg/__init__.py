"""Phase modules for auto_paint — one module per phase.

Each module exports `NAME: str` and `run(ctx: PipelineContext) -> None`.
See docs/superpowers/specs/2026-04-22-pipeline-phase-split-design.md.

CODE_REVIEW P2.11: 14 phase modules extracted from pipeline.py.
"""
from . import (  # noqa: F401
    analyze,
    skill_feedback,
    underpaint,
    fog,
    edge,
    gap_fill,
    detail,
    contour,
    highlight,
    face_detail,
    sculpt,
    critique_correct,
    score,
    reflect,
)
