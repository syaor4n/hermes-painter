"""Tests for community-style loader and list_styles tool.

All tests are pure-Python / filesystem; no viewer services required.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

# Ensure scripts/ and src/ are on the path so paint_lib and painter are importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from paint_lib import morph


# ---------------------------------------------------------------------------
# 1. lumiere_doree loads and is present in STYLE_DEFAULTS
# ---------------------------------------------------------------------------

def test_lumiere_doree_in_style_defaults():
    assert "lumiere_doree" in morph.STYLE_DEFAULTS, (
        "lumiere_doree should be loaded from styles/lumiere_doree/style.yaml"
    )


def test_lumiere_doree_params_have_all_keys():
    required = {
        "contrast_boost",
        "complementary_shadow",
        "painterly_details_bias",
        "van_gogh_bias",
        "tenebrism_bias",
        "pointillism_bias",
        "engraving_bias",
    }
    params = morph.STYLE_DEFAULTS["lumiere_doree"]
    assert required == set(params.keys()), f"unexpected keys: {set(params)}"


def test_lumiere_doree_param_values():
    params = morph.STYLE_DEFAULTS["lumiere_doree"]
    assert params["contrast_boost"] == pytest.approx(0.28)
    assert params["complementary_shadow"] == pytest.approx(0.15)
    assert params["painterly_details_bias"] == pytest.approx(0.5)
    assert params["van_gogh_bias"] == pytest.approx(0.2)
    assert params["tenebrism_bias"] == pytest.approx(0.0)
    assert params["pointillism_bias"] == pytest.approx(0.0)
    assert params["engraving_bias"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 2. STYLE_DISPATCH["lumiere_doree"] is the same callable as STYLE_DISPATCH["default"]
# ---------------------------------------------------------------------------

def test_lumiere_doree_dispatch_inherits_default():
    assert "lumiere_doree" in morph.STYLE_DISPATCH, (
        "lumiere_doree should be registered in STYLE_DISPATCH"
    )
    assert morph.STYLE_DISPATCH["lumiere_doree"] is morph.STYLE_DISPATCH["default"], (
        "lumiere_doree extends default, so its generator must be the same callable"
    )


# ---------------------------------------------------------------------------
# 3. validate_schedule accepts lumiere_doree
# ---------------------------------------------------------------------------

def test_validate_schedule_accepts_lumiere_doree_as_start():
    morph.validate_schedule({"start": "lumiere_doree", "end": "tenebrism"})


def test_validate_schedule_accepts_lumiere_doree_as_end():
    morph.validate_schedule({"start": "default", "end": "lumiere_doree"})


def test_validate_schedule_accepts_lumiere_doree_to_lumiere_doree():
    morph.validate_schedule({"start": "lumiere_doree", "end": "lumiere_doree"})


# ---------------------------------------------------------------------------
# 4. blend_params works with lumiere_doree
# ---------------------------------------------------------------------------

def test_blend_params_lumiere_doree_tenebrism():
    out = morph.blend_params("lumiere_doree", "tenebrism", 0.5)
    A = morph.STYLE_DEFAULTS["lumiere_doree"]
    B = morph.STYLE_DEFAULTS["tenebrism"]
    for k in set(A) | set(B):
        expected = 0.5 * A.get(k, 0.0) + 0.5 * B.get(k, 0.0)
        assert out[k] == pytest.approx(expected, abs=0.01), (
            f"blend midpoint wrong for {k}: expected {expected}, got {out[k]}"
        )


def test_blend_params_lumiere_doree_t0_returns_params():
    out = morph.blend_params("lumiere_doree", "tenebrism", 0.0)
    for k, v in morph.STYLE_DEFAULTS["lumiere_doree"].items():
        assert out[k] == pytest.approx(v), f"{k} at t=0 should equal lumiere_doree params"


# ---------------------------------------------------------------------------
# 5. list_styles tool returns lumiere_doree with kind="community" + extends="default"
# ---------------------------------------------------------------------------

def test_list_styles_includes_lumiere_doree():
    from painter.tools.analyze import tool_list_styles
    result = tool_list_styles({})
    assert "styles" in result
    names = {s["name"] for s in result["styles"]}
    assert "lumiere_doree" in names, f"lumiere_doree not in list_styles: {names}"


def test_list_styles_lumiere_doree_kind_and_extends():
    from painter.tools.analyze import tool_list_styles
    result = tool_list_styles({})
    entry = next(s for s in result["styles"] if s["name"] == "lumiere_doree")
    assert entry["kind"] == "community", f"expected kind=community, got {entry['kind']}"
    assert entry["extends"] == "default", f"expected extends=default, got {entry.get('extends')}"


def test_list_styles_includes_all_builtins():
    from painter.tools.analyze import tool_list_styles
    result = tool_list_styles({})
    names = {s["name"] for s in result["styles"]}
    for builtin in ("default", "van_gogh", "tenebrism", "pointillism", "engraving"):
        assert builtin in names, f"builtin {builtin!r} missing from list_styles"


def test_list_styles_builtin_kind_field():
    from painter.tools.analyze import tool_list_styles
    result = tool_list_styles({})
    for entry in result["styles"]:
        if entry["name"] in ("default", "van_gogh", "tenebrism", "pointillism", "engraving"):
            assert entry["kind"] == "builtin", (
                f"{entry['name']} should be kind=builtin, got {entry['kind']}"
            )


def test_list_styles_total_matches_style_defaults():
    from painter.tools.analyze import tool_list_styles
    result = tool_list_styles({})
    assert result["total"] == len(morph.STYLE_DEFAULTS)
    assert result["total"] == len(result["styles"])


# ---------------------------------------------------------------------------
# 6. Malformed style.yaml is skipped with a warning (tmp_path fixture)
# ---------------------------------------------------------------------------

def _reload_morph_with_extra_dir(extra_dir: Path) -> "types.ModuleType":
    """Reload the morph module with STYLES_PATH pointing at extra_dir."""
    import os
    import importlib
    old_env = os.environ.get("STYLES_PATH")
    os.environ["STYLES_PATH"] = str(extra_dir)
    try:
        # Remove cached module so _load_community_styles runs fresh
        for key in list(sys.modules.keys()):
            if "paint_lib" in key:
                del sys.modules[key]
        import paint_lib.morph as fresh
        return fresh
    finally:
        if old_env is None:
            os.environ.pop("STYLES_PATH", None)
        else:
            os.environ["STYLES_PATH"] = old_env
        # Restore the cached module for other tests
        for key in list(sys.modules.keys()):
            if "paint_lib" in key:
                del sys.modules[key]
        import paint_lib.morph  # noqa: F401 — repopulate cache


def test_malformed_bad_format_version_is_skipped(tmp_path, capsys):
    """A style.yaml with wrong format_version emits a warning and is skipped."""
    style_dir = tmp_path / "bad_version"
    style_dir.mkdir()
    (style_dir / "style.yaml").write_text(textwrap.dedent("""\
        format_version: 99
        name: bad_version_style
        extends: default
        parameters:
          contrast_boost: 0.1
          complementary_shadow: 0.1
          painterly_details_bias: 0.0
          van_gogh_bias: 0.0
          tenebrism_bias: 0.0
          pointillism_bias: 0.0
          engraving_bias: 0.0
    """))
    fresh = _reload_morph_with_extra_dir(tmp_path)
    captured = capsys.readouterr()
    assert "bad_version_style" not in fresh.STYLE_DEFAULTS
    assert "[morph]" in captured.err


def test_malformed_missing_parameter_key_is_skipped(tmp_path, capsys):
    """A style.yaml missing a required parameter key emits a warning and is skipped."""
    style_dir = tmp_path / "missing_param"
    style_dir.mkdir()
    (style_dir / "style.yaml").write_text(textwrap.dedent("""\
        format_version: 1
        name: missing_param_style
        extends: default
        parameters:
          contrast_boost: 0.1
          complementary_shadow: 0.1
          painterly_details_bias: 0.0
          van_gogh_bias: 0.0
          tenebrism_bias: 0.0
          pointillism_bias: 0.0
    """))  # engraving_bias is missing
    fresh = _reload_morph_with_extra_dir(tmp_path)
    captured = capsys.readouterr()
    assert "missing_param_style" not in fresh.STYLE_DEFAULTS
    assert "[morph]" in captured.err


def test_malformed_unknown_extends_is_skipped(tmp_path, capsys):
    """A style.yaml with an unknown extends value emits a warning and is skipped."""
    style_dir = tmp_path / "bad_extends"
    style_dir.mkdir()
    (style_dir / "style.yaml").write_text(textwrap.dedent("""\
        format_version: 1
        name: bad_extends_style
        extends: nonexistent_builtin
        parameters:
          contrast_boost: 0.1
          complementary_shadow: 0.1
          painterly_details_bias: 0.0
          van_gogh_bias: 0.0
          tenebrism_bias: 0.0
          pointillism_bias: 0.0
          engraving_bias: 0.0
    """))
    fresh = _reload_morph_with_extra_dir(tmp_path)
    captured = capsys.readouterr()
    assert "bad_extends_style" not in fresh.STYLE_DEFAULTS
    assert "[morph]" in captured.err


def test_valid_community_style_from_styles_path_is_loaded(tmp_path):
    """A well-formed style.yaml in STYLES_PATH is registered correctly."""
    style_dir = tmp_path / "golden_dusk"
    style_dir.mkdir()
    (style_dir / "style.yaml").write_text(textwrap.dedent("""\
        format_version: 1
        name: golden_dusk
        author: test-author
        license: CC0-1.0
        extends: van_gogh
        parameters:
          contrast_boost: 0.30
          complementary_shadow: 0.10
          painterly_details_bias: 0.7
          van_gogh_bias: 0.9
          tenebrism_bias: 0.0
          pointillism_bias: 0.0
          engraving_bias: 0.0
    """))
    fresh = _reload_morph_with_extra_dir(tmp_path)
    assert "golden_dusk" in fresh.STYLE_DEFAULTS
    assert fresh.STYLE_DISPATCH["golden_dusk"] is fresh.STYLE_DISPATCH["van_gogh"]


def test_builtin_cannot_be_overwritten_by_community(tmp_path, capsys):
    """A community style.yaml that tries to shadow a built-in name is rejected."""
    style_dir = tmp_path / "van_gogh"
    style_dir.mkdir()
    (style_dir / "style.yaml").write_text(textwrap.dedent("""\
        format_version: 1
        name: van_gogh
        extends: default
        parameters:
          contrast_boost: 0.99
          complementary_shadow: 0.0
          painterly_details_bias: 0.0
          van_gogh_bias: 0.0
          tenebrism_bias: 0.0
          pointillism_bias: 0.0
          engraving_bias: 0.0
    """))
    original_params = dict(morph.STYLE_DEFAULTS["van_gogh"])
    fresh = _reload_morph_with_extra_dir(tmp_path)
    # Built-in params must not be replaced
    assert fresh.STYLE_DEFAULTS["van_gogh"]["contrast_boost"] != pytest.approx(0.99)
    captured = capsys.readouterr()
    assert "[morph]" in captured.err
