"""Unit tests for paint_lib.morph — pure functions, no services needed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest

from paint_lib import morph


def test_style_defaults_has_all_builtins():
    for name in ("default", "van_gogh", "tenebrism", "pointillism", "engraving"):
        assert name in morph.STYLE_DEFAULTS, f"{name} missing from STYLE_DEFAULTS"


def test_style_dispatch_has_all_builtins():
    for name in ("default", "van_gogh", "tenebrism", "pointillism", "engraving"):
        assert name in morph.STYLE_DISPATCH, f"{name} missing from STYLE_DISPATCH"


def test_phase_t_has_8_entries_monotonic_0_to_1():
    ts = list(morph.PHASE_T.values())
    assert len(ts) == 8
    assert ts[0] == 0.0
    assert ts[-1] == 1.0
    assert ts == sorted(ts)


def test_validate_schedule_accepts_wellformed():
    morph.validate_schedule({"start": "van_gogh", "end": "tenebrism"})
    morph.validate_schedule({"start": "van_gogh", "end": "tenebrism", "rationale": "x"})


def test_validate_schedule_rejects_unknown_style():
    with pytest.raises(ValueError, match="unknown style"):
        morph.validate_schedule({"start": "van_gogh", "end": "bogus"})
    with pytest.raises(ValueError, match="unknown style"):
        morph.validate_schedule({"start": "bogus", "end": "tenebrism"})


def test_validate_schedule_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing"):
        morph.validate_schedule({"start": "van_gogh"})
    with pytest.raises(ValueError, match="missing"):
        morph.validate_schedule({"end": "tenebrism"})


def test_validate_schedule_rejects_non_dict():
    with pytest.raises(ValueError, match="dict"):
        morph.validate_schedule("van_gogh → tenebrism")


def test_validate_schedule_allows_extra_keys():
    morph.validate_schedule({"start": "van_gogh", "end": "tenebrism",
                             "future_key": "ignored", "rationale": "x"})


def test_blend_params_t0_equals_start():
    out = morph.blend_params("van_gogh", "tenebrism", 0.0)
    for k, v in morph.STYLE_DEFAULTS["van_gogh"].items():
        assert out[k] == pytest.approx(v), f"{k} at t=0 should match start"


def test_blend_params_t1_equals_end():
    out = morph.blend_params("van_gogh", "tenebrism", 1.0)
    for k, v in morph.STYLE_DEFAULTS["tenebrism"].items():
        assert out[k] == pytest.approx(v), f"{k} at t=1 should match end"


def test_blend_params_t_half_is_midpoint():
    out = morph.blend_params("van_gogh", "tenebrism", 0.5)
    A = morph.STYLE_DEFAULTS["van_gogh"]
    B = morph.STYLE_DEFAULTS["tenebrism"]
    for k in A.keys() | B.keys():
        expected = 0.5 * A.get(k, 0.0) + 0.5 * B.get(k, 0.0)
        assert out[k] == pytest.approx(expected, abs=0.01), f"midpoint wrong for {k}"


def test_blend_params_degenerate_same_style():
    out = morph.blend_params("van_gogh", "van_gogh", 0.5)
    for k, v in morph.STYLE_DEFAULTS["van_gogh"].items():
        assert out[k] == pytest.approx(v), f"degenerate case should return start vector at every t"


def test_blend_params_all_values_within_bounds():
    # EFFECT_LIMITS lives in src/painter/skills — verify clamping.
    src_path = Path(__file__).resolve().parent.parent / "src"
    sys.path.insert(0, str(src_path))
    from painter.skills import EFFECT_LIMITS  # noqa: E402
    for start in morph.STYLE_DEFAULTS:
        for end in morph.STYLE_DEFAULTS:
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                out = morph.blend_params(start, end, t)
                for k, v in out.items():
                    if k in EFFECT_LIMITS:
                        lo, hi = EFFECT_LIMITS[k]
                        assert lo <= v <= hi, (
                            f"{start}→{end} @ t={t}: {k}={v} out of [{lo}, {hi}]"
                        )


def test_blend_params_missing_keys_default_to_zero():
    # Simulate partial coverage: one vector has a key the other lacks.
    old_vg = morph.STYLE_DEFAULTS["van_gogh"]
    morph.STYLE_DEFAULTS["van_gogh"] = {**old_vg, "hypothetical_knob": 0.5}
    try:
        out = morph.blend_params("van_gogh", "tenebrism", 0.5)
        assert out["hypothetical_knob"] == pytest.approx(0.25)
    finally:
        morph.STYLE_DEFAULTS["van_gogh"] = old_vg


def _fake_stroke(i: int, source: str) -> dict:
    """Deterministic stroke dict for interleave tests."""
    return {"type": "brush", "points": [[i, i]], "color": f"#{i:06x}",
            "source": source, "idx": i}


def test_interleave_t0_returns_start_strokes_unshuffled():
    start = [_fake_stroke(i, "A") for i in range(10)]
    end = [_fake_stroke(i, "B") for i in range(10)]
    out = morph.interleave_strokes(start, end, 0.0, seed=42)
    assert out == start, "t=0 must preserve start strokes exactly (order + content)"


def test_interleave_t1_returns_end_strokes_unshuffled():
    start = [_fake_stroke(i, "A") for i in range(10)]
    end = [_fake_stroke(i, "B") for i in range(10)]
    out = morph.interleave_strokes(start, end, 1.0, seed=42)
    assert out == end, "t=1 must preserve end strokes exactly"


def test_interleave_t_half_mixes_both_sources():
    start = [_fake_stroke(i, "A") for i in range(100)]
    end = [_fake_stroke(i, "B") for i in range(100)]
    out = morph.interleave_strokes(start, end, 0.5, seed=42)
    sources = {s["source"] for s in out}
    assert sources == {"A", "B"}, f"expected both sources, got {sources}"
    n_a = sum(1 for s in out if s["source"] == "A")
    n_b = sum(1 for s in out if s["source"] == "B")
    assert abs(n_a - n_b) <= 2, f"at t=0.5 counts should be balanced, got A={n_a} B={n_b}"


def test_interleave_same_seed_deterministic():
    start = [_fake_stroke(i, "A") for i in range(50)]
    end = [_fake_stroke(i, "B") for i in range(50)]
    out1 = morph.interleave_strokes(start, end, 0.5, seed=7)
    out2 = morph.interleave_strokes(start, end, 0.5, seed=7)
    assert out1 == out2, "same seed must produce identical output"


def test_interleave_different_seed_different_order():
    start = [_fake_stroke(i, "A") for i in range(50)]
    end = [_fake_stroke(i, "B") for i in range(50)]
    out1 = morph.interleave_strokes(start, end, 0.5, seed=7)
    out2 = morph.interleave_strokes(start, end, 0.5, seed=8)
    assert out1 != out2, "different seeds should produce different shuffle orders"


def test_interleave_weighted_average_budget():
    # Equal-sized inputs case: when both sources have enough strokes,
    # weighted average holds exactly. Test with sufficient counts.
    start = [_fake_stroke(i, "A") for i in range(10000)]
    end = [_fake_stroke(i, "B") for i in range(10000)]
    out = morph.interleave_strokes(start, end, 0.5, seed=0)
    expected = round(0.5 * 10000 + 0.5 * 10000)  # 10000
    assert len(out) == expected, f"expected weighted-avg budget {expected}, got {len(out)}"


def test_interleave_empty_inputs():
    # Defensive: one side empty shouldn't crash.
    out = morph.interleave_strokes([], [_fake_stroke(0, "B")], 1.0, seed=0)
    assert len(out) == 1
    out2 = morph.interleave_strokes([_fake_stroke(0, "A")], [], 0.0, seed=0)
    assert len(out2) == 1

# --- tool handler tests (no viewer services) -----------------------------
# We fake the viewer-dependent analyze_target call by passing
# target_analysis directly.


def _sample_analysis(image_type="balanced", warmth=0.0, saturation=30.0,
                     edge_density=0.08):
    """Mimic the shape of tool_analyze_target's returned dict."""
    return {
        "classification": {
            "type": image_type,
            "warmth": warmth,
            "saturation": saturation,
        },
        "edge_density": edge_density,
    }


