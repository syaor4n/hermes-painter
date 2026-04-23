"""Canvas-level tools: load/draw/score, state dumps, and simple target queries.

Handlers here are thin wrappers around viewer.py's ``/api/*`` plus a handful
of numpy-based inspection helpers (palette, features, gap coverage, grid
sampling). The rest of the tool server layers richer analysis and
stroke-planning on top of these primitives — e.g. ``analyze_target`` pulls
palette + features from this module, and the planning tools consume the
target array exposed via ``_common``.
"""
from __future__ import annotations

import base64
import io as _io
import json

import numpy as np
from PIL import Image

from painter.image_type import classify

from ._common import (
    PathNotAllowed,
    ViewerUnavailable,
    _DUMP_DIR,
    _dump_png,
    _safe_path,
    _target_array,
    _viewer_get,
    _viewer_post,
)


def tool_load_target(args: dict) -> dict:
    try:
        path = _safe_path(args["path"])
    except PathNotAllowed as exc:
        return {"error": str(exc)}
    try:
        with Image.open(path) as probe:
            probe.verify()
    except Exception as exc:
        return {"error": f"not a valid image: {path.name} ({exc})"}
    png = path.read_bytes()
    _viewer_post("/api/clear")
    _viewer_post("/api/target", raw=png)
    return {
        "path": str(path),
        "classification": classify(png),
    }


def tool_draw_strokes(args: dict) -> dict:
    plan = {"reasoning": args.get("reasoning", ""), "strokes": args["strokes"]}
    resp = json.loads(_viewer_post("/api/plan", plan))
    return resp


def tool_score_plan(args: dict) -> dict:
    plan = {"reasoning": args.get("reasoning", ""), "strokes": args["strokes"]}
    resp = json.loads(_viewer_post("/api/score_plan", plan))
    return resp


def tool_get_heatmap(_args: dict) -> dict:
    png = _viewer_get("/api/heatmap")
    return {"png_b64": base64.b64encode(png).decode("ascii")}


# --- Visual inspection tools ---
#
# The CLI agent (Claude Code / Hermes) is multimodal — it can Read PNG files.
# These tools write the current canvas / target / heatmap to disk so the agent
# can actually *look* at them via its Read tool, instead of reasoning about
# scores alone. This closes the biggest gap in the loop: visual critique.


def tool_dump_canvas(_args: dict) -> dict:
    """Save the current canvas to /tmp/painter_canvas.png and return the path.

    The agent should then `Read` the path to visually inspect its own work.
    """
    state = json.loads(_viewer_get("/api/state"))
    if not state.get("canvas_png"):
        return {"error": "no canvas yet"}
    return _dump_png("canvas", base64.b64decode(state["canvas_png"]))


def tool_dump_target(_args: dict) -> dict:
    """Save the current target to /tmp/painter_target.png and return the path."""
    try:
        resp = json.loads(_viewer_get("/api/target"))
    except ViewerUnavailable:
        raise
    except Exception:
        return {"error": "no target loaded"}
    if not resp.get("target_png"):
        return {"error": "no target loaded"}
    return _dump_png("target", base64.b64decode(resp["target_png"]))


def tool_dump_heatmap(_args: dict) -> dict:
    """Save the current error heatmap to /tmp/painter_heatmap.png."""
    png = _viewer_get("/api/heatmap")
    return _dump_png("heatmap", png)


