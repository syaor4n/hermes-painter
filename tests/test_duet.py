"""Unit tests for paint_lib.duet — pure functions + registry, no services."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from paint_lib import duet


def test_shipped_personas_load():
    """The three YAMLs in personas/ must populate the registry at import."""
    assert "van_gogh_voice" in duet.PERSONAS
    assert "tenebrist_voice" in duet.PERSONAS
    assert "pointillist_voice" in duet.PERSONAS


def test_persona_fields_populated():
    p = duet.PERSONAS["van_gogh_voice"]
    assert p.name == "van_gogh_voice"
    assert p.style_mode == "van_gogh"
    assert "expressive" in p.skills_tags
    assert p.cares_about["MUDDY_UNDERPAINT"] == 1.0
    assert p.correction_budget["max_cells_per_turn"] == 6


def test_persona_defaults_applied(tmp_path):
    """A minimum-viable persona YAML loads with schema defaults."""
    d = tmp_path / "minimalist_voice"
    d.mkdir()
    (d / "persona.yaml").write_text(
        "format_version: 1\nname: minimalist_voice\nstyle_mode: default\n"
    )
    p = duet._validate_persona_file(d / "persona.yaml")
    assert p is not None
    assert p.name == "minimalist_voice"
    assert p.correction_budget["max_cells_per_turn"] == 6  # default
    assert p.correction_budget["stroke_width"] == 3
    assert p.correction_budget["alpha"] == 0.55


def test_persona_rejects_unknown_style_mode(tmp_path, capsys):
    d = tmp_path / "bogus_voice"
    d.mkdir()
    (d / "persona.yaml").write_text(
        "format_version: 1\nname: bogus_voice\nstyle_mode: totally_fake\n"
    )
    result = duet._validate_persona_file(d / "persona.yaml")
    assert result is None
    err = capsys.readouterr().err
    assert "bogus_voice" in err


def test_persona_rejects_unknown_failure_mode(tmp_path, capsys):
    d = tmp_path / "weird_voice"
    d.mkdir()
    (d / "persona.yaml").write_text(
        "format_version: 1\n"
        "name: weird_voice\n"
        "style_mode: default\n"
        "cares_about:\n"
        "  NOT_A_REAL_MODE: 1.0\n"
    )
    assert duet._validate_persona_file(d / "persona.yaml") is None


def test_persona_clamps_out_of_range_weights(tmp_path, capsys):
    d = tmp_path / "shouty_voice"
    d.mkdir()
    (d / "persona.yaml").write_text(
        "format_version: 1\n"
        "name: shouty_voice\n"
        "style_mode: default\n"
        "cares_about:\n"
        "  MUDDY_UNDERPAINT: 5.0\n"
    )
    p = duet._validate_persona_file(d / "persona.yaml")
    assert p is not None
    assert p.cares_about["MUDDY_UNDERPAINT"] == 2.0  # clamped


def test_persona_builtin_collision_rejected(tmp_path, capsys):
    """A community YAML with a shipped persona's name must not shadow it."""
    d = tmp_path / "van_gogh_voice"
    d.mkdir()
    (d / "persona.yaml").write_text(
        "format_version: 1\nname: van_gogh_voice\nstyle_mode: tenebrism\n"
    )
    # Simulate loader — built-ins have already populated the registry
    duet._register_persona_from_file(d / "persona.yaml", override_existing=False)
    # The original persona stays
    assert duet.PERSONAS["van_gogh_voice"].style_mode == "van_gogh"


def test_style_affinity_van_gogh_prefers_warm():
    warm_rgb = [230, 140, 60]
    cool_rgb = [60, 80, 180]
    from paint_lib.duet import _style_affinity
    assert _style_affinity(warm_rgb, "van_gogh") > _style_affinity(cool_rgb, "van_gogh")


def test_style_affinity_tenebrism_prefers_extremes():
    very_dark = [15, 15, 20]
    midtone = [128, 128, 128]
    very_light = [240, 235, 225]
    from paint_lib.duet import _style_affinity
    assert _style_affinity(very_dark, "tenebrism") > _style_affinity(midtone, "tenebrism")
    assert _style_affinity(very_light, "tenebrism") > _style_affinity(midtone, "tenebrism")


def test_style_affinity_engraving_prefers_grayscale():
    gray = [100, 100, 100]
    saturated = [200, 50, 50]
    from paint_lib.duet import _style_affinity
    assert _style_affinity(gray, "engraving") > _style_affinity(saturated, "engraving")


def test_style_affinity_default_is_neutral():
    from paint_lib.duet import _style_affinity
    assert _style_affinity([200, 100, 50], "default") == 0.5
    assert _style_affinity([50, 50, 200], "default") == 0.5


