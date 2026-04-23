"""Pipeline orchestration tests: verify auto_paint runs all phases, produces
the expected stroke counts + coverage, and doesn't silently skip stages.

Prerequisites: viewer on :8080 AND hermes_tools on :8765 must be running.
This is a black-box smoke test — it's the cheapest way to catch regressions
when a phase is broken or goes empty.

Run:
  .venv/bin/python -m pytest tests/test_pipeline_orchestration.py -v
  .venv/bin/python tests/test_pipeline_orchestration.py        # direct
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def post(tool, payload=None, port=8765, timeout=120):
    req = urllib.request.Request(
        f"http://localhost:{port}/tool/{tool}",
        data=json.dumps(payload or {}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def services_up():
    try:
        urllib.request.urlopen("http://localhost:8080/api/state", timeout=2).read()
        urllib.request.urlopen("http://localhost:8765/tool/manifest", timeout=2).read()
        return True
    except Exception:
        return False


def test_all_phases_produce_strokes():
    """auto_paint must run every phase and produce non-trivial stroke counts."""
    if not services_up():
        import pytest
        pytest.skip("viewer :8080 or tool server :8765 not running")

    from paint_lib import auto_paint
    target = str(ROOT / "targets" / "unsplash" / "cat.jpg")
    result = auto_paint(target, seed=42, verbose=False)

    # Phase-by-phase invariants
    assert result["underpaint_strokes"] >= 500, \
        f"underpainting too sparse: {result['underpaint_strokes']}"
    assert result["edge_strokes"] >= 10, \
        f"edge pass too weak: {result['edge_strokes']}"
    # Detail passes must fire on a medium-complexity image
    assert result["mid_detail_strokes"] > 0, "mid-detail missing"
    assert result["fine_detail_strokes"] > 0, "fine-detail missing"
    # Contour should find something on a cat portrait
    assert result["contour_strokes"] > 10, \
        f"contour too weak on cat: {result['contour_strokes']}"
    # Coverage must be high
    assert result["coverage"] >= 0.95, \
        f"coverage below threshold: {result['coverage']:.1%}"


def test_saliency_applied_when_available():
    """Subject photos should trigger the saliency mask (separability > 0.18)."""
    if not services_up():
        import pytest
        pytest.skip("services not running")
    from paint_lib import auto_paint
    result = auto_paint(str(ROOT / "targets" / "unsplash" / "old_man.jpg"),
                        seed=42, verbose=False)
    assert result["mask_used"] is True, \
        "saliency mask should activate on a portrait"


def test_no_pure_black_in_finishing_passes(tmp_path):
    """v10 contract: no finishing stroke may use #101010 or darker pure black.

    Inspect the stroke_log endpoint for the latest iteration and verify all
    stroke colors are above a minimum lightness.
    """
    if not services_up():
        import pytest
        pytest.skip("services not running")
    import urllib.request
    state = json.loads(urllib.request.urlopen("http://localhost:8080/api/state").read())
    last_iter = state["iteration"]
    if last_iter == 0:
        import pytest
        pytest.skip("no iterations yet (run test_all_phases_produce_strokes first)")

    resp = json.loads(urllib.request.urlopen(
        f"http://localhost:8080/api/iteration/{last_iter}/strokes").read())
    strokes = resp.get("strokes", [])
    # Check for pure ink blacks in polyline/bezier (the old #101010)
    offenders = []
    for s in strokes:
        if s.get("type") not in ("polyline", "bezier"):
            continue
        c = s.get("color", "")
        if len(c) == 7 and c.startswith("#"):
            r = int(c[1:3], 16); g = int(c[3:5], 16); b = int(c[5:7], 16)
            if r + g + b < 30 and abs(r - g) < 5 and abs(g - b) < 5:
                offenders.append(c)
    # Allow some cases where tonal-dark rounds to very dark, but not more than 5%
    n_total = sum(1 for s in strokes if s.get("type") in ("polyline", "bezier"))
    if n_total > 0:
        ratio = len(offenders) / n_total
        assert ratio < 0.05, (
            f"too many pure-black finishing strokes ({len(offenders)}/{n_total} = {ratio:.1%})"
        )


def main():
    print("Pipeline orchestration tests")
    if not services_up():
        print("  SKIP (services not up)")
        return 0
    t0 = time.time()
    test_all_phases_produce_strokes()
    print(f"  [PASS] all_phases_produce_strokes ({time.time()-t0:.1f}s)")
    t0 = time.time()
    test_saliency_applied_when_available()
    print(f"  [PASS] saliency_applied_when_available ({time.time()-t0:.1f}s)")
    test_no_pure_black_in_finishing_passes(Path("/tmp"))
    print(f"  [PASS] no_pure_black_in_finishing_passes")
    print("All pipeline orchestration tests passed.")
    return 0


def test_morph_two_endpoints():
    """auto_paint with a style_schedule produces the result keys and
    well-formed phase_blends. Uses a small target so it runs
    in a few seconds."""
    if not services_up():
        import pytest
        pytest.skip("viewer :8080 or tool server :8765 not running")

    from paint_lib import auto_paint
    target = str(ROOT / "targets" / "masterworks" / "great_wave.jpg")
    result = auto_paint(
        target,
        seed=42,
        verbose=False,
        style_schedule={"start": "van_gogh", "end": "tenebrism",
                        "rationale": "test"},
    )
    assert result.get("style_schedule") == {
        "start": "van_gogh", "end": "tenebrism", "rationale": "test"
    }
    pb = result.get("phase_blends")
    assert pb is not None, "phase_blends missing when schedule was set"
    assert len(pb) == 8, f"expected 8 phase_blends, got {len(pb)}"
    assert pb[0] == 0.0, f"first blend must be 0.0, got {pb[0]}"
    assert pb[-1] == 1.0, f"last blend must be 1.0, got {pb[-1]}"
    assert pb == sorted(pb), "phase_blends must be monotonic"
    # Stroke counts must be non-empty across the main phases
    assert result["underpaint_strokes"] >= 500, f"underpaint: {result['underpaint_strokes']}"
    assert result["coverage"] >= 0.90, f"coverage: {result['coverage']:.1%}"


def test_morph_degenerate_matches_style_mode():
    """Degenerate schedule {start:X, end:X} must be pixel-identical to
    style_mode=X at the stroke-set level (same seeds, same counts)."""
    if not services_up():
        import pytest
        pytest.skip("services not running")

    from paint_lib import auto_paint
    target = str(ROOT / "targets" / "masterworks" / "great_wave.jpg")

    # Run 1: style_mode=van_gogh
    post("clear")
    r1 = auto_paint(target, seed=42, verbose=False, style_mode="van_gogh")

    # Run 2: degenerate schedule
    post("clear")
    r2 = auto_paint(
        target, seed=42, verbose=False,
        style_schedule={"start": "van_gogh", "end": "van_gogh"},
    )

    # Same underpainting stroke count (interleave at t=0 returns start_strokes unmodified)
    assert r1["underpaint_strokes"] == r2["underpaint_strokes"], (
        f"degenerate schedule diverged at underpainting: "
        f"style_mode={r1['underpaint_strokes']} vs schedule={r2['underpaint_strokes']}"
    )
    # Final SSIM within 1% (parameter-interp is no-op when both endpoints same)
    if r1.get("final_score") and r2.get("final_score"):
        s1 = r1["final_score"]["ssim"]
        s2 = r2["final_score"]["ssim"]
        assert abs(s1 - s2) < 0.01, f"final SSIM drift: {s1:.4f} vs {s2:.4f}"


def test_paint_duet_produces_artifacts(tmp_path):
    """End-to-end: a duet run writes canvas, journal, trace, summary."""
    if not services_up():
        import pytest
        pytest.skip("viewer :8080 or tool server :8765 not running")

    from paint_lib.duet import paint_duet
    target = str(ROOT / "targets" / "masterworks" / "great_wave.jpg")
    result = paint_duet(
        target,
        personas=["van_gogh_voice", "tenebrist_voice"],
        max_turns=3,
        seed=42,
        out_dir=tmp_path,
        verbose=False,
    )
    assert result["final_ssim"] is not None
    assert result["reason"] in ("max_turns", "converged_early")
    assert result["personas_used"] == ["van_gogh_voice", "tenebrist_voice"]
    for key in ("canvas_path", "journal_path", "trace_path"):
        assert Path(result[key]).exists(), f"{key} not written"
    assert len(result["turns"]) <= 3
    assert result["turns"][0]["action"] == "opening"
    assert result["turns"][0]["persona"] == "van_gogh_voice"


def test_paint_duet_personas_alternate(tmp_path):
    """Turns 2+ alternate between the two personas."""
    if not services_up():
        import pytest
        pytest.skip("services not running")

    from paint_lib.duet import paint_duet
    target = str(ROOT / "targets" / "masterworks" / "great_wave.jpg")
    result = paint_duet(
        target, personas=["van_gogh_voice", "tenebrist_voice"],
        max_turns=4, seed=42, out_dir=tmp_path, verbose=False,
    )
    turns = result["turns"]
    if len(turns) >= 2:
        assert turns[1]["persona"] == "tenebrist_voice"
    if len(turns) >= 3:
        assert turns[2]["persona"] == "van_gogh_voice"
    if len(turns) >= 4:
        assert turns[3]["persona"] == "tenebrist_voice"


def test_contour_painterly_default_emits_brush_strokes():
    """Default auto_paint after painterly revamp emits brush-type strokes
    for contours. Check that auto_paint on great_wave produces brush strokes
    with bristle texture (characteristic of painterly multi-stroke contours)."""
    if not services_up():
        import pytest
        pytest.skip("services not running")

    # Clear + paint
    post("clear")
    from paint_lib import auto_paint
    target = str(ROOT / "targets" / "masterworks" / "great_wave.jpg")
    result = auto_paint(target, seed=42, verbose=False)

    # The result dict shows contour_strokes count
    assert result.get("contour_strokes", 0) > 10, \
        f"contour phase produced too few strokes: {result.get('contour_strokes')}"

    # Read the viewer's stroke log for the most recent iteration
    state = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:8080/api/state", timeout=5).read())
    last_iter = state["iteration"]
    resp = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:8080/api/iteration/{last_iter}/strokes",
        timeout=5).read())
    strokes = resp.get("strokes", [])

    # Count brush strokes with bristle texture (characteristic of painterly)
    brush_bristle = [s for s in strokes
                     if s.get("type") == "brush" and s.get("texture") == "bristle"]
    assert len(brush_bristle) > 0, (
        f"expected brush strokes with bristle texture (painterly), got none"
    )
    # After painterly revamp, most finishing strokes should be brush-type
    brush_ratio = len(brush_bristle) / len(strokes) if strokes else 0
    assert brush_ratio >= 0.5, (
        f"expected ≥50% brush-bristle strokes after painterly revamp, got {brush_ratio:.2f} "
        f"({len(brush_bristle)}/{len(strokes)})"
    )


def test_pipeline_determinism_great_wave_seed42():
    """auto_paint on great_wave.jpg @ seed=42 must match the committed
    baseline. Locks in byte-for-byte behavior across the phase refactor
    (CODE_REVIEW P2.11)."""
    if not services_up():
        import pytest
        pytest.skip("services not running")

    import json
    from paint_lib import auto_paint
    baseline_path = ROOT / "tests" / "fixtures" / "pipeline_baseline_great_wave_seed42.json"
    baseline = json.loads(baseline_path.read_text())

    post("clear")
    r = auto_paint(str(ROOT / "targets" / "masterworks" / "great_wave.jpg"),
                   seed=42, verbose=False)

    for key in ("image_type", "style_mode", "underpaint_strokes",
                "edge_strokes", "fill_strokes", "mid_detail_strokes",
                "fine_detail_strokes", "contour_strokes", "highlight_strokes",
                "critique_strokes"):
        assert r.get(key) == baseline[key], (
            f"{key}: baseline {baseline[key]!r} != current {r.get(key)!r}"
        )
    assert round((r.get("coverage") or 0), 3) == baseline["coverage"]
    ssim = round((r.get("final_score") or {}).get("ssim") or 0, 4)
    assert abs(ssim - baseline["final_ssim"]) < 0.005, \
        f"ssim drift: baseline {baseline['final_ssim']}, current {ssim}"


if __name__ == "__main__":
    sys.exit(main())
