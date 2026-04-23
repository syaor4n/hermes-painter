"""Tests for the hand-written YAML-subset frontmatter parser in painter.skills.

Catches regressions in the parser that would silently mis-classify skills
or drop their dimensional_effects.
"""
from __future__ import annotations
import pytest


def test_parse_empty_frontmatter():
    from painter.skills import _parse_frontmatter
    meta, body = _parse_frontmatter("")
    assert meta == {}
    assert body == ""


def test_parse_no_frontmatter():
    from painter.skills import _parse_frontmatter
    meta, body = _parse_frontmatter("just a body\nwith two lines\n")
    assert meta == {}
    assert body.startswith("just a body")


def test_parse_flat_scalars():
    from painter.skills import _parse_frontmatter
    text = """---
name: test_skill
confidence: 3
weight: 0.75
---
body here"""
    meta, body = _parse_frontmatter(text)
    assert meta["name"] == "test_skill"
    assert meta["confidence"] == 3
    assert meta["weight"] == 0.75
    assert "body here" in body


def test_parse_list_inline():
    from painter.skills import _parse_frontmatter
    text = """---
tags: [warm, sunset, dramatic]
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["tags"] == ["warm", "sunset", "dramatic"]


def test_parse_nested_dict():
    from painter.skills import _parse_frontmatter
    text = """---
scope:
  image_types: [portrait, landscape]
  exclude: [night]
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["scope"]["image_types"] == ["portrait", "landscape"]
    assert meta["scope"]["exclude"] == ["night"]


def test_parse_dimensional_effects():
    """The P0.1 feedback loop depends on this parse being correct."""
    from painter.skills import _parse_frontmatter
    text = """---
dimensional_effects:
  contrast_boost: 0.1
  van_gogh_bias: 0.4
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["dimensional_effects"]["contrast_boost"] == 0.1
    assert meta["dimensional_effects"]["van_gogh_bias"] == 0.4


def test_parse_booleans_and_null():
    from painter.skills import _parse_frontmatter
    text = """---
enabled: true
verified: false
fallback: null
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["enabled"] is True
    assert meta["verified"] is False
    assert meta["fallback"] is None


def test_parse_quoted_strings():
    from painter.skills import _parse_frontmatter
    text = """---
name: "quoted name"
other: 'single quoted'
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["name"] == "quoted name"
    assert meta["other"] == "single quoted"


def test_parse_handles_comments_and_blanks():
    from painter.skills import _parse_frontmatter
    text = """---
# top-level comment
name: test

confidence: 2
---
body"""
    meta, _ = _parse_frontmatter(text)
    assert meta["name"] == "test"
    assert meta["confidence"] == 2


def test_parse_unclosed_frontmatter_degrades():
    """If the closing --- is missing, treat the whole thing as body.
    Don't raise (some skills may have legitimate --- in the body)."""
    from painter.skills import _parse_frontmatter
    text = """---
name: test
no closing marker"""
    meta, body = _parse_frontmatter(text)
    assert meta == {}  # couldn't parse, but degraded gracefully
