"""Unit tests for the three simplest failure detectors in painter.failures.

Only the stroke-based and simple-canvas detectors are tested here because:
  - detect_too_dark_outlines: purely stroke-color-based, no image math
  - detect_over_rendered_fg: purely stroke-count-based, no image math
  - detect_under_covered: canvas-bytes only, simple color-distance check

The remaining 5 detectors (detect_subject_lost_in_bg, detect_muddy_underpaint,
detect_over_rendered_bg, detect_hard_banding, detect_direction_mismatch) all
require semantically meaningful image pairs (DOF photos, real gradient fields,
FFT-measurable grid artifacts) — deferred to a follow-up session with fixture
images.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image


# --- Helpers ------------------------------------------------------------------

def _make_png(color: tuple[int, int, int], size: int = 64) -> bytes:
    """Return a solid-color PNG in bytes."""
    arr = np.full((size, size, 3), color, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def _stroke(stype: str, color: str, width: int = 1, **kwargs) -> dict:
    return {"type": stype, "color": color, "width": width, **kwargs}


# --- detect_too_dark_outlines -------------------------------------------------

def test_too_dark_outlines_true_positive():
    """More than 5% of thin strokes near-pure-black should fire."""
    from painter.failures import detect_too_dark_outlines

    # 10 dark outlines out of 10 thin polylines → 100% ratio
    strokes = [_stroke("polyline", "#000000", width=1) for _ in range(10)]
    result = detect_too_dark_outlines(strokes=strokes)
    assert result is not None
    assert result["mode"] == "TOO_DARK_OUTLINES"
    assert result["severity"] in (2, 3)


def test_too_dark_outlines_true_negative():
    """Thin strokes that are clearly not near-pure-black should not fire."""
    from painter.failures import detect_too_dark_outlines

    # 10 warm-colored thin polylines
    strokes = [_stroke("polyline", "#c87840", width=1) for _ in range(10)]
    result = detect_too_dark_outlines(strokes=strokes)
    assert result is None


def test_too_dark_outlines_no_strokes():
    """Empty stroke list must return None (no crash)."""
    from painter.failures import detect_too_dark_outlines

    assert detect_too_dark_outlines(strokes=None) is None
    assert detect_too_dark_outlines(strokes=[]) is None


def test_too_dark_outlines_wide_strokes_ignored():
    """Strokes with width > 2 are not thin finishing strokes; must not fire."""
    from painter.failures import detect_too_dark_outlines

    strokes = [_stroke("polyline", "#000000", width=5) for _ in range(20)]
    result = detect_too_dark_outlines(strokes=strokes)
    assert result is None


# --- detect_over_rendered_fg --------------------------------------------------

def test_over_rendered_fg_true_positive():
    """finishing/brush ratio > 0.40 with enough brush strokes should fire."""
    from painter.failures import detect_over_rendered_fg

    # 100 brush strokes + 60 thin finishing → ratio = 0.60
    strokes = (
        [_stroke("brush", "#ffffff", width=8) for _ in range(100)]
        + [_stroke("polyline", "#ffffff", width=1) for _ in range(60)]
    )
    result = detect_over_rendered_fg(strokes=strokes)
    assert result is not None
    assert result["mode"] == "OVER_RENDERED_FG"
    assert "finishing/brush ratio" in result["metric"]


def test_over_rendered_fg_true_negative():
    """finishing/brush ratio <= 0.40 should not fire."""
    from painter.failures import detect_over_rendered_fg

    # 100 brush + 30 thin finishing → ratio = 0.30
    strokes = (
        [_stroke("brush", "#ffffff", width=8) for _ in range(100)]
        + [_stroke("polyline", "#ffffff", width=1) for _ in range(30)]
    )
    result = detect_over_rendered_fg(strokes=strokes)
    assert result is None


def test_over_rendered_fg_too_few_brush_strokes():
    """Fires only when brush count >= 100; fewer strokes → None."""
    from painter.failures import detect_over_rendered_fg

    # 50 brush + 50 finishing → ratio = 1.0 but brush < 100
    strokes = (
        [_stroke("brush", "#ffffff", width=8) for _ in range(50)]
        + [_stroke("polyline", "#ffffff", width=1) for _ in range(50)]
    )
    result = detect_over_rendered_fg(strokes=strokes)
    assert result is None


# --- detect_under_covered -----------------------------------------------------

def test_under_covered_true_positive():
    """Canvas mostly linen base color should fire."""
    from painter.failures import detect_under_covered

    # Linen base is #fbf7ee = (251, 247, 238) — paint the whole canvas that color
    canvas_bytes = _make_png((251, 247, 238))
    result = detect_under_covered(canvas=canvas_bytes)
    assert result is not None
    assert result["mode"] == "UNDER_COVERED"
    assert result["severity"] in (2, 3)


def test_under_covered_true_negative():
    """Canvas fully painted (no linen base showing) should not fire."""
    from painter.failures import detect_under_covered

    # Vivid blue — far from the linen base
    canvas_bytes = _make_png((60, 120, 200))
    result = detect_under_covered(canvas=canvas_bytes)
    assert result is None


def test_under_covered_no_strokes_kwarg_ignored():
    """detect_under_covered accepts **_ so strokes= must not cause a TypeError."""
    from painter.failures import detect_under_covered

    canvas_bytes = _make_png((60, 120, 200))
    # Should not raise even with extra keyword args
    result = detect_under_covered(canvas=canvas_bytes, strokes=[], target=canvas_bytes)
    assert result is None
