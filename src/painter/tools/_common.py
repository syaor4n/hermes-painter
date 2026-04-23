"""Shared helpers for the painter tool server.

Everything here is imported by >1 handler group:
  - ``VIEWER_URL`` + ``_viewer_get`` / ``_viewer_post`` — the HTTP bridge to
    viewer.py. ``VIEWER_URL`` is mutated by ``server.main`` at startup, so
    ``_viewer_*`` read it from this module at call time (not at import time).
  - ``ViewerUnavailable`` — surfaced through the HTTP layer as 503.
  - ``_safe_path`` + ``PathNotAllowed`` + ``_ALLOWED_ROOTS`` — path allowlist
    so a networked tool layer can't exfiltrate arbitrary files.
  - ``_DUMP_DIR`` + ``_dump_png`` — /tmp canvas dump convention.
  - ``_target_array`` — fetch the current target as HxWx3 RGB numpy array.
  - ``_load_mask`` — load a 0..1 float mask from a PNG path (saliency, etc.).
  - ``_SALIENCY_PATH`` — shared location of the saliency mask file.
  - ``_REPO_ROOT`` / ``_REFLECTIONS_DIR`` / ``_SCRIPTS_DIR`` — filesystem
    anchors used by memory handlers. Kept here so moving the code
    under ``src/painter/tools/`` doesn't change the paths they resolve to.
"""
from __future__ import annotations

import base64
import io as _io
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image


# --- Viewer bridge --------------------------------------------------------
#
# ``VIEWER_URL`` is a module-level global so ``server.main`` can rebind it at
# startup (``common.VIEWER_URL = args.viewer``). ``_viewer_get`` /
# ``_viewer_post`` dereference it at call time — do NOT capture it at import
# time in other modules.

VIEWER_URL = "http://localhost:8080"


class ViewerUnavailable(RuntimeError):
    """The viewer on :8080 is not reachable. Surface this to the caller."""


def _viewer_get(path: str) -> bytes:
    req = Request(f"{VIEWER_URL}{path}")
    try:
        with urlopen(req, timeout=30) as r:
            return r.read()
    except URLError as e:
        raise ViewerUnavailable(f"viewer unreachable at {VIEWER_URL}: {e}") from e


def _viewer_post(path: str, payload: dict | None = None, raw: bytes | None = None) -> bytes:
    if raw is not None:
        req = Request(f"{VIEWER_URL}{path}", data=raw, method="POST")
        req.add_header("Content-Type", "image/png")
    else:
        data = json.dumps(payload or {}).encode()
        req = Request(f"{VIEWER_URL}{path}", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=60) as r:
            return r.read()
    except URLError as e:
        raise ViewerUnavailable(f"viewer unreachable at {VIEWER_URL}: {e}") from e


# --- Path allowlist -------------------------------------------------------
# Any tool accepting a user-supplied path goes through `_safe_path` so the
# tool server cannot exfiltrate arbitrary files if exposed (e.g. someone
# binding on 0.0.0.0 or colocating with a less-trusted caller).
#
# ``_REPO_ROOT`` used to resolve to the hermes-painter checkout from
# ``scripts/hermes_tools.py``; after the split the code lives under
# ``src/painter/tools/`` so we walk three levels up instead of one.

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_REFLECTIONS_DIR = Path(
    os.environ.get("PAINTER_REFLECTIONS_DIR")
    or _REPO_ROOT / "reflections"
)
_ALLOWED_ROOTS = tuple(p.resolve() for p in (
    _REPO_ROOT / "targets",
    _REPO_ROOT / "runs",
    _REPO_ROOT / "reflections",
    _REPO_ROOT / "skills",
    _REPO_ROOT / "styles",
    _REPO_ROOT / "personas",
    Path("/tmp"),
))


class PathNotAllowed(ValueError):
    """Raised when a user-supplied path resolves outside the allowlist."""


def _safe_path(raw: str, *, must_exist: bool = True) -> Path:
    """Resolve `raw` and refuse if it escapes `_ALLOWED_ROOTS`.

    Raises `PathNotAllowed` (a ValueError) on violation. Tool handlers
    should catch it and surface `{"error": str(exc)}`.
    """
    if not raw:
        raise PathNotAllowed("empty path")
    p = Path(raw).resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(root)
        except ValueError:
            continue
        if must_exist and not p.exists():
            raise PathNotAllowed(f"no such file: {raw}")
        return p
    raise PathNotAllowed(
        f"path {raw!r} is outside the allowlist "
        f"({', '.join(str(r) for r in _ALLOWED_ROOTS)})"
    )


# --- /tmp dump helpers ----------------------------------------------------
#
# The CLI agent (Claude Code / Hermes) is multimodal — it can Read PNG files.
# These helpers write the current canvas / target / heatmap to disk so the
# agent can actually *look* at them via its Read tool, instead of reasoning
# about scores alone. This closes the biggest gap in the loop: visual
# critique.

_DUMP_DIR = Path("/tmp")
_SALIENCY_PATH = Path("/tmp/painter_saliency.png")


def _dump_png(name: str, png_bytes: bytes) -> dict:
    path = _DUMP_DIR / f"painter_{name}.png"
    path.write_bytes(png_bytes)
    return {"path": str(path), "bytes": len(png_bytes)}


def _target_array() -> np.ndarray:
    """Fetch the current target as an HxWx3 numpy array (canvas-sized, RGB).

    The viewer already resizes targets to CANVAS_SIZE on upload, so we just
    return the raw array without further resize (v15: canvas is configurable).
    """
    resp = json.loads(_viewer_get("/api/target"))
    raw = base64.b64decode(resp["target_png"])
    img = Image.open(_io.BytesIO(raw)).convert("RGB")
    return np.asarray(img)


def _load_mask(mask_path: str | None):
    """Load a 0..1 float mask from a PNG path. Returns None if no path."""
    if not mask_path:
        return None
    try:
        p = _safe_path(mask_path)
    except PathNotAllowed:
        return None
    img = Image.open(p).convert("L")
    target_size = tuple(_target_array().shape[:2][::-1])  # (W, H)
    if img.size != target_size:
        img = img.resize(target_size, Image.LANCZOS)
    return np.asarray(img).astype(np.float32) / 255.0
