"""Invariant: every handler in TOOLS has a matching MANIFEST entry and vice versa.

Catches the common mistake of adding a handler without registering it
(or registering a manifest entry whose name doesn't match the dict key).
"""
from __future__ import annotations


def test_tools_and_manifest_synced():
    from painter.tools import TOOLS, MANIFEST
    tools_names = set(TOOLS.keys())
    manifest_names = {m["name"] for m in MANIFEST}
    missing_in_manifest = tools_names - manifest_names
    missing_in_tools = manifest_names - tools_names
    assert not missing_in_manifest, (
        f"handlers without manifest entries: {sorted(missing_in_manifest)}"
    )
    assert not missing_in_tools, (
        f"manifest entries without handlers: {sorted(missing_in_tools)}"
    )
    assert len(TOOLS) == len(MANIFEST), (
        f"TOOLS ({len(TOOLS)}) and MANIFEST ({len(MANIFEST)}) have different counts"
    )


def test_manifest_entries_have_required_fields():
    from painter.tools import MANIFEST
    for entry in MANIFEST:
        assert "name" in entry, f"manifest entry missing 'name': {entry}"
        assert "input" in entry, f"{entry['name']}: missing 'input'"
        assert "output" in entry, f"{entry['name']}: missing 'output'"
