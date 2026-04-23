"""Regression tests for the path allowlist in painter.tools._common.

Prevents CODE_REVIEW P0.2 from recurring: a networked tool layer must
not be able to exfiltrate files outside the configured roots.
"""
from __future__ import annotations
import pytest
from pathlib import Path


def test_safe_path_accepts_target_inside_roots():
    from painter.tools._common import _safe_path
    p = _safe_path("targets/masterworks/great_wave.jpg")
    assert p.exists(), "a real target path inside targets/ must resolve"


def test_safe_path_rejects_etc_passwd():
    from painter.tools._common import _safe_path, PathNotAllowed
    with pytest.raises(PathNotAllowed):
        _safe_path("/etc/passwd")


def test_safe_path_rejects_relative_traversal():
    from painter.tools._common import _safe_path, PathNotAllowed
    # Any path that resolves outside allowed roots must raise
    with pytest.raises(PathNotAllowed):
        _safe_path("../../../etc/passwd")


def test_safe_path_rejects_empty():
    from painter.tools._common import _safe_path, PathNotAllowed
    with pytest.raises(PathNotAllowed):
        _safe_path("")


def test_safe_path_tmp_allowed():
    """/tmp is in the allowlist for target-dump / heatmap-dump scratch files."""
    from painter.tools._common import _safe_path
    # File may not exist, but must_exist=False should accept.
    # NOTE: on macOS /tmp is a symlink to /private/tmp, so resolve() returns
    # /private/tmp/... — check the resolved suffix rather than the prefix.
    p = _safe_path("/tmp/painter_test_placeholder.png", must_exist=False)
    assert "tmp" in str(p)


def test_safe_path_must_exist_default_true():
    """Default must_exist=True raises when the file is missing."""
    from painter.tools._common import _safe_path, PathNotAllowed
    with pytest.raises(PathNotAllowed):
        _safe_path("/tmp/definitely_does_not_exist_" + "x" * 20 + ".png")