def tool_sample_grid(args: dict) -> dict:
    """Batch-sample a grid of mean colors from the target in one call.

    Replaces the N² HTTP round-trips of calling sample_target in a loop.
    For a 24×24 grid, drops from ~4s to ~20ms.

    args: {gx: int = 16, gy: int = 16}
    Returns: {grid: [[hex, ...], ...], cell_w: int, cell_h: int}

    Cell dimensions are ceiling-divided so `gx * cell_w >= C_W` and
    `gy * cell_h >= C_H`. When the grid can't tile the canvas exactly
    (e.g. gx=24, C_W=512 → cell_w=22, total=528), the target is padded
    with edge-replicated pixels before reshape. This ensures stroke
    centers (`cx = i * cell_w + cell_w // 2`) fully span the canvas
    rather than leaving a blank strip at right/bottom. Side effect: the
    last column/row of strokes extends a few px past the canvas edge
    and gets clipped by the renderer — visually indistinguishable from
    a perfectly-tiled grid.
    """
    arr = _target_array()
    gx = int(args.get("gx", 16))
    gy = int(args.get("gy", 16))
    C_H, C_W = arr.shape[:2]
    # Ceiling division so gx*cell_w >= C_W (fixes 8-px right/bottom gap
    # on grid_size=24 where 24*21=504 < 512).
    cell_w = (C_W + gx - 1) // gx
    cell_h = (C_H + gy - 1) // gy
    sub_h = gy * cell_h
    sub_w = gx * cell_w
    if sub_h > C_H or sub_w > C_W:
        # Pad with edge-replicated pixels so the reshape works and the
        # padded region samples the target's edge colors (not pure white).
        padded = np.zeros((sub_h, sub_w, 3), dtype=arr.dtype)
        padded[:C_H, :C_W] = arr
        if sub_h > C_H:
            padded[C_H:, :C_W] = arr[C_H - 1:C_H, :, :]
        if sub_w > C_W:
            padded[:, C_W:] = padded[:, C_W - 1:C_W, :]
        sub = padded
    else:
        sub = arr[:sub_h, :sub_w]
    # (gy, cell_h, gx, cell_w, 3) → mean over axes 1 and 3
    means = sub.reshape(gy, cell_h, gx, cell_w, 3).mean(axis=(1, 3)).astype(int)
    grid = [
        ["#%02x%02x%02x" % (int(means[j, i, 0]), int(means[j, i, 1]), int(means[j, i, 2]))
         for i in range(gx)]
        for j in range(gy)
    ]
    return {"grid": grid, "cell_w": cell_w, "cell_h": cell_h}


