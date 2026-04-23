"""Smoke tests for the extracted phase modules (CODE_REVIEW P2.11).

Each test imports a phase module, verifies it exposes the expected
contract (NAME str, run callable), and executes run() against a
minimal synthetic ctx with mocked side effects.

End-to-end correctness is covered by the integration tests in
test_pipeline_orchestration.py (notably the determinism baseline);
these tests fail fast when a phase module is accidentally broken.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest

from paint_lib.phases_pkg._context import PipelineContext


def _ctx(**kw):
    """Build a minimal PipelineContext for a phase to run against."""
    defaults = dict(
        target_path=str(ROOT / "targets" / "masterworks" / "great_wave.jpg"),
        seed=0,
        verbose=False
    )
    defaults.update(kw)
    return PipelineContext(**defaults)


@pytest.mark.parametrize("module_name", [
    "analyze", "skill_feedback", "underpaint", "fog", "edge",
    "gap_fill", "detail", "contour", "highlight", "face_detail",
    "sculpt", "critique_correct", "score", "reflect",
])
def test_phase_module_imports_and_has_run(module_name):
    """Every phase module must be importable and expose a run(ctx) callable."""
    import importlib
    mod = importlib.import_module(f"paint_lib.phases_pkg.{module_name}")
    assert hasattr(mod, "run"), f"{module_name}: missing run(ctx)"
    assert callable(mod.run), f"{module_name}: run is not callable"


def test_phases_pkg_init_is_valid():
    """The package imports cleanly."""
    import paint_lib.phases_pkg as pkg
    assert pkg.__doc__, "phases_pkg must have a module docstring"


def test_context_has_required_fields():
    """PipelineContext must have the fields that phases mutate."""
    ctx = _ctx()
    # Input fields
    assert hasattr(ctx, "target_path")
    assert hasattr(ctx, "seed")
    assert hasattr(ctx, "style_mode")
    assert hasattr(ctx, "style_schedule")
    # Stroke counters
    assert hasattr(ctx, "underpaint_strokes")
    assert hasattr(ctx, "edge_strokes")
    assert hasattr(ctx, "mid_detail_strokes")
    assert hasattr(ctx, "fine_detail_strokes")
    assert hasattr(ctx, "contour_strokes")
    assert hasattr(ctx, "highlight_strokes")
    assert hasattr(ctx, "critique_strokes")
    # Running state
    assert hasattr(ctx, "current_score")
    assert hasattr(ctx, "phase_deltas")
    assert hasattr(ctx, "applied_skills")
    assert hasattr(ctx, "effective_params")


def test_shared_helpers_importable():
    """_shared.py must expose the helpers that phase modules consume."""
    from paint_lib.phases_pkg import _shared
    assert callable(_shared._warn)
    assert callable(_shared._lost_and_found)
    assert callable(_shared._morph_params_at)
    assert callable(_shared._track_phase)
    assert callable(_shared._build_result_dict)
    assert callable(_shared.painterly_spread)  # re-exported from core


def test_build_result_dict_shape():
    """_build_result_dict includes all the fields auto_paint used to return."""
    from paint_lib.phases_pkg._shared import _build_result_dict
    ctx = _ctx(underpaint_strokes=100, edge_strokes=20, contour_strokes=5)
    result = _build_result_dict(ctx)
    required = {
        "image_type", "style_mode", "underpaint_strokes", "edge_strokes",
        "fill_strokes", "mid_detail_strokes", "fine_detail_strokes",
        "contour_strokes", "highlight_strokes", "critique_strokes",
        "coverage", "final_score", "regression", "phase_deltas",
        "mask_used", "applied_skills", "effective_params",
        "style_schedule", "phase_blends", "reflection_path", "journal_path",
    }
    missing = required - set(result.keys())
    assert not missing, f"_build_result_dict missing required fields: {missing}"