def test_pick_cells_respects_avoid_set():
    from paint_lib.duet import _pick_cells_by_affinity, PERSONAS
    regions = [
        {"x": 0, "y": 0, "w": 64, "h": 64, "error": 0.5,
         "target_rgb": [230, 140, 60], "current_rgb": [255, 255, 255]},
        {"x": 64, "y": 0, "w": 64, "h": 64, "error": 0.4,
         "target_rgb": [200, 120, 50], "current_rgb": [255, 255, 255]},
    ]
    avoid = {(0, 0)}
    picked = _pick_cells_by_affinity(regions, PERSONAS["van_gogh_voice"], avoid, budget=2)
    assert len(picked) == 1
    assert picked[0]["x"] == 64


def test_pick_cells_mutates_avoid():
    from paint_lib.duet import _pick_cells_by_affinity, PERSONAS
    regions = [{"x": 0, "y": 0, "w": 64, "h": 64, "error": 0.5,
                "target_rgb": [230, 140, 60], "current_rgb": [255, 255, 255]}]
    avoid: set = set()
    _pick_cells_by_affinity(regions, PERSONAS["van_gogh_voice"], avoid, budget=1)
    assert (0, 0) in avoid, "picked cells must be added to avoid set"


def test_pick_cells_returns_empty_when_budget_zero():
    from paint_lib.duet import _pick_cells_by_affinity, PERSONAS
    regions = [{"x": 0, "y": 0, "w": 64, "h": 64, "error": 0.5,
                "target_rgb": [230, 140, 60], "current_rgb": [255, 255, 255]}]
    picked = _pick_cells_by_affinity(regions, PERSONAS["van_gogh_voice"], set(), budget=0)
    assert picked == []


def test_turn_opening_packages_result(tmp_path, monkeypatch):
    """_turn_opening calls auto_paint, snapshots, dumps canvas."""
    from paint_lib import core, duet

    calls = {"auto_paint": 0, "posts": []}
    def fake_auto_paint(target, **kwargs):
        calls["auto_paint"] += 1
        return {"final_score": {"ssim": 0.42}, "underpaint_strokes": 1728,
                "edge_strokes": 80, "mid_detail_strokes": 100,
                "fine_detail_strokes": 50, "contour_strokes": 20,
                "highlight_strokes": 10}
    monkeypatch.setattr(duet, "_auto_paint", fake_auto_paint)

    # _copy_canvas now reads the canvas from /api/state via
    # paint_lib.core._read_canvas_bytes (no more /tmp side channel).
    from io import BytesIO

    from PIL import Image
    def fake_read_canvas_bytes():
        buf = BytesIO()
        Image.new("RGB", (512, 512), (255, 0, 0)).save(buf, format="PNG")
        return buf.getvalue()
    monkeypatch.setattr(core, "_read_canvas_bytes", fake_read_canvas_bytes)

    def fake_post(tool, payload=None):
        calls["posts"].append((tool, payload))
        if tool == "snapshot":
            return {"id": "snap-1"}
        return {}
    monkeypatch.setattr(duet, "_post", fake_post)

    persona = duet.PERSONAS["van_gogh_voice"]
    tr = duet._turn_opening("targets/t.jpg", persona, seed=42,
                             out_dir=tmp_path, verbose=False)

    assert tr.turn == 1
    assert tr.persona == "van_gogh_voice"
    assert tr.action == "opening"
    assert tr.ssim == 0.42
    assert tr.n_strokes == 1728 + 80 + 100 + 50 + 20 + 10
    assert tr.snapshot_id == "snap-1"
    assert (tmp_path / "turn_01_van_gogh_voice.png").exists()
    assert calls["auto_paint"] == 1


def test_turn_correction_passes_when_no_cells(tmp_path, monkeypatch):
    from paint_lib import duet

    def fake_post(tool, payload=None):
        if tool == "critique_canvas":
            return {"findings": [], "verdict": "ok"}
        if tool == "get_regions":
            return {"regions": []}
        if tool == "snapshot":
            return {"id": "snap-x"}
        return {}
    monkeypatch.setattr(duet, "_post", fake_post)
    monkeypatch.setattr(duet, "_current_ssim", lambda *a, **k: 0.5)

    persona = duet.PERSONAS["van_gogh_voice"]
    tr = duet._turn_correction("targets/t.jpg", persona, avoid=set(),
                                turn_index=2, seed=42, out_dir=tmp_path,
                                verbose=False)
    assert tr.action == "pass"
    assert tr.n_strokes == 0
    assert tr.cells_painted == []


