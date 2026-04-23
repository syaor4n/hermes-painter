"""Stroke-planning tools: edges, details, contours, highlights, sculpting, faces, accents.

Each ``tool_*_plan`` handler returns a ``strokes`` list ready to POST back
to the viewer's ``/api/plan``. The helpers at the top (tonal dark, tanh
contrast, focus alpha) keep the finishing passes in the same tonal universe
as the underpainting — see ``paint_lib._apply_contrast_boost`` for the
mirror implementation.
"""
from __future__ import annotations

import base64
import colorsys as _colorsys
import io as _io
import json
import math
import sys

import numpy as np
from PIL import Image

from ._common import (
    _load_mask,
    _target_array,
    _viewer_get,
)


def tool_edge_stroke_plan(args: dict) -> dict:
    """Generate brush strokes following the strongest edges of the target.

    These strokes add DETAIL and shape definition — they paint along object boundaries.
    Apply AFTER the underpainting to restore structure that the grid averaging destroyed.

    args: {
      max_strokes: int = "auto",    # "auto" = scale with edge density (40-250); else int
      min_length: int = 10,
      width: int = 3,
      alpha: float = 0.7,
      sample_every: int = 2,
      percentile: float = 92,       # edge threshold percentile (higher = fewer edges)
      color_source: "target"|"dark"
    }
    Returns: {strokes, n, edge_pixel_count, auto_budget}
    """
    from scipy.ndimage import sobel
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)
    mag = np.hypot(gx, gy)

    percentile = float(args.get("percentile", 92))
    thresh = np.percentile(mag, percentile)
    edge_pts = np.argwhere(mag > thresh)
    edge_pixel_count = int(len(edge_pts))
    if edge_pixel_count == 0:
        return {"strokes": [], "n": 0, "edge_pixel_count": 0, "auto_budget": 0}

    import random as _random
    _random.seed(int(args.get("seed", 0)))

    # Auto budget: scale max_strokes with edge density.
    # Low-density images (simple scenes) need fewer strokes; high-density (detailed)
    # get more, capped at 250 for perf.
    max_arg = args.get("max_strokes", "auto")
    if max_arg == "auto":
        # edge_pixel_count typical range: 500 (simple) — 50000 (dense). We want strokes 40-250.
        auto_budget = int(min(250, max(40, edge_pixel_count / 150)))
        max_strokes = auto_budget
    else:
        max_strokes = int(max_arg)
        auto_budget = None

    min_length = int(args.get("min_length", 10))
    width = int(args.get("width", 3))
    alpha = float(args.get("alpha", 0.7))
    sample_every = int(args.get("sample_every", 2))
    color_source = args.get("color_source", "target")

    # Shuffle and walk edges to build stroke paths
    pts_set = set(map(tuple, edge_pts[::sample_every]))
    strokes: list[dict] = []
    visited: set[tuple[int, int]] = set()

    # Normalize edge direction (perpendicular to gradient)
    def edge_dir(y, x):
        # Edge direction = perpendicular to (gx, gy) at this point
        g_x = gx[y, x]
        g_y = gy[y, x]
        n = (g_x * g_x + g_y * g_y) ** 0.5 or 1.0
        # Perpendicular:
        return (-g_y / n, g_x / n)

    pts_list = list(pts_set)
    _random.shuffle(pts_list)

    for (y, x) in pts_list:
        if len(strokes) >= max_strokes:
            break
        if (y, x) in visited:
            continue
        # Walk the edge in both directions
        path = [(x, y)]
        # Walk forward
        cur_y, cur_x = y, x
        for _ in range(20):
            dx, dy = edge_dir(cur_y, cur_x)
            nx = int(round(cur_x + dx * sample_every))
            ny = int(round(cur_y + dy * sample_every))
            if not (0 <= nx < arr.shape[1] and 0 <= ny < arr.shape[0]):
                break
            if (ny, nx) not in pts_set or (ny, nx) in visited:
                break
            path.append((nx, ny))
            visited.add((ny, nx))
            cur_y, cur_x = ny, nx
        # Walk backward
        cur_y, cur_x = y, x
        back_path: list[tuple[int, int]] = []
        for _ in range(20):
            dx, dy = edge_dir(cur_y, cur_x)
            nx = int(round(cur_x - dx * sample_every))
            ny = int(round(cur_y - dy * sample_every))
            if not (0 <= nx < arr.shape[1] and 0 <= ny < arr.shape[0]):
                break
            if (ny, nx) not in pts_set or (ny, nx) in visited:
                break
            back_path.append((nx, ny))
            visited.add((ny, nx))
            cur_y, cur_x = ny, nx
        path = list(reversed(back_path)) + path
        visited.add((y, x))

        # Check path length
        if len(path) < 3:
            continue
        total_len = sum(
            ((path[i + 1][0] - path[i][0]) ** 2 + (path[i + 1][1] - path[i][1]) ** 2) ** 0.5
            for i in range(len(path) - 1)
        )
        if total_len < min_length:
            continue

        # Sample color
        if color_source == "dark":
            color = "#0a0a0a"
        else:
            mid_y, mid_x = path[len(path) // 2][1], path[len(path) // 2][0]
            r, g, b = arr[mid_y, mid_x]
            # Slightly darken to emphasize edge
            color = "#%02x%02x%02x" % (max(0, int(r) - 30), max(0, int(g) - 30), max(0, int(b) - 30))

        # Use the first, middle, and last points as brush path (3 points).
        # Cast to int (not numpy int64) for JSON serialization.
        def to_int_pair(p):
            return [int(p[0]), int(p[1])]

        simplified = [to_int_pair(path[0])]
        if len(path) >= 3:
            simplified.append(to_int_pair(path[len(path) // 2]))
        simplified.append(to_int_pair(path[-1]))

        strokes.append({
            "type": "brush",
            "points": simplified,
            "color": color,
            "width": int(width),
            "alpha": float(alpha),
            "texture": "smooth",
        })

    return {
        "strokes": strokes,
        "n": len(strokes),
        "edge_pixel_count": edge_pixel_count,
        "auto_budget": auto_budget,
    }


# ----- v10 aesthetic helpers: tonal colors, contrast shaping, focus falloff -----


def _tonal_dark(r: int, g: int, b: int, s_boost: float = 0.22, l_drop: float = 0.38) -> tuple[int, int, int]:
    """Return the 'painterly dark' version of a color: same hue, more saturated,
    less light. Unlike #101010 (pure ink), this stays within the target's
    color universe — red lips produce deep carmine, not black.
    """
    h, l, s = _colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    s = min(1.0, s + s_boost)
    # Floor at L=0.06 so extreme saturation lows don't collapse to black
    l = max(0.06, l - l_drop)
    rr, gg, bb = _colorsys.hls_to_rgb(h, l, s)
    return int(rr * 255), int(gg * 255), int(bb * 255)


def _apply_tanh_boost(r: int, g: int, b: int, boost: float) -> tuple[int, int, int]:
    """tanh S-curve matching paint_lib's _apply_contrast_boost (paint_lib uses
    the same function on underpainting colors — we apply it here so the
    finishing passes stay in the same tonal universe)."""
    if boost <= 0:
        return r, g, b
    k = 1.0 + 3.0 * boost

    def f(v: float) -> int:
        x = (v / 255.0 - 0.5) * k
        return int(255 * 0.5 * (1 + math.tanh(x)))
    return f(r), f(g), f(b)


def _focus_alpha_scale(x: int, y: int, focus_center, focus_radius: float,
                        focus_falloff: float) -> float:
    """Radial alpha falloff around a focus center. Returns 1.0 at center,
    (1 - focus_falloff) at radius. Linear in-between. Clamped to >= 0.5."""
    if focus_center is None or focus_falloff <= 0:
        return 1.0
    cx, cy = focus_center
    r = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    if focus_radius <= 0:
        return 1.0
    t = min(1.0, r / focus_radius)
    return max(1.0 - focus_falloff * t, 0.5)


def tool_detail_stroke_plan(args: dict) -> dict:
    """Generate THIN polyline strokes for finishing details (final pass).

    Distinct from edge_stroke_plan:
      - Only the strongest edges (high percentile, default 97).
      - Very thin width (1-2), high alpha, crisp polylines (not brush).
      - Pixel-exact color sampling (target pixel color, no cell averaging).
      - Short segments — these are ink-like contour marks for fine features:
        eyes, lips, petal outlines, branch tips, window frames, text edges.

    Run AFTER underpainting, fog, edge_stroke_plan, and gap-fill — details
    must sit on top so they read.

    args: {
      max_strokes: int|"auto" = "auto",   # auto = 100-600 scaled from edge density
      percentile: float = 97,             # higher = rarer edges
      width: int = 1,
      alpha: float = 0.9,
      min_length: int = 5,
      sample_every: int = 1,
      color_source: "target"|"dark"|"contrast" = "contrast",
      mask_path: str|None,                # skip strokes whose midpoint is in low-saliency
      mask_threshold: float = 0.3,
      contrast_boost: float = 0.0,        # v10: tanh S-curve on output color
      width_jitter: bool = True,          # v10: random {0,0,0,+1} width variation
      focus_center: [x, y]|None,          # v10: radial alpha falloff center
      focus_radius: float = 200.0,
      focus_falloff: float = 0.0,         # 0 = no falloff, 0.3 = 30% alpha drop at radius
      seed: int = 0,
    }
    color_source:
      - "target": use the pixel color at the midpoint (pure sampling)
      - "dark": v10 tonal dark — saturated darker version of the local color
      - "contrast": sample the DARKER side of the gradient

    Returns: {strokes, n, edge_pixel_count, auto_budget, percentile}
    """
    from scipy.ndimage import sobel
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)
    mag = np.hypot(gx, gy)

    mask = _load_mask(args.get("mask_path"))
    mask_threshold = float(args.get("mask_threshold", 0.3))

    percentile = float(args.get("percentile", 97))
    thresh = np.percentile(mag, percentile)
    edge_pts = np.argwhere(mag > thresh)
    edge_pixel_count = int(len(edge_pts))
    if edge_pixel_count == 0:
        return {"strokes": [], "n": 0, "edge_pixel_count": 0,
                "auto_budget": 0, "percentile": percentile}

    import random as _random
    _random.seed(int(args.get("seed", 0)))

    max_arg = args.get("max_strokes", "auto")
    if max_arg == "auto":
        auto_budget = int(min(600, max(80, edge_pixel_count / 40)))
        max_strokes = auto_budget
    else:
        max_strokes = int(max_arg)
        auto_budget = None

    min_length = int(args.get("min_length", 5))
    width = int(args.get("width", 1))
    alpha = float(args.get("alpha", 0.9))
    sample_every = max(1, int(args.get("sample_every", 1)))
    color_source = args.get("color_source", "contrast")
    # v10 aesthetic args
    contrast_boost = float(args.get("contrast_boost", 0.0))
    width_jitter = bool(args.get("width_jitter", True))
    focus_center = args.get("focus_center")
    focus_radius = float(args.get("focus_radius", 200.0))
    focus_falloff = float(args.get("focus_falloff", 0.0))

    def edge_dir(y, x):
        g_x = gx[y, x]; g_y = gy[y, x]
        n = (g_x * g_x + g_y * g_y) ** 0.5 or 1.0
        return (-g_y / n, g_x / n)

    def sample_contrast(y, x):
        """Pick darker side of the edge — gives outline effect."""
        g_x = gx[y, x]; g_y = gy[y, x]
        n = (g_x * g_x + g_y * g_y) ** 0.5 or 1.0
        nx_, ny_ = g_x / n, g_y / n
        # Try ±2 px along gradient, pick darker pixel
        samples = []
        for s in (-2, 2):
            sy = int(np.clip(y + ny_ * s, 0, arr.shape[0] - 1))
            sx = int(np.clip(x + nx_ * s, 0, arr.shape[1] - 1))
            r, g, b = arr[sy, sx]
            samples.append((int(r) + int(g) + int(b), sy, sx))
        _, sy, sx = min(samples)
        r, g, b = arr[sy, sx]
        return int(r), int(g), int(b)

    pts_set = set(map(tuple, edge_pts[::sample_every]))
    pts_list = list(pts_set)
    _random.shuffle(pts_list)

    strokes: list[dict] = []
    visited: set[tuple[int, int]] = set()

    for (y, x) in pts_list:
        if len(strokes) >= max_strokes:
            break
        if (y, x) in visited:
            continue
        path = [(x, y)]
        # Walk both directions, shorter than edge_stroke_plan (max 12 steps each way)
        cur_y, cur_x = y, x
        for _ in range(12):
            dx, dy = edge_dir(cur_y, cur_x)
            nx = int(round(cur_x + dx * sample_every))
            ny = int(round(cur_y + dy * sample_every))
            if not (0 <= nx < arr.shape[1] and 0 <= ny < arr.shape[0]):
                break
            if (ny, nx) not in pts_set or (ny, nx) in visited:
                break
            path.append((nx, ny))
            visited.add((ny, nx))
            cur_y, cur_x = ny, nx
        cur_y, cur_x = y, x
        back: list[tuple[int, int]] = []
        for _ in range(12):
            dx, dy = edge_dir(cur_y, cur_x)
            nx = int(round(cur_x - dx * sample_every))
            ny = int(round(cur_y - dy * sample_every))
            if not (0 <= nx < arr.shape[1] and 0 <= ny < arr.shape[0]):
                break
            if (ny, nx) not in pts_set or (ny, nx) in visited:
                break
            back.append((nx, ny))
            visited.add((ny, nx))
            cur_y, cur_x = ny, nx
        path = list(reversed(back)) + path
        visited.add((y, x))

        if len(path) < 2:
            continue
        total_len = sum(
            ((path[i+1][0] - path[i][0])**2 + (path[i+1][1] - path[i][1])**2) ** 0.5
            for i in range(len(path) - 1)
        )
        if total_len < min_length:
            continue

        mid_x, mid_y = path[len(path) // 2]

        # Optional mask filter: skip strokes whose midpoint is in low-saliency
        if mask is not None and mask[mid_y, mid_x] < mask_threshold:
            continue

        if color_source == "dark":
            # v10: tonal dark (saturated darker version of local color) rather
            # than pure ink, so finishing lines stay within the target's color
            # universe — red lips → carmine, not black.
            pr, pg, pb = arr[mid_y, mid_x]
            cr, cg, cb = _tonal_dark(int(pr), int(pg), int(pb))
        elif color_source == "target":
            pr, pg, pb = arr[mid_y, mid_x]
            cr, cg, cb = int(pr), int(pg), int(pb)
        else:  # contrast — darker side of the gradient
            cr, cg, cb = sample_contrast(mid_y, mid_x)

        # v10: apply contrast_boost so finishing colors match underpainting tone
        cr, cg, cb = _apply_tanh_boost(cr, cg, cb, contrast_boost)
        color = "#%02x%02x%02x" % (cr, cg, cb)

        # v10: width jitter for hand-drawn feel
        w_jitter = _random.choice([0, 0, 0, 1]) if width_jitter else 0
        this_width = max(1, int(width) + w_jitter)

        # v10: radial focus falloff on alpha
        a = float(alpha) * _focus_alpha_scale(
            int(mid_x), int(mid_y), focus_center, focus_radius, focus_falloff)

        # Simplify path: keep ≤5 points for crisp polyline
        if len(path) <= 5:
            simplified = [[int(p[0]), int(p[1])] for p in path]
        else:
            idxs = [0,
                    len(path) // 4,
                    len(path) // 2,
                    (3 * len(path)) // 4,
                    len(path) - 1]
            simplified = [[int(path[i][0]), int(path[i][1])] for i in idxs]

        strokes.append({
            "type": "polyline",
            "points": simplified,
            "color": color,
            "width": this_width,
            "alpha": a,
        })

    return {
        "strokes": strokes,
        "n": len(strokes),
        "edge_pixel_count": edge_pixel_count,
        "auto_budget": auto_budget,
        "percentile": percentile,
    }


def tool_contour_stroke_plan(args: dict) -> dict:
    """Trace connected edge contours as smooth curves — for faces, animals, legibility.

    Distinct from detail_stroke_plan (which walks random high-gradient pixels):
    this uses Canny + skeletonize to extract CONNECTED 1-pixel-wide edges, then
    orders each component into a path so we emit strokes that follow real
    contours (eye outlines, beak, lips, branch edges). Each output stroke is
    a bezier or polyline that actually looks like drawing, not scribbling.

    Run as the final pass after detail_stroke_plan so the contours sit on top.

    args: {
      sigma: float = 2.0,             # Canny gaussian sigma (smaller = more edges)
      low_threshold: float|None,      # Canny hysteresis; None = auto
      high_threshold: float|None,
      min_length: int = 14,           # min path length in pixels
      max_strokes: int|"auto" = "auto",
      width: int = 1,
      alpha: float = 0.9,
      color_source: "target"|"dark"|"contrast" = "contrast",
      stroke_type: "bezier"|"polyline" = "bezier",
      simplify_tolerance: float = 1.2,
      focus_box: [x,y,w,h]|None,      # restrict to a region (e.g. a face)
      focus_boost: float = 2.0,        # how much to upweight contours in focus_box
      mask_path: str|None,             # saliency mask — components in high-saliency get boosted
      mask_boost: float = 2.5,
      mask_threshold: float = 0.3,     # per-pixel threshold inside mask
    }

    Returns: {strokes, n, n_components, auto_budget, total_contour_pixels}
    """
    from skimage.feature import canny
    from skimage.morphology import skeletonize
    from skimage.measure import approximate_polygon
    from scipy.ndimage import label
    import random as _random

    arr = _target_array()
    gray_01 = arr.mean(axis=2) / 255.0

    sigma = float(args.get("sigma", 2.0))
    low = args.get("low_threshold")
    high = args.get("high_threshold")
    edges = canny(gray_01, sigma=sigma,
                  low_threshold=low, high_threshold=high)
    # Thin to 1-pixel-wide skeletons so walks don't branch unpredictably
    skel = skeletonize(edges)

    total_px = int(skel.sum())
    if total_px == 0:
        return {"strokes": [], "n": 0, "n_components": 0,
                "auto_budget": 0, "total_contour_pixels": 0}

    # Connected components (8-connectivity)
    structure = np.ones((3, 3), dtype=int)
    labels, n_components = label(skel, structure=structure)

    painterly = bool(args.get("painterly", True))

    min_length = int(args.get("min_length", 14))
    width = int(args.get("width", 1))
    alpha = float(args.get("alpha", 0.9))
    color_source = args.get("color_source", "contrast")
    stroke_type = args.get("stroke_type", "bezier")
    simplify_tol = float(args.get("simplify_tolerance", 1.2))
    # v10 aesthetic args
    contrast_boost = float(args.get("contrast_boost", 0.0))
    width_jitter = bool(args.get("width_jitter", True))
    skip_short_fraction = float(args.get("skip_short_fraction", 0.0))  # 0..0.5
    focus_center = args.get("focus_center")
    focus_radius = float(args.get("focus_radius", 200.0))
    focus_falloff = float(args.get("focus_falloff", 0.0))

    focus_box = args.get("focus_box")
    focus_boost = float(args.get("focus_boost", 2.0))
    if focus_box:
        fx, fy, fw, fh = focus_box
        fx = max(0, int(fx)); fy = max(0, int(fy))
        fw = min(arr.shape[1] - fx, int(fw)); fh = min(arr.shape[0] - fy, int(fh))
    else:
        fx = fy = fw = fh = 0

    max_arg = args.get("max_strokes", "auto")
    if max_arg == "auto":
        auto_budget = int(min(400, max(30, n_components // 2)))
        max_strokes = auto_budget
    else:
        max_strokes = int(max_arg)
        auto_budget = None

    seed = int(args.get("seed", 0))
    _random.seed(seed)

    # Pre-compute gradient for contrast color sampling
    from scipy.ndimage import sobel
    gy = sobel(gray_01 * 255, axis=0)
    gx = sobel(gray_01 * 255, axis=1)

    def sample_color(path_pts_xy):
        mid = path_pts_xy[len(path_pts_xy) // 2]
        mx, my = int(mid[0]), int(mid[1])
        if color_source == "dark":
            return "#101010"
        if color_source == "target":
            r, g, b = arr[my, mx]
            return "#%02x%02x%02x" % (int(r), int(g), int(b))
        # contrast — pick darker side of gradient
        gxv = gx[my, mx]; gyv = gy[my, mx]
        n = (gxv * gxv + gyv * gyv) ** 0.5 or 1.0
        nx_, ny_ = gxv / n, gyv / n
        best = None
        for s in (-2, 2):
            sy = int(np.clip(my + ny_ * s, 0, arr.shape[0] - 1))
            sx = int(np.clip(mx + nx_ * s, 0, arr.shape[1] - 1))
            r, g, b = arr[sy, sx]
            lum = int(r) + int(g) + int(b)
            if best is None or lum < best[0]:
                best = (lum, int(r), int(g), int(b))
        return "#%02x%02x%02x" % (best[1], best[2], best[3])

    def trace_component(ys, xs):
        """Order a connected component into a path by repeated nearest-neighbor walk."""
        if len(ys) < 2:
            return None
        pts = set(zip(map(int, ys), map(int, xs)))
        # Find an endpoint: pixel with fewest neighbors in the component.
        # 8-conn neighbors from within the component.
        def nb_count(p):
            y, x = p
            c = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    if (y + dy, x + dx) in pts:
                        c += 1
            return c
        # Pick endpoint (deg==1). If none (closed loop), any point works.
        endpoints = [p for p in pts if nb_count(p) <= 1]
        if endpoints:
            start = endpoints[0]
        else:
            start = next(iter(pts))
        # Walk
        path = [start]
        visited = {start}
        cur = start
        while True:
            cy, cx = cur
            nxt = None
            # Prefer 4-connected first, then diagonals, for smoother paths
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                cand = (cy + dy, cx + dx)
                if cand in pts and cand not in visited:
                    nxt = cand
                    break
            if nxt is None:
                break
            path.append(nxt)
            visited.add(nxt)
            cur = nxt
        if len(path) < 2:
            return None
        # Convert (y,x) → (x,y) for stroke output
        return [(int(p[1]), int(p[0])) for p in path]

    # Optional saliency mask — boost components mostly inside high-saliency
    mask = _load_mask(args.get("mask_path"))
    mask_boost = float(args.get("mask_boost", 2.5))
    mask_threshold = float(args.get("mask_threshold", 0.3))

    # Collect component sizes + (optionally) boost components inside focus_box / saliency
    component_info = []
    for c in range(1, n_components + 1):
        ys, xs = np.where(labels == c)
        if len(ys) < min_length // 2:
            continue
        # Check overlap with focus_box
        boost = 1.0
        if focus_box:
            in_box = ((xs >= fx) & (xs < fx + fw) &
                      (ys >= fy) & (ys < fy + fh)).sum()
            if in_box > len(xs) * 0.4:
                boost = focus_boost
        # Saliency-aware boost
        if mask is not None:
            in_salient = (mask[ys, xs] > mask_threshold).sum()
            if in_salient > len(xs) * 0.5:
                boost = max(boost, mask_boost)
            elif in_salient < len(xs) * 0.15:
                # Mostly background — de-prioritize
                boost *= 0.4
        component_info.append((len(ys) * boost, c, ys, xs, boost))
    # Paint longest components first (they're usually the most important contours)
    component_info.sort(reverse=True, key=lambda t: t[0])
    # v10: drop the shortest N% of components — lost & found edges principle.
    # Applied AFTER the boost sort so we drop from the tail (least important).
    if skip_short_fraction > 0 and len(component_info) > 5:
        keep = int(len(component_info) * (1.0 - skip_short_fraction))
        component_info = component_info[:max(5, keep)]

    # For painterly emission, sample color from the current canvas so
    # contour strokes blend with the paint they sit on. Falls back to
    # the target array if the viewer isn't reachable.
    if painterly:
        _canvas_arr = _fetch_current_canvas()
        if _canvas_arr is None:
            _canvas_arr = arr  # the target array, already in scope
    else:
        _canvas_arr = None

    strokes: list[dict] = []
    for _, c, ys, xs, boost in component_info:
        if len(strokes) >= max_strokes:
            break
        path = trace_component(ys, xs)
        if path is None or len(path) < 2:
            continue
        total_len = sum(
            ((path[i+1][0] - path[i][0])**2 + (path[i+1][1] - path[i][1])**2) ** 0.5
            for i in range(len(path) - 1)
        )
        if total_len < min_length:
            continue

        # Simplify path (Douglas-Peucker via approximate_polygon)
        arr_pts = np.array([[p[1], p[0]] for p in path])  # (y, x) order for skimage
        approx = approximate_polygon(arr_pts, tolerance=simplify_tol)
        # Back to (x, y)
        simplified = [(int(p[1]), int(p[0])) for p in approx.tolist()]
        if len(simplified) < 2:
            continue

        # v10: apply tanh contrast_boost to the sampled color
        hex_color = sample_color(simplified)
        cr = int(hex_color[1:3], 16); cg = int(hex_color[3:5], 16); cb = int(hex_color[5:7], 16)
        cr, cg, cb = _apply_tanh_boost(cr, cg, cb, contrast_boost)
        color = "#%02x%02x%02x" % (cr, cg, cb)

        # Width jitter (v10: controlled via width_jitter flag)
        w = width + (_random.choice([0, 0, 0, 1]) if width_jitter else 0)

        # v10: radial focus falloff on alpha, using midpoint of stroke
        mid_idx = len(simplified) // 2
        mx, my = simplified[mid_idx]
        a = float(alpha) * _focus_alpha_scale(
            int(mx), int(my), focus_center, focus_radius, focus_falloff)

        # Painterly emission (new default): 3-8 overlapping brush strokes.
        if painterly:
            import random as _r_mod
            component_rng = _r_mod.Random(seed * 31 + c)
            painterly_strokes = _painterly_contour_strokes(
                simplified_path=[(float(p[0]), float(p[1])) for p in simplified],
                current_canvas=_canvas_arr,
                base_width=int(width),
                args=args,
                rng=component_rng,
            )
            # Scale per-stroke alpha by focus falloff (same formula as drawn path)
            focus_scale = _focus_alpha_scale(
                int(mx), int(my), focus_center, focus_radius, focus_falloff)
            for ps in painterly_strokes:
                ps["alpha"] = float(ps["alpha"]) * focus_scale
                strokes.append(ps)
                if len(strokes) >= max_strokes:
                    break
            if len(strokes) >= max_strokes:
                break
            continue

        # Emit as beziers connecting consecutive simplified points, or a single polyline
        if stroke_type == "bezier" and len(simplified) >= 2:
            # For smoothness, emit one bezier per consecutive pair with control
            # points derived from neighboring points (Catmull-Rom-ish)
            pts = simplified
            for i in range(len(pts) - 1):
                p0 = pts[i]; p1 = pts[i + 1]
                prev = pts[i - 1] if i > 0 else p0
                nxt = pts[i + 2] if i + 2 < len(pts) else p1
                # tangents
                t0 = ((p1[0] - prev[0]) / 6.0, (p1[1] - prev[1]) / 6.0)
                t1 = ((nxt[0] - p0[0]) / 6.0, (nxt[1] - p0[1]) / 6.0)
                c1 = [int(p0[0] + t0[0]), int(p0[1] + t0[1])]
                c2 = [int(p1[0] - t1[0]), int(p1[1] - t1[1])]
                strokes.append({
                    "type": "bezier",
                    "points": [[int(p0[0]), int(p0[1])], c1, c2,
                               [int(p1[0]), int(p1[1])]],
                    "color": color,
                    "width": int(w),
                    "alpha": a,
                })
                if len(strokes) >= max_strokes:
                    break
        else:
            strokes.append({
                "type": "polyline",
                "points": [[int(p[0]), int(p[1])] for p in simplified],
                "color": color,
                "width": int(w),
                "alpha": a,
            })

    return {
        "strokes": strokes,
        "n": len(strokes),
        "n_components": int(n_components),
        "auto_budget": auto_budget,
        "total_contour_pixels": total_px,
    }


def tool_highlight_stroke_plan(args: dict) -> dict:
    """Find local brightness maxima and emit small dabs for catchlights / shine.

    Ideal as the final phase — adds "life" to eyes, lips, water, foam, metal.

    args: {
      threshold: int = 235,         # minimum brightness (0-255) to consider
      contrast_min: int = 30,        # min difference vs local surroundings
      max_strokes: int|"auto" = "auto",   # auto scales 10-60 with number of candidates
      size_min: int = 3,
      size_max: int = 6,
      alpha: float = 0.85,
      warm_tint: float = 0.1,        # 0..1, bias toward warm highlight color
      mask_path: str|None,           # only keep maxima inside the mask
      seed: int = 0,
    }
    Returns: {strokes, n, candidates, auto_budget}
    """
    from scipy.ndimage import maximum_filter
    import random as _random
    arr = _target_array()
    gray = arr.mean(axis=2)

    threshold = int(args.get("threshold", 235))
    contrast_min = int(args.get("contrast_min", 30))
    mx = maximum_filter(gray, size=7)
    is_max = (gray == mx) & (gray >= threshold)
    # Local contrast: brightness above local mean in a 15px window
    from scipy.ndimage import uniform_filter
    local_mean = uniform_filter(gray, size=15)
    has_contrast = (gray - local_mean) >= contrast_min
    candidates = is_max & has_contrast
    ys, xs = np.where(candidates)
    n_cand = int(len(ys))
    if n_cand == 0:
        return {"strokes": [], "n": 0, "candidates": 0, "auto_budget": 0}

    mask = _load_mask(args.get("mask_path"))
    if mask is not None:
        keep = mask[ys, xs] > 0.3
        ys, xs = ys[keep], xs[keep]
        n_cand = int(len(ys))
        if n_cand == 0:
            return {"strokes": [], "n": 0, "candidates": 0, "auto_budget": 0}

    max_arg = args.get("max_strokes", "auto")
    if max_arg == "auto":
        auto_budget = int(min(60, max(10, n_cand // 4)))
        max_strokes = auto_budget
    else:
        max_strokes = int(max_arg)
        auto_budget = None

    # Sort candidates by brightness, keep top budget
    order = np.argsort(-gray[ys, xs])
    ys, xs = ys[order][:max_strokes], xs[order][:max_strokes]

    seed = int(args.get("seed", 0))
    _random.seed(seed)

    size_min = int(args.get("size_min", 3))
    size_max = int(args.get("size_max", 6))
    alpha = float(args.get("alpha", 0.85))
    warm = float(args.get("warm_tint", 0.1))
    # v10: shared contrast shaping with underpainting
    contrast_boost = float(args.get("contrast_boost", 0.0))
    focus_center = args.get("focus_center")
    focus_radius = float(args.get("focus_radius", 200.0))
    focus_falloff = float(args.get("focus_falloff", 0.0))

    strokes: list[dict] = []
    for y, x in zip(ys.tolist(), xs.tolist()):
        r0, g0, b0 = arr[y, x]
        # Blend toward white, optional warm tint
        rr = int(255 * (1 - warm) + (int(r0) * 0.3 + 255 * 0.7) * warm)
        gg = int(255 * (1 - warm) + (int(g0) * 0.3 + 250 * 0.7) * warm)
        bb = int(255 * (1 - warm) + (int(b0) * 0.3 + 235 * 0.7) * warm)
        # Clamp + brighten
        rr = min(255, max(240, rr))
        gg = min(255, max(238, gg))
        bb = min(255, max(230, bb))
        # v10: apply shared contrast shaping to stay in the same tonal universe
        rr, gg, bb = _apply_tanh_boost(rr, gg, bb, contrast_boost)
        size = _random.randint(size_min, size_max)
        # v10: radial focus falloff (highlights de-emphasized far from focus)
        a = float(alpha) * _focus_alpha_scale(
            int(x), int(y), focus_center, focus_radius, focus_falloff)
        strokes.append({
            "type": "dab",
            "x": int(x),
            "y": int(y),
            "w": size,
            "h": max(2, size - 1),
            "angle": _random.uniform(0, math.pi),
            "color": "#%02x%02x%02x" % (rr, gg, bb),
            "alpha": a,
        })
    return {
        "strokes": strokes,
        "n": len(strokes),
        "candidates": n_cand,
        "auto_budget": auto_budget,
    }


def tool_accent_preserve_plan(args: dict) -> dict:
    """v17: find high-chroma regions (saturated accents like red lips, turquoise
    eye shadow, bright flags) and emit dense bristle brushes at their EXACT
    target color so they survive the underpainting averaging.

    Pop-art and poster-like targets have small but crucial accent colors that
    get merged into neighbors by the default underpainting. This pass runs
    AFTER the main pipeline to restore those accents.

    args: {
      chroma_threshold: int = 90,     # per-pixel max-min across RGB
      min_region: int = 30,            # skip tiny speckle noise
      max_regions: int = 40,
      stroke_density: int = 4,          # dabs per 100 region pixels
      alpha: float = 0.92,
      stroke_width: int = 6,
      seed: int = 0,
    }
    Returns: {strokes, n, regions_found}
    """
    from scipy.ndimage import label
    import random as _random
    arr = _target_array().astype(int)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    threshold = int(args.get("chroma_threshold", 90))
    min_region = int(args.get("min_region", 30))
    max_regions = int(args.get("max_regions", 40))
    stroke_density = int(args.get("stroke_density", 4))
    alpha = float(args.get("alpha", 0.92))
    stroke_width = int(args.get("stroke_width", 6))
    _random.seed(int(args.get("seed", 0)))

    mask = chroma > threshold
    if not mask.any():
        return {"strokes": [], "n": 0, "regions_found": 0}
    labels, n = label(mask)
    strokes: list[dict] = []
    regions_info = []
    for lbl in range(1, n + 1):
        region = labels == lbl
        pc = int(region.sum())
        if pc < min_region:
            continue
        ys, xs = np.where(region)
        # Use median color (robust to edge outliers) rather than mean
        reg_pixels = arr[region]
        mr = int(np.median(reg_pixels[:, 0]))
        mg = int(np.median(reg_pixels[:, 1]))
        mb = int(np.median(reg_pixels[:, 2]))
        color = "#%02x%02x%02x" % (mr, mg, mb)
        regions_info.append((pc, ys, xs, color))
    # Sort by size desc, keep top-N
    regions_info.sort(reverse=True, key=lambda t: t[0])
    regions_info = regions_info[:max_regions]
    for pc, ys, xs, color in regions_info:
        # Place stroke_density × pc/100 small brushes inside the region
        n_strokes = max(3, int(stroke_density * pc / 100))
        for _ in range(n_strokes):
            idx = _random.randint(0, len(ys) - 1)
            cy = int(ys[idx]); cx = int(xs[idx])
            # Short brush centered on this pixel, bristle texture
            angle = _random.uniform(0, math.pi)
            hw = stroke_width
            dx = math.cos(angle) * hw
            dy = math.sin(angle) * hw
            strokes.append({
                "type": "brush",
                "points": [[int(cx - dx), int(cy - dy)],
                            [int(cx), int(cy)],
                            [int(cx + dx), int(cy + dy)]],
                "color": color,
                "width": stroke_width,
                "alpha": alpha,
                "texture": "bristle",
            })
    return {"strokes": strokes, "n": len(strokes),
             "regions_found": len(regions_info)}


def tool_face_detail_plan(args: dict) -> dict:
    """v17.5: painterly face-detail — direction-aware BRISTLE brush strokes
    (not dabs). Gives eye/nose/mouth features a painted quality that blends
    with the rest of the canvas instead of looking like pasted pixels.

    Scoped to face bounding boxes (optionally padded). For each high-error
    cell inside the box: emit a small bristle brush stroke oriented
    perpendicular to the local gradient (along-the-form), same way the
    v16.2 sculpt_correction pass works.

    args: {
      faces: list[{x,y,w,h}],
      padding: float = 0.15,
      cell_size: int = 4,              # 4px cells → brush fits 5-6px stroke
      error_threshold: float = 15,
      max_strokes_per_face: int = 600,
      alpha: float = 0.78,
      stroke_width: int = 4,
      seed: int = 0,
    }
    Returns: {strokes, n, per_face: [{x,y,w,h,n_strokes,source}]}
    """
    import random as _random
    faces = args.get("faces") or []
    if not faces:
        return {"strokes": [], "n": 0, "per_face": []}
    padding = float(args.get("padding", 0.15))
    cell_size = int(args.get("cell_size", 4))
    error_threshold = float(args.get("error_threshold", 15))
    max_per_face = int(args.get("max_strokes_per_face", 600))
    alpha = float(args.get("alpha", 0.78))
    stroke_width = int(args.get("stroke_width", 4))
    _random.seed(int(args.get("seed", 0)))

    arr = _target_array()
    state = json.loads(_viewer_get("/api/state"))
    if not state.get("canvas_png"):
        return {"error": "no canvas yet"}
    canvas_bytes = base64.b64decode(state["canvas_png"])
    canvas_arr = np.asarray(Image.open(_io.BytesIO(canvas_bytes)).convert("RGB")).astype(np.float32)
    target_arr = arr.astype(np.float32)
    error_map = np.abs(target_arr - canvas_arr).mean(axis=2)

    # Direction field from target gradient (like sculpt v16.2)
    from scipy.ndimage import sobel
    t_gray = target_arr.mean(axis=2).astype(np.float32)
    gx_arr = sobel(t_gray, axis=1)
    gy_arr = sobel(t_gray, axis=0)

    H, W = arr.shape[:2]

    all_strokes: list[dict] = []
    per_face: list[dict] = []
    for fi, face in enumerate(faces):
        x0 = face["x"]; y0 = face["y"]
        w = face["w"]; h = face["h"]
        px = int(w * padding); py = int(h * padding)
        fx0 = max(0, x0 - px); fy0 = max(0, y0 - py)
        fx1 = min(W, x0 + w + px); fy1 = min(H, y0 + h + py)
        candidates = []
        for cy in range(fy0, fy1, cell_size):
            for cx in range(fx0, fx1, cell_size):
                y1 = min(fy1, cy + cell_size)
                x1 = min(fx1, cx + cell_size)
                err = float(error_map[cy:y1, cx:x1].mean())
                if err >= error_threshold:
                    candidates.append((err, cy + cell_size // 2, cx + cell_size // 2))
        candidates.sort(reverse=True)
        candidates = candidates[:max_per_face]
        face_strokes = []
        for err, mid_y, mid_x in candidates:
            mid_y = min(H - 1, max(0, mid_y))
            mid_x = min(W - 1, max(0, mid_x))
            r, g, b = target_arr[mid_y, mid_x]
            color = "#%02x%02x%02x" % (int(r), int(g), int(b))
            # Direction-aware angle (along-the-form)
            gxv = float(gx_arr[mid_y, mid_x])
            gyv = float(gy_arr[mid_y, mid_x])
            mag = (gxv * gxv + gyv * gyv) ** 0.5
            if mag < 3.0:
                angle = _random.uniform(0, math.pi)
            else:
                angle = math.atan2(gyv, gxv) + math.pi / 2
            angle += _random.uniform(-0.20, 0.20)
            hw = int(cell_size * 1.2)
            dx = math.cos(angle) * hw
            dy = math.sin(angle) * hw
            # Bristle brush with slight jitter for painterly feel
            face_strokes.append({
                "type": "brush",
                "points": [[int(mid_x - dx), int(mid_y - dy)],
                            [int(mid_x), int(mid_y)],
                            [int(mid_x + dx), int(mid_y + dy)]],
                "color": color,
                "width": max(stroke_width, int(cell_size * 0.9)),
                "alpha": alpha,
                "texture": "bristle",
            })
        all_strokes.extend(face_strokes)
        per_face.append({"x": x0, "y": y0, "w": w, "h": h,
                         "n_strokes": len(face_strokes),
                         "source": face.get("source", "?")})
    return {"strokes": all_strokes, "n": len(all_strokes), "per_face": per_face}


def tool_sculpt_correction_plan(args: dict) -> dict:
    """v14: dense per-cell error correction. For each small cell with high
    error between canvas and target, emit a small brush stroke with the
    target color to pull the canvas toward the target.

    Unlike critique_correct which touches only top-N worst cells, this
    produces hundreds of corrections across the image, giving anatomy
    detail the coarse underpainting can't reach.

    args: {
      cell_size: int = 8,           # smaller = more detail, more strokes
      error_threshold: float = 25,  # per-channel abs error to trigger
      mask_path: str|None,          # restrict to saliency-positive cells
      mask_threshold: float = 0.25,
      max_strokes: int|"auto" = "auto",  # cap
      stroke_width: int = 4,
      alpha: float = 0.70,
      seed: int = 0,
    }
    Returns: {strokes, n, high_error_cells, total_lit_cells}
    """
    import random as _random
    arr = _target_array()
    state = json.loads(_viewer_get("/api/state"))
    if not state.get("canvas_png"):
        return {"error": "no canvas"}
    canvas_bytes = base64.b64decode(state["canvas_png"])
    canvas_arr = np.asarray(Image.open(_io.BytesIO(canvas_bytes)).convert("RGB")).astype(np.float32)
    target_arr = arr.astype(np.float32)

    cell_size = int(args.get("cell_size", 8))
    error_threshold = float(args.get("error_threshold", 25))
    stroke_width = int(args.get("stroke_width", 4))
    alpha = float(args.get("alpha", 0.70))
    seed = int(args.get("seed", 0))
    _random.seed(seed)

    mask = _load_mask(args.get("mask_path"))
    mask_threshold = float(args.get("mask_threshold", 0.25))

    # Per-cell abs error summed across RGB
    error_map = np.abs(target_arr - canvas_arr).mean(axis=2)

    max_arg = args.get("max_strokes", "auto")

    strokes: list[dict] = []
    candidate_cells = []
    C_H, C_W = target_arr.shape[:2]
    rows = C_H // cell_size
    cols = C_W // cell_size
    for j in range(rows):
        for i in range(cols):
            y0 = j * cell_size; y1 = y0 + cell_size
            x0 = i * cell_size; x1 = x0 + cell_size
            if mask is not None:
                m_slice = mask[y0:y1, x0:x1]
                if m_slice.mean() < mask_threshold:
                    continue
            err = float(error_map[y0:y1, x0:x1].mean())
            if err < error_threshold:
                continue
            candidate_cells.append((err, j, i))
    # Sort by error desc, cap if needed
    candidate_cells.sort(reverse=True, key=lambda t: t[0])
    if max_arg == "auto":
        auto_budget = min(800, max(100, len(candidate_cells)))
    else:
        auto_budget = int(max_arg)
    candidate_cells = candidate_cells[:auto_budget]

    # v16.1: Direction-aware sculpt. Hard-horizontal was creating a visible
    # horizontal-stripe artifact. Now strokes follow the TARGET's local
    # gradient direction (perpendicular to edges = along the form, like
    # real painters). Cells ≤ 3px still use dabs (directionless, precise).
    from scipy.ndimage import sobel
    target_gray = target_arr.mean(axis=2).astype(np.float32)
    gx_arr = sobel(target_gray, axis=1)
    gy_arr = sobel(target_gray, axis=0)
    use_dab = cell_size <= 3

    def _stroke_angle(cy, cx):
        """Along-form direction (perpendicular to gradient) at (cy, cx)."""
        gx = float(gx_arr[cy, cx])
        gy = float(gy_arr[cy, cx])
        mag = (gx * gx + gy * gy) ** 0.5
        if mag < 3.0:
            # Low gradient — use varied angle per stroke index for diversity
            return _random.uniform(0, math.pi)
        return math.atan2(gy, gx) + math.pi / 2  # perpendicular

    for err, j, i in candidate_cells:
        y0 = j * cell_size; y1 = y0 + cell_size
        x0 = i * cell_size; x1 = x0 + cell_size
        cy = (y0 + y1) // 2
        cx = (x0 + x1) // 2
        cy = max(0, min(target_arr.shape[0] - 1, cy))
        cx = max(0, min(target_arr.shape[1] - 1, cx))
        r, g, b = target_arr[cy, cx]
        color = "#%02x%02x%02x" % (int(r), int(g), int(b))
        if use_dab:
            size = max(2, cell_size)
            strokes.append({
                "type": "dab",
                "x": int(cx), "y": int(cy),
                "w": size, "h": size,
                "angle": 0.0,
                "color": color,
                "alpha": alpha,
            })
        else:
            # v16.2: longer stroke along the form + bristle texture → matches
            # the painterly feel of the underpainting instead of looking like
            # a tight grid of smooth ribbons.
            angle = _stroke_angle(cy, cx)
            # Add per-stroke angle jitter so aligned regions don't form
            # an obvious hatching pattern
            angle += _random.uniform(-0.25, 0.25)
            hx = int(cell_size * 1.2)  # reach past the cell into neighbors
            dx = math.cos(angle) * hx
            dy = math.sin(angle) * hx
            pts = [[int(cx - dx), int(cy - dy)],
                   [int(cx), int(cy)],
                   [int(cx + dx), int(cy + dy)]]
            strokes.append({
                "type": "brush",
                "points": pts,
                "color": color,
                "width": max(stroke_width, int(cell_size * 0.9)),
                "alpha": alpha,
                "texture": "bristle",   # v16.2: match underpainting aesthetic
            })
    return {
        "strokes": strokes,
        "n": len(strokes),
        "high_error_cells": len(candidate_cells),
        "total_lit_cells": None if mask is None else int((mask > mask_threshold).sum()),
    }


# ============================================================================
# Painterly contour helpers — pure functions used by the painterly emission
# branch of tool_contour_stroke_plan. See docs/superpowers/specs/
# 2026-04-22-painterly-contours-design.md.
# ============================================================================


def _arc_length(path):
    return sum(
        ((path[i + 1][0] - path[i][0]) ** 2 +
         (path[i + 1][1] - path[i][1]) ** 2) ** 0.5
        for i in range(len(path) - 1)
    )


def _slice_path(path, t_start: float, t_end: float):
    """Return the sub-path spanning [t_start, t_end] of the total arc length.

    path: list of (x, y) tuples. t_start, t_end in [0, 1].
    Returns a new list; inputs not mutated. Guarantees >= 2 points when
    t_end > t_start and input has >= 2 points.
    """
    t_start = max(0.0, min(1.0, t_start))
    t_end = max(t_start, min(1.0, t_end))
    if len(path) < 2:
        return list(path)
    total = _arc_length(path)
    if total <= 0:
        return list(path)
    target_start = t_start * total
    target_end = t_end * total
    out = []
    walked = 0.0
    for i in range(len(path) - 1):
        seg_len = ((path[i + 1][0] - path[i][0]) ** 2 +
                   (path[i + 1][1] - path[i][1]) ** 2) ** 0.5
        seg_start = walked
        seg_end = walked + seg_len
        if seg_end < target_start:
            walked = seg_end
            continue
        if seg_start > target_end:
            break
        a = max(target_start, seg_start)
        b = min(target_end, seg_end)
        if seg_len <= 0:
            walked = seg_end
            continue
        fa = (a - seg_start) / seg_len
        fb = (b - seg_start) / seg_len
        pa = (path[i][0] + (path[i + 1][0] - path[i][0]) * fa,
              path[i][1] + (path[i + 1][1] - path[i][1]) * fa)
        pb = (path[i][0] + (path[i + 1][0] - path[i][0]) * fb,
              path[i][1] + (path[i + 1][1] - path[i][1]) * fb)
        if not out:
            out.append(pa)
        out.append(pb)
        walked = seg_end
    if len(out) < 2:
        # Guarantee 2 points even for very-short ranges
        mid_t = (t_start + t_end) / 2.0
        target_mid = mid_t * total
        walked = 0.0
        for i in range(len(path) - 1):
            seg_len = ((path[i + 1][0] - path[i][0]) ** 2 +
                       (path[i + 1][1] - path[i][1]) ** 2) ** 0.5
            if walked + seg_len >= target_mid:
                fa = (target_mid - walked) / max(seg_len, 1e-9)
                p_mid = (path[i][0] + (path[i + 1][0] - path[i][0]) * fa,
                         path[i][1] + (path[i + 1][1] - path[i][1]) * fa)
                return [path[i], p_mid, path[i + 1]]
            walked += seg_len
        return list(path[:2])
    return out


def _jitter_perpendicular(path, max_px: float, rng):
    """Offset each interior point by up to max_px perpendicular to local direction.

    Endpoints stay at their original coordinates. Returns a new list.
    `rng` is a random.Random instance (for determinism).
    """
    import math as _m
    if len(path) < 2:
        return list(path)
    out = [tuple(path[0])]
    for i in range(1, len(path) - 1):
        prev = path[i - 1]
        nxt = path[i + 1]
        dx = nxt[0] - prev[0]
        dy = nxt[1] - prev[1]
        length = _m.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        offset = rng.uniform(-max_px, max_px)
        out.append((path[i][0] + nx * offset, path[i][1] + ny * offset))
    out.append(tuple(path[-1]))
    return out


def _tapered_width(base_width: int, position: float, seed: int) -> int:
    """Width at a given path position [0, 1], narrower at ends.

    Uses sin(pi*position) curve (0.5 at ends, 1.0 at middle) + a small
    per-seed jitter. Returns an integer >= 1, capped at base_width * 2.
    """
    import math as _m
    import random as _r
    curve = 0.5 + 0.5 * _m.sin(_m.pi * position)
    r = _r.Random(seed)
    jitter = 1.0 + r.uniform(-0.15, 0.15)
    w = int(round(base_width * curve * jitter))
    return max(1, min(w, base_width * 2))


def _fetch_current_canvas():
    """Fetch /api/state -> canvas PNG -> RGB ndarray. None on any failure.

    Logs a single-line warning to stderr on failure so the fallback
    doesn't happen silently.
    """
    try:
        import urllib.request
        import json as _json
        import base64 as _base64
        import io as _io
        from PIL import Image as _Image
        with urllib.request.urlopen("http://127.0.0.1:8080/api/state",
                                     timeout=5) as r:
            data = _json.loads(r.read())
        png_b64 = data.get("canvas_png")
        if not png_b64:
            return None
        img = _Image.open(_io.BytesIO(_base64.b64decode(png_b64))).convert("RGB")
        return np.asarray(img)
    except Exception as _exc:
        print(f"[contour] painterly: canvas fetch failed, "
              f"falling back to target: {_exc}", file=sys.stderr)
        return None


def _sample_canvas_rgb(arr, point) -> str:
    """Nearest-pixel color read from `arr` (HxWx3 uint8) at `(x, y)`. Hex."""
    x, y = point
    h = arr.shape[0]
    w = arr.shape[1]
    xi = int(max(0, min(w - 1, x)))
    yi = int(max(0, min(h - 1, y)))
    r, g, b = arr[yi, xi][:3]
    return "#%02x%02x%02x" % (int(r), int(g), int(b))


def _painterly_contour_strokes(simplified_path, current_canvas,
                                 base_width: int, args: dict, rng):
    """Emit 3-8 overlapping short brush strokes that follow simplified_path.

    Each stroke covers painterly_segment_coverage of the path, has
    tapered width, per-stroke alpha in painterly_alpha_range, perpendicular
    position jitter in painterly_position_jitter_px, and color sampled
    from current_canvas at the stroke's midpoint.
    """
    if len(simplified_path) < 2:
        return []
    count_arg = args.get("painterly_strokes_per_component", "auto")
    if count_arg == "auto":
        n_strokes = max(2, min(8, len(simplified_path) // 3))
    else:
        n_strokes = max(1, int(count_arg))

    alpha_lo, alpha_hi = args.get("painterly_alpha_range", [0.30, 0.55])
    pos_jitter_lo, pos_jitter_hi = args.get("painterly_position_jitter_px",
                                             [1.0, 2.5])
    cov_lo, cov_hi = args.get("painterly_segment_coverage", [0.35, 0.55])

    out = []
    for i in range(n_strokes):
        t_start = (i / n_strokes) * 0.45
        t_end = min(1.0, t_start + rng.uniform(cov_lo, cov_hi))
        segment = _slice_path(simplified_path, t_start, t_end)
        if len(segment) < 2:
            continue
        jitter_px = rng.uniform(pos_jitter_lo, pos_jitter_hi)
        jittered = _jitter_perpendicular(segment, jitter_px, rng)
        mid_idx = len(jittered) // 2
        mid_pt = jittered[mid_idx]
        color = _sample_canvas_rgb(current_canvas, mid_pt)
        width = _tapered_width(base_width, position=0.5,
                                seed=rng.randint(0, 10 ** 6))
        alpha = rng.uniform(alpha_lo, alpha_hi)
        out.append({
            "type": "brush",
            "texture": "bristle",
            "points": [[int(x), int(y)] for x, y in jittered],
            "color": color,
            "width": int(width),
            "alpha": float(alpha),
        })
    return out