def test_plan_style_schedule_returns_primary_and_candidates():
    import sys
    src = Path(__file__).resolve().parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from painter.tools.analyze import tool_plan_style_schedule
    out = tool_plan_style_schedule({
        "target_analysis": _sample_analysis(image_type="high_contrast",
                                             warmth=20.0, edge_density=0.15)
    })
    assert "schedule" in out
    sch = out["schedule"]
    assert set(sch) >= {"start", "end", "rationale"}
    assert sch["start"] in morph.STYLE_DEFAULTS
    assert sch["end"] in morph.STYLE_DEFAULTS
    assert isinstance(sch["rationale"], str) and len(sch["rationale"]) > 0
    assert "candidates" in out
    assert isinstance(out["candidates"], list)
    assert len(out["candidates"]) >= 1
    assert out["candidates"][0]["start"] == sch["start"]
    assert out["candidates"][0]["end"] == sch["end"]


def test_plan_style_schedule_candidates_ranked_desc():
    from painter.tools.analyze import tool_plan_style_schedule
    out = tool_plan_style_schedule({
        "target_analysis": _sample_analysis(image_type="dark")
    })
    scores = [c["score"] for c in out["candidates"]]
    assert scores == sorted(scores, reverse=True), f"candidates not desc: {scores}"


def test_plan_style_schedule_covers_all_image_types():
    from painter.tools.analyze import tool_plan_style_schedule
    for image_type in ("balanced", "high_contrast", "dark", "bright", "muted"):
        out = tool_plan_style_schedule({
            "target_analysis": _sample_analysis(image_type=image_type)
        })
        sch = out["schedule"]
        assert sch["start"] != "" and sch["end"] != "", \
            f"{image_type} returned empty schedule"
        assert sch["rationale"], f"{image_type} returned empty rationale"