def test_turn_correction_rejects_on_regression(tmp_path, monkeypatch):
    from paint_lib import duet

    ssim_sequence = iter([0.5, 0.3])  # pre=0.5, post=0.3 → reject
    regions = [{"x": 0, "y": 0, "w": 64, "h": 64, "error": 0.5,
                "target_rgb": [230, 140, 60], "current_rgb": [0, 0, 0]}]
    restore_calls = []

    def fake_post(tool, payload=None):
        if tool == "critique_canvas":
            return {"findings": [], "verdict": "warn"}
        if tool == "get_regions":
            return {"regions": regions}
        if tool == "snapshot":
            return {"id": "snap-pre"}
        if tool == "sculpt_correction_plan":
            return {"strokes": [{"type": "dab", "x": 10, "y": 10, "w": 4, "h": 4,
                                 "color": "#888888"}]}
        if tool == "draw_strokes":
            return {}
        if tool == "restore":
            restore_calls.append(payload)
            return {"ok": True}
        if tool == "dump_canvas":
            from PIL import Image
            Image.new("RGB", (512, 512), (0, 0, 0)).save("/tmp/painter_canvas.png")
            return {"path": "/tmp/painter_canvas.png"}
        return {}
    monkeypatch.setattr(duet, "_post", fake_post)
    monkeypatch.setattr(duet, "_current_ssim", lambda *a, **k: next(ssim_sequence))

    persona = duet.PERSONAS["van_gogh_voice"]
    tr = duet._turn_correction("targets/t.jpg", persona, avoid=set(),
                                turn_index=2, seed=42, out_dir=tmp_path,
                                verbose=False)
    assert tr.action == "reject"
    assert tr.rejected_reason == "ssim_regressed"
    assert len(restore_calls) == 1
    assert restore_calls[0] == {"id": "snap-pre"}


def test_paint_duet_validates_personas_upfront(tmp_path, monkeypatch):
    from paint_lib import duet
    with pytest.raises(ValueError, match="unknown persona"):
        duet.paint_duet("targets/masterworks/great_wave.jpg",
                        personas=["not_a_persona"],
                        out_dir=tmp_path)


def test_paint_duet_requires_exactly_two_personas(tmp_path):
    from paint_lib import duet
    with pytest.raises(ValueError, match="exactly 2"):
        duet.paint_duet("targets/masterworks/great_wave.jpg",
                        personas=["van_gogh_voice"],
                        out_dir=tmp_path)


def test_paint_duet_clamps_max_turns(tmp_path, monkeypatch):
    """max_turns=100 must clamp to 20 — then short-circuit before real painting."""
    from paint_lib import duet
    seen = {}
    def boom(*a, **k):
        seen["called"] = True
        raise RuntimeError("stop here")
    monkeypatch.setattr(duet, "_turn_opening", lambda *a, **k: boom())
    with pytest.raises(RuntimeError, match="stop here"):
        duet.paint_duet("targets/masterworks/great_wave.jpg",
                        max_turns=100, out_dir=tmp_path)
    assert seen.get("called")


def test_write_journal_format(tmp_path):
    from paint_lib.duet import _write_journal, TurnResult
    turns = [
        TurnResult(turn=1, persona="A", action="opening",
                   ssim=0.25, n_strokes=1000, cells_painted=[],
                   findings=None, snapshot_id="s1"),
        TurnResult(turn=2, persona="B", action="correct",
                   ssim=0.28, n_strokes=120, cells_painted=[(1, 2), (3, 4)],
                   findings=[{"mode": "MUDDY_UNDERPAINT", "severity": 2, "weight": 1.0}],
                   snapshot_id="s2"),
    ]
    path = tmp_path / "duet_journal.md"
    _write_journal(path, "targets/t.jpg", ["A", "B"], turns,
                    reason="max_turns", max_turns=6)
    text = path.read_text()
    assert "# Duet" in text
    assert "Turn 1 — A · opening" in text
    assert "Turn 2 — B · correct" in text
    assert "MUDDY_UNDERPAINT" in text
    assert "0.250" in text


def test_tool_list_personas_returns_shipped():
    from painter.tools.duet_tool import tool_list_personas
    out = tool_list_personas({})
    assert "personas" in out
    names = {p["name"] for p in out["personas"]}
    assert {"van_gogh_voice", "tenebrist_voice", "pointillist_voice"} <= names
    for p in out["personas"]:
        assert set(p) >= {"name", "style_mode", "description", "kind", "source_path"}


def test_tool_paint_duet_rejects_unknown_persona():
    from painter.tools.duet_tool import tool_paint_duet
    out = tool_paint_duet({
        "target": "targets/masterworks/great_wave.jpg",
        "personas": ["not_a_real_persona"],
    })
    assert "error" in out
    assert "unknown persona" in out["error"].lower()


def test_tools_manifest_includes_duet_and_list_personas():
    from painter.tools import TOOLS, MANIFEST
    assert "paint_duet" in TOOLS
    assert "list_personas" in TOOLS
    names = {m["name"] for m in MANIFEST}
    assert "paint_duet" in names
    assert "list_personas" in names
    assert len(TOOLS) == len(MANIFEST)