def tool_get_palette(args: dict) -> dict:
    """Extract the N dominant colors from the target (LAB-space k-means-lite).

    args: {n: int=8}
    Returns: {colors: [{hex, rgb, weight}]} sorted by weight desc (weight = pixel count).

    This is the target's "recommended palette" — restricting your strokes to these
    (or close variants) tends to produce renders that look like the target.
    """
    n = int(args.get("n", 8))
    arr = _target_array()
    pixels = arr.reshape(-1, 3).astype(np.float32)

    # Quantize to a coarse grid in RGB to seed centroids deterministically
    quantized = (pixels // 32) * 32 + 16
    unique, counts = np.unique(quantized.astype(np.int32), axis=0, return_counts=True)
    order = np.argsort(-counts)
    unique = unique[order]
    counts = counts[order]

    # Pick top-N colors that are sufficiently different (MinDistance in LAB approximation
    # via Euclidean on scaled RGB — good enough for this purpose)
    picked: list[tuple[np.ndarray, int]] = []
    for u, c in zip(unique, counts):
        too_close = False
        for p, _ in picked:
            if np.linalg.norm(u.astype(float) - p.astype(float)) < 45:
                too_close = True
                break
        if not too_close:
            picked.append((u, int(c)))
        if len(picked) >= n:
            break

    total = sum(c for _, c in picked)
    return {
        "colors": [
            {
                "hex": "#%02x%02x%02x" % tuple(int(v) for v in p),
                "rgb": [int(v) for v in p],
                "weight": round(c / total, 3),
            }
            for p, c in picked
        ],
    }


def tool_dump_gaps(args: dict) -> dict:
    """Save a binary mask of canvas pixels that are TRUE gaps.

    A "true gap" = canvas pixel is close to the raw off-white base AND the target
    pixel at the same position is NOT near-white. This prevents false positives when
    the target itself has white/light areas (snow, bright sky, paper, etc.).

    Returns coverage in two flavors:
      - coverage: fraction of canvas painted away from base
      - effective_coverage: fraction of pixels that should be painted and are
        (ignores pixels where target = near-white too)

    Writes /tmp/painter_gaps.png. Black pixel = OK, white pixel = true gap.
    """
    state = json.loads(_viewer_get("/api/state"))
    if not state.get("canvas_png"):
        return {"error": "no canvas yet"}
    canvas_bytes = base64.b64decode(state["canvas_png"])
    img = Image.open(_io.BytesIO(canvas_bytes)).convert("RGB")
    arr = np.asarray(img).astype(np.int16)
    base_r, base_g, base_b = 251, 247, 238
    close = (
        (np.abs(arr[..., 0] - base_r) < 18) &
        (np.abs(arr[..., 1] - base_g) < 18) &
        (np.abs(arr[..., 2] - base_b) < 22)
    )
    light = arr.mean(axis=2) > 235
    looks_unpainted = close | light

    # Fetch target for "intentional bright areas" mask
    try:
        target_arr = _target_array()
        target_gray = target_arr.mean(axis=2)
        # Target pixels that are near-white (>230 brightness) should NOT be flagged
        # even if the canvas there is near-white — that's correct coverage.
        target_bright = target_gray > 225
    except Exception:
        target_bright = np.zeros_like(looks_unpainted, dtype=bool)

    # True gap = canvas looks unpainted AND target is not bright there
    true_gap = looks_unpainted & (~target_bright)
    gap_mask = true_gap.astype(np.uint8) * 255
    gap_img = Image.fromarray(gap_mask, mode="L")
    path = _DUMP_DIR / "painter_gaps.png"
    gap_img.save(path, format="PNG")

    # Also return the mask as base64 so clients can skip the shared-/tmp
    # file read — avoids cross-session contamination risk. The file is
    # still written for callers that have a legacy consumer (e.g. an agent
    # that wants to Read it directly).
    buf = _io.BytesIO()
    gap_img.save(buf, format="PNG")
    mask_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    coverage_raw = float(1.0 - looks_unpainted.sum() / looks_unpainted.size)
    effective_coverage = float(1.0 - true_gap.sum() / true_gap.size)
    return {
        "path": str(path),
        "mask_png": mask_b64,
        "coverage": round(effective_coverage, 3),
        "coverage_raw": round(coverage_raw, 3),
        "gap_pixels": int(true_gap.sum()),
    }


def tool_sample_target(args: dict) -> dict:
    """Return the mean color of a rectangle on the target.

    args: {x, y, w, h} — default w=h=8 for a point sample.
    Returns: {rgb, hex, x, y, w, h}
    """
    arr = _target_array()
    arr = _target_array()
    C_H, C_W = arr.shape[:2]
    x = max(0, min(C_W - 1, int(args.get("x", 0))))
    y = max(0, min(C_H - 1, int(args.get("y", 0))))
    w = max(1, min(C_W - x, int(args.get("w", 8))))
    h = max(1, min(C_H - y, int(args.get("h", 8))))
    block = arr[y:y + h, x:x + w]
    mean = block.mean(axis=(0, 1)).astype(int).tolist()
    return {
        "x": x, "y": y, "w": w, "h": h,
        "rgb": mean,
        "hex": "#%02x%02x%02x" % tuple(mean),
    }


def tool_dump_all(_args: dict) -> dict:
    """Shortcut: dump canvas + target + heatmap at once for a full visual audit."""
    out = {}
    try:
        out["canvas"] = tool_dump_canvas({})
    except Exception as e:
        out["canvas"] = {"error": str(e)}
    try:
        out["target"] = tool_dump_target({})
    except Exception as e:
        out["target"] = {"error": str(e)}
    try:
        out["heatmap"] = tool_dump_heatmap({})
    except Exception as e:
        out["heatmap"] = {"error": str(e)}
    return out


def tool_get_regions(args: dict) -> dict:
    resp = json.loads(_viewer_get("/api/regions"))
    top = int(args.get("top", 8))
    return {"regions": resp.get("regions", [])[:top]}


def tool_get_state(_args: dict) -> dict:
    return json.loads(_viewer_get("/api/state"))


def tool_clear(_args: dict) -> dict:
    return json.loads(_viewer_post("/api/clear"))


def tool_snapshot(_args: dict) -> dict:
    return json.loads(_viewer_post("/api/snapshot"))


def tool_restore(args: dict) -> dict:
    return json.loads(_viewer_post("/api/restore", {"id": args["id"]}))
