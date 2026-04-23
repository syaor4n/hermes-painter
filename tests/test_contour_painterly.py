"""Unit tests for the painterly contour helpers — pure functions, no services."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pytest
import random

from painter.tools import plans as P


# ---------- _slice_path ----------

def test_slice_path_full_range_returns_full_path():
    path = [(0, 0), (10, 0), (20, 0), (30, 0)]
    out = P._slice_path(path, 0.0, 1.0)
    assert out[0] == (0, 0)
    assert out[-1] == (30, 0)


def test_slice_path_half_range_returns_half_by_arc_length():
    path = [(0, 0), (10, 0), (20, 0), (30, 0)]  # total length 30
    out = P._slice_path(path, 0.0, 0.5)
    total = _arc_length(out)
    assert abs(total - 15.0) < 1e-6


def test_slice_path_short_range_returns_at_least_two_points():
    path = [(0, 0), (100, 0)]
    out = P._slice_path(path, 0.2, 0.22)
    assert len(out) >= 2


def _arc_length(path):
    return sum(((path[i+1][0] - path[i][0])**2 +
                (path[i+1][1] - path[i][1])**2) ** 0.5
               for i in range(len(path) - 1))


# ---------- _jitter_perpendicular ----------

def test_jitter_preserves_endpoints():
    path = [(0, 0), (10, 0), (20, 0), (30, 0)]
    rng = random.Random(42)
    out = P._jitter_perpendicular(path, max_px=5.0, rng=rng)
    assert out[0] == path[0]
    assert out[-1] == path[-1]


def test_jitter_interior_points_within_max_px():
    path = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0)]
    rng = random.Random(42)
    out = P._jitter_perpendicular(path, max_px=3.0, rng=rng)
    for orig, new in zip(path[1:-1], out[1:-1]):
        dx = new[0] - orig[0]
        dy = new[1] - orig[1]
        dist = (dx*dx + dy*dy) ** 0.5
        assert dist <= 3.0 + 1e-6, f"{orig} → {new} offset {dist}"


# ---------- _tapered_width ----------

def test_tapered_width_narrow_at_ends():
    base = 10
    w_start = P._tapered_width(base, position=0.0, seed=1)
    w_mid = P._tapered_width(base, position=0.5, seed=1)
    w_end = P._tapered_width(base, position=1.0, seed=1)
    assert w_start < w_mid
    assert w_end < w_mid


def test_tapered_width_respects_min_width():
    for pos in (0.0, 0.5, 1.0):
        assert P._tapered_width(1, position=pos, seed=0) >= 1


# ---------- _sample_canvas_rgb ----------

def test_sample_canvas_rgb_returns_hex_at_correct_pixel():
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    arr[5, 5] = [200, 100, 50]
    out = P._sample_canvas_rgb(arr, (5.0, 5.0))
    assert out == "#c86432"


def test_sample_canvas_rgb_clamps_out_of_bounds():
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    arr[9, 9] = [10, 20, 30]
    out = P._sample_canvas_rgb(arr, (100.0, 100.0))
    assert out == "#0a141e"


# ---------- _fetch_current_canvas ----------

def test_fetch_current_canvas_returns_none_on_network_failure(monkeypatch):
    import urllib.request
    def boom(*a, **k):
        raise ConnectionError("services down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    out = P._fetch_current_canvas()
    assert out is None


# ---------- _painterly_contour_strokes ----------

def test_painterly_emits_brush_bristle_strokes():
    path = [(i * 3, 0) for i in range(20)]
    canvas = np.full((512, 512, 3), 180, dtype=np.uint8)
    rng = random.Random(0)
    strokes = P._painterly_contour_strokes(
        simplified_path=path, current_canvas=canvas, base_width=2,
        args={
            "painterly_strokes_per_component": "auto",
            "painterly_width_jitter": 0.5,
            "painterly_alpha_range": [0.30, 0.55],
            "painterly_position_jitter_px": [1.0, 2.5],
            "painterly_segment_coverage": [0.35, 0.55],
        }, rng=rng,
    )
    assert len(strokes) >= 2, "auto must emit at least 2 strokes per component"
    assert len(strokes) <= 8, "auto must cap at 8 strokes per component"
    for s in strokes:
        assert s["type"] == "brush"
        assert s["texture"] == "bristle"


def test_painterly_stroke_alpha_within_range():
    path = [(i * 3, 0) for i in range(20)]
    canvas = np.full((512, 512, 3), 180, dtype=np.uint8)
    rng = random.Random(0)
    strokes = P._painterly_contour_strokes(
        simplified_path=path, current_canvas=canvas, base_width=2,
        args={
            "painterly_strokes_per_component": "auto",
            "painterly_width_jitter": 0.5,
            "painterly_alpha_range": [0.30, 0.55],
            "painterly_position_jitter_px": [1.0, 2.5],
            "painterly_segment_coverage": [0.35, 0.55],
        }, rng=rng,
    )
    for s in strokes:
        assert 0.30 <= s["alpha"] <= 0.55


def test_painterly_explicit_count_overrides_auto():
    path = [(i * 3, 0) for i in range(50)]
    canvas = np.full((512, 512, 3), 180, dtype=np.uint8)
    rng = random.Random(0)
    strokes = P._painterly_contour_strokes(
        simplified_path=path, current_canvas=canvas, base_width=2,
        args={
            "painterly_strokes_per_component": 4,
            "painterly_width_jitter": 0.5,
            "painterly_alpha_range": [0.30, 0.55],
            "painterly_position_jitter_px": [1.0, 2.5],
            "painterly_segment_coverage": [0.35, 0.55],
        }, rng=rng,
    )
    assert len(strokes) == 4


# ---------- handler-level tests ----------

def test_painterly_false_emits_non_brush(monkeypatch):
    """painterly=False must skip canvas fetch AND emit non-brush strokes."""
    fake_target = np.full((256, 256, 3), 120, dtype=np.uint8)
    # Create a detectable edge so Canny+skeletonize finds a component
    fake_target[100:150, 50:200] = 255
    monkeypatch.setattr(P, "_target_array", lambda: fake_target)

    called = {"fetched": False}
    def should_not_be_called():
        called["fetched"] = True
        return None
    monkeypatch.setattr(P, "_fetch_current_canvas", should_not_be_called)

    result = P.tool_contour_stroke_plan({
        "painterly": False,
        "sigma": 1.5, "min_length": 5, "max_strokes": 20,
        "stroke_type": "polyline", "width": 2, "alpha": 0.7,
        "seed": 0,
    })
    assert called["fetched"] is False, "painterly=False must skip canvas fetch"
    for s in result["strokes"]:
        assert s["type"] in ("polyline", "bezier")


def test_painterly_true_emits_brush_strokes(monkeypatch):
    """painterly=True (default) emits brush-bristle strokes."""
    fake_target = np.zeros((256, 256, 3), dtype=np.uint8)
    fake_target[100:150, 50:200] = 255
    monkeypatch.setattr(P, "_target_array", lambda: fake_target)
    monkeypatch.setattr(P, "_fetch_current_canvas",
                        lambda: np.full((256, 256, 3), 180, dtype=np.uint8))

    result = P.tool_contour_stroke_plan({
        "sigma": 1.5, "min_length": 5, "max_strokes": 30,
        "seed": 0,  # painterly defaults to True
    })
    if result["strokes"]:
        for s in result["strokes"]:
            assert s["type"] == "brush", \
                f"all painterly strokes must be brush type, got {s['type']}"


def test_painterly_true_falls_back_to_target_on_canvas_fetch_fail(monkeypatch):
    """When _fetch_current_canvas returns None, handler still emits brush strokes."""
    fake_target = np.zeros((256, 256, 3), dtype=np.uint8)
    fake_target[100:150, 50:200] = [200, 100, 50]
    monkeypatch.setattr(P, "_target_array", lambda: fake_target)
    monkeypatch.setattr(P, "_fetch_current_canvas", lambda: None)

    result = P.tool_contour_stroke_plan({
        "sigma": 1.5, "min_length": 5, "max_strokes": 10,
        "seed": 0,
    })
    for s in result["strokes"]:
        assert s["type"] == "brush"
