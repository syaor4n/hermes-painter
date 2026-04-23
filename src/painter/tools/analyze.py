"""Target analysis tools: features, edges, gradients, segmentation, faces.

These handlers read the current target (via ``_common._target_array``) and
extract structural information that the planning tools can consume.
``tool_analyze_target`` is the one-shot summary that orchestrates the rest
plus a couple of canvas-level helpers.
"""
from __future__ import annotations

import base64
import io as _io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from ._common import (
    _DUMP_DIR,
    _SALIENCY_PATH,
    _SCRIPTS_DIR,
    _target_array,
    _viewer_get,
)


def tool_edge_map(args: dict) -> dict:
    """Detect edges in the target via Sobel operator. Save a visualizable PNG
    AND return high-density edge regions (bounding boxes of likely "subjects").

    args: {threshold: float (percentile, default 80)}
    Returns: {path, subject_region: {x,y,w,h}, edge_density: float (0..1)}
    """
    from scipy.ndimage import sobel
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)
    mag = np.hypot(gx, gy)
    # Normalize & threshold
    if mag.max() > 0:
        mag_norm = (mag / mag.max() * 255).astype(np.uint8)
    else:
        mag_norm = np.zeros_like(gray, dtype=np.uint8)
    thresh_pct = float(args.get("threshold", 80))
    cutoff = np.percentile(mag_norm, thresh_pct)
    binary = (mag_norm > cutoff).astype(np.uint8) * 255

    # Save visualization
    from PIL import Image as _PI
    edge_img = _PI.fromarray(mag_norm, mode="L")
    path = _DUMP_DIR / "painter_edges.png"
    edge_img.save(path, format="PNG")

    # Find dense-edge region (subject)
    # Downsample to 16x16 grid, find cell with highest edge density
    h, w = binary.shape
    cell = 32
    best_y, best_x, best_d = 0, 0, -1
    for gy_ in range(0, h - cell, cell // 2):
        for gx_ in range(0, w - cell * 3, cell // 2):
            # Use a 3-cell-wide window to find the densest subject region
            region = binary[gy_:gy_ + cell * 3, gx_:gx_ + cell * 3]
            d = float(region.mean())
            if d > best_d:
                best_d = d
                best_y = gy_
                best_x = gx_

    subject = {
        "x": int(best_x), "y": int(best_y),
        "w": cell * 3, "h": cell * 3,
        "edge_density": round(best_d / 255, 3),
    }
    global_edge_density = float((binary.mean() / 255))
    return {
        "path": str(path),
        "subject_region": subject,
        "edge_density": round(global_edge_density, 3),
    }


def tool_gradient_field(_args: dict) -> dict:
    """Compute dominant stroke direction per quadrant of the target.

    Returns angles in radians (0 = horizontal, pi/2 = vertical) plus a "coherence"
    score indicating how aligned gradients are locally. Low coherence = random/mixed,
    high coherence = strongly directional (e.g. trees, buildings).
    """
    from scipy.ndimage import sobel
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)

    h, w = gray.shape
    # Quadrants + full
    def analyze_region(y0, y1, x0, x1):
        rx = gx[y0:y1, x0:x1]
        ry = gy[y0:y1, x0:x1]
        # Structure tensor accumulate
        Jxx = (rx * rx).sum()
        Jyy = (ry * ry).sum()
        Jxy = (rx * ry).sum()
        # Dominant direction: eigenvector of [[Jxx,Jxy],[Jxy,Jyy]]
        trace = Jxx + Jyy
        det = Jxx * Jyy - Jxy * Jxy
        disc = max(0.0, trace * trace / 4 - det)
        lam1 = trace / 2 + disc ** 0.5
        lam2 = trace / 2 - disc ** 0.5
        # Eigen angle of dominant direction (perpendicular to gradient = stroke direction)
        # Edge direction is perpendicular to gradient → stroke runs ALONG edges
        if abs(Jxy) < 1e-6:
            angle_grad = 0.0 if Jxx > Jyy else np.pi / 2
        else:
            angle_grad = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)
        # Stroke direction is 90° off from gradient direction
        stroke_angle = angle_grad + np.pi / 2
        # Coherence: how much more dominant is one direction vs the other
        coherence = 0.0 if trace < 1e-6 else float((lam1 - lam2) / (lam1 + lam2 + 1e-9))
        return {
            "angle_rad": float(stroke_angle),
            "angle_deg": float(np.degrees(stroke_angle) % 180),
            "coherence": round(coherence, 3),
        }

    quadrants = {
        "top_left": analyze_region(0, h // 2, 0, w // 2),
        "top_right": analyze_region(0, h // 2, w // 2, w),
        "bottom_left": analyze_region(h // 2, h, 0, w // 2),
        "bottom_right": analyze_region(h // 2, h, w // 2, w),
        "global": analyze_region(0, h, 0, w),
    }
    # Better classification: if any quadrant has strong directional coherence,
    # honor that. Otherwise check global. Only fall back to "random" if every
    # quadrant is weak.
    def classify_angle(a_deg):
        return "vertical" if 60 < a_deg < 120 else "horizontal"

    strong_coh = 0.15
    strong_votes = {"horizontal": 0, "vertical": 0}
    for q_name, q in quadrants.items():
        if q_name == "global":
            continue
        if q["coherence"] >= strong_coh:
            strong_votes[classify_angle(q["angle_deg"])] += 1

    if strong_votes["vertical"] > strong_votes["horizontal"] and strong_votes["vertical"] >= 2:
        suggested = "vertical"
    elif strong_votes["horizontal"] > strong_votes["vertical"] and strong_votes["horizontal"] >= 2:
        suggested = "horizontal"
    else:
        # Fallback 1: global direction if any coherence
        gc = quadrants["global"]["coherence"]
        ga = quadrants["global"]["angle_deg"]
        if gc >= 0.08:
            suggested = classify_angle(ga)
        else:
            # Fallback 2: highest-coherence quadrant regardless of threshold
            non_global = [(n, q) for n, q in quadrants.items() if n != "global"]
            best = max(non_global, key=lambda nq: nq[1]["coherence"])
            if best[1]["coherence"] >= 0.07:
                suggested = classify_angle(best[1]["angle_deg"])
            else:
                suggested = "random"

    return {
        "quadrants": quadrants,
        "suggested_direction": suggested,
        "quadrant_votes": strong_votes,
    }


# -----------------------------------------------------------------------------
# v8 additions — saliency, direction field grid, highlights
# -----------------------------------------------------------------------------


def tool_saliency_mask(args: dict) -> dict:
    """Compute a foreground/subject mask for the current target.

    Simple, zero-dep saliency: per-pixel local contrast (Laplacian² smoothed)
    combined with a mild center bias. Produces a smooth 0-255 mask where high
    values = sharp/textured areas (usually the subject), low = blurred fallback.

    Saves the mask to /tmp/painter_saliency.png (readable by other tools via
    `mask_path` arg). Also returns a tight bbox around the subject for use with
    `focus_box` in contour_stroke_plan.

    args: {
      blur_sigma: float = 2.0,     # smoothing of the variance map
      center_bias: float = 0.2,    # 0..1, how much to upweight the image center
      threshold: float = 0.35,     # 0..1 foreground threshold for bbox computation
    }
    Returns: {path, bbox, fg_fraction, separability}
      separability: 0..1, higher = cleaner fg/bg split (use to decide whether to rely on mask)
    """
    from scipy.ndimage import gaussian_filter, laplace
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32) / 255.0
    # Local contrast via Laplacian². Bigger sigma → subject-scale (not pixel noise).
    blur_sigma = float(args.get("blur_sigma", 8.0))
    lap = laplace(gray)
    variance = gaussian_filter(lap * lap, sigma=blur_sigma)
    # Percentile-based normalization (robust to outliers) + gamma boost
    p5 = float(np.percentile(variance, 5))
    p95 = float(np.percentile(variance, 95))
    v = np.clip((variance - p5) / (p95 - p5 + 1e-9), 0, 1)
    # Gamma < 1 boosts mid values so the subject is more visible
    v = v ** 0.5
    # Add center bias (Gaussian-like falloff from center)
    cb = float(args.get("center_bias", 0.15))
    if cb > 0:
        h, w = v.shape
        yy, xx = np.mgrid[0:h, 0:w]
        cy, cx = h / 2, w / 2
        r = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5
        r_max = (cx * cx + cy * cy) ** 0.5
        center = np.clip(1.0 - (r / r_max), 0, 1) ** 2
        v = v * (1 - cb) + center * cb
        v = np.clip(v, 0, 1)
    # Threshold
    threshold = float(args.get("threshold", 0.3))
    fg = v > threshold
    fg_fraction = float(fg.mean())
    # Bbox
    if fg.any():
        ys, xs = np.where(fg)
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        bbox = [x0, y0, x1 - x0 + 1, y1 - y0 + 1]
    else:
        bbox = [0, 0, arr.shape[1], arr.shape[0]]
    # Separability: how well threshold splits the histogram
    # (std of v) — higher = more contrasted mask
    separability = float(v.std())
    # Save PNG
    mask_u8 = (v * 255).clip(0, 255).astype(np.uint8)
    Image.fromarray(mask_u8).save(str(_SALIENCY_PATH))
    return {
        "path": str(_SALIENCY_PATH),
        "bbox": bbox,
        "fg_fraction": round(fg_fraction, 3),
        "separability": round(separability, 3),
    }


def tool_direction_field_grid(args: dict) -> dict:
    """Per-cell dominant stroke direction (local structure tensor).

    Returns a grid_size × grid_size array of {angle, coherence} dicts, where
    `angle` is the stroke direction in radians (the eigenvector of the
    structure tensor, perpendicular to the gradient = along edges), and
    `coherence` is how strongly aligned gradients are in that cell (0..1).

    Use with `layered_underpainting` to vary stroke direction per cell —
    fur, plumes, fabric folds, foliage all get their local orientation.

    args: {
      grid_size: int = 16,          # cells per side
      coherence_floor: float = 0.05, # cells below this get 'random' direction
    }
    Returns: {grid: [[{angle, coherence, mode}, ...], ...], grid_size}
      mode: 'angle' if coherence >= floor, else 'random'
    """
    from scipy.ndimage import sobel
    arr = _target_array()
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)

    grid_size = int(args.get("grid_size", 16))
    coherence_floor = float(args.get("coherence_floor", 0.05))

    h, w = gray.shape
    cell_h, cell_w = h // grid_size, w // grid_size
    grid = []
    for j in range(grid_size):
        row = []
        for i in range(grid_size):
            y0, y1 = j * cell_h, (j + 1) * cell_h
            x0, x1 = i * cell_w, (i + 1) * cell_w
            rx = gx[y0:y1, x0:x1]
            ry = gy[y0:y1, x0:x1]
            Jxx = float((rx * rx).sum())
            Jyy = float((ry * ry).sum())
            Jxy = float((rx * ry).sum())
            trace = Jxx + Jyy
            det = Jxx * Jyy - Jxy * Jxy
            disc = max(0.0, trace * trace / 4 - det)
            lam1 = trace / 2 + disc ** 0.5
            lam2 = trace / 2 - disc ** 0.5
            coherence = (lam1 - lam2) / (lam1 + lam2 + 1e-9)
            # Gradient direction
            grad_angle = math.atan2(Jxy, (Jxx - lam2) if Jxx > Jyy else (Jxy))
            if Jxy == 0 and Jxx >= Jyy:
                grad_angle = 0.0
            elif Jxy == 0:
                grad_angle = math.pi / 2
            # Stroke direction is perpendicular to gradient
            stroke_angle = grad_angle + math.pi / 2
            mode = "angle" if coherence >= coherence_floor else "random"
            row.append({
                "angle": round(stroke_angle, 4),
                "coherence": round(float(coherence), 4),
                "mode": mode,
            })
        grid.append(row)
    return {"grid": grid, "grid_size": grid_size, "cell_w": cell_w, "cell_h": cell_h}


_SEGMENT_PATH = Path("/tmp/painter_segments.png")


def tool_segment_regions(args: dict) -> dict:
    """SLIC super-pixel segmentation of the target.

    Produces a label map (PNG saved to /tmp/painter_segments.png where each
    pixel's intensity = region id × 8) + per-region metadata that callers can
    use to paint each region with its own palette, direction, and density.

    args: {
      n_segments: int = 8,       # target number of regions
      compactness: float = 10.0, # SLIC shape-vs-color trade-off
      sigma: float = 1.0,
    }

    Returns: {
      path,
      n_regions,
      regions: [{
        id, centroid: [x, y], bbox: [x, y, w, h],
        pixel_count, mean_rgb, dominant_angle, coherence,
        palette: [[r,g,b], ...]  # top 3 colors in the region
      }, ...]
    }
    """
    from skimage.segmentation import slic
    from scipy.ndimage import sobel
    arr = _target_array()
    n_segments = int(args.get("n_segments", 8))
    compactness = float(args.get("compactness", 10.0))
    sigma = float(args.get("sigma", 1.0))
    labels = slic(arr, n_segments=n_segments, compactness=compactness,
                  sigma=sigma, channel_axis=-1, start_label=0)
    n_regions = int(labels.max()) + 1
    # Save the RAW label map as 16-bit PNG so paint_lib can roundtrip region ids
    # (8-bit would clamp at 256 regions; 16-bit covers 65k)
    Image.fromarray(labels.astype(np.uint16)).save(str(_SEGMENT_PATH))

    # Pre-compute gradients for dominant angle per region
    gray = arr.mean(axis=2).astype(np.float32)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)

    regions = []
    for rid in range(n_regions):
        mask = labels == rid
        pc = int(mask.sum())
        if pc == 0:
            continue
        ys, xs = np.where(mask)
        cy = float(ys.mean())
        cx = float(xs.mean())
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        # Mean color
        pixels = arr[mask]
        mean_rgb = pixels.mean(axis=0).astype(int).tolist()

        # Dominant angle via structure tensor on this region only
        mrx = gx[mask]
        mry = gy[mask]
        Jxx = float((mrx * mrx).sum())
        Jyy = float((mry * mry).sum())
        Jxy = float((mrx * mry).sum())
        trace = Jxx + Jyy
        det = Jxx * Jyy - Jxy * Jxy
        disc = max(0.0, trace * trace / 4 - det)
        lam1 = trace / 2 + disc ** 0.5
        lam2 = trace / 2 - disc ** 0.5
        coherence = (lam1 - lam2) / (lam1 + lam2 + 1e-9) if (lam1 + lam2) > 0 else 0.0
        if abs(Jxy) < 1e-6:
            grad_angle = 0.0 if Jxx >= Jyy else math.pi / 2
        else:
            grad_angle = math.atan2(2 * Jxy, Jxx - Jyy) / 2
        stroke_angle = grad_angle + math.pi / 2

        # #19: Region palette via LAB-space quantization (perceptually uniform).
        # Convert pixels to LAB, bin at perceptual quanta, take top-3 cluster
        # means and convert back to RGB.
        from skimage.color import rgb2lab, lab2rgb
        lab_pixels = rgb2lab((pixels / 255.0).reshape(-1, 1, 3)).reshape(-1, 3)
        # Quantize LAB: L at 10 steps, a/b at 10 each — perceptually sensible
        lab_q = np.zeros_like(lab_pixels)
        lab_q[:, 0] = np.round(lab_pixels[:, 0] / 10) * 10
        lab_q[:, 1] = np.round(lab_pixels[:, 1] / 10) * 10
        lab_q[:, 2] = np.round(lab_pixels[:, 2] / 10) * 10
        # Pack into hashable key
        keys = lab_q[:, 0].astype(int) * 100000 + lab_q[:, 1].astype(int) * 100 + lab_q[:, 2].astype(int)
        unique, counts = np.unique(keys, return_counts=True)
        top_idx = np.argsort(-counts)[:3]
        palette = []
        for t in top_idx.tolist():
            # Compute the mean RGB of pixels whose key matches
            match = keys == int(unique[t])
            cluster_rgb = pixels[match].mean(axis=0)
            palette.append([int(cluster_rgb[0]), int(cluster_rgb[1]), int(cluster_rgb[2])])

        regions.append({
            "id": int(rid),
            "centroid": [round(cx, 1), round(cy, 1)],
            "bbox": [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
            "pixel_count": pc,
            "mean_rgb": mean_rgb,
            "dominant_angle": round(float(stroke_angle), 4),
            "coherence": round(float(coherence), 4),
            "palette": palette,
        })

    # Sort regions by pixel_count descending so the largest come first
    regions.sort(key=lambda r: -r["pixel_count"])
    return {
        "path": str(_SEGMENT_PATH),
        "n_regions": len(regions),
        "regions": regions,
    }


def tool_find_features(_args: dict) -> dict:
    """Auto-detect salient features of the target.

    Uses compact-bright-spot heuristics: a "sun" is a LOCALLY bright disc
    whose core is much brighter than its surrounding ring. A "horizon" is
    the row where brightness drops sharply from sky to water. This avoids
    the common pitfall of a global-argmax finding a cloud instead of a sun.
    """
    arr = _target_array()
    h, w = arr.shape[:2]
    gray = arr.mean(axis=2)

    # --- Sun disc: core-vs-ring contrast, not global max ---
    # For each candidate center, compare 9x9 core brightness to 25x25 ring.
    sun_best = {"x": w // 2, "y": h // 2, "score": -1.0, "brightness": 0.0, "rgb": [0, 0, 0]}
    for y in range(20, h - 20, 3):
        for x in range(20, w - 20, 3):
            core = float(gray[max(0, y-4):y+5, max(0, x-4):x+5].mean())
            ring = float(gray[max(0, y-12):y+13, max(0, x-12):x+13].mean())
            contrast = core - ring
            if contrast < 10:
                continue
            score = contrast * core
            if score > sun_best["score"]:
                sun_best = {
                    "x": int(x), "y": int(y), "score": float(score),
                    "brightness": float(core),
                    "rgb": arr[y, x].astype(int).tolist(),
                }

    # --- Horizon: strongest row-wise negative derivative in middle band ---
    row_mean = gray.mean(axis=1)
    # Smooth
    row_smooth = np.convolve(row_mean, np.ones(8) / 8, mode="same")
    deriv = np.diff(row_smooth)
    # Search only middle band — horizons aren't in the top or bottom
    search_start, search_end = 80, h - 120
    search = deriv[search_start:search_end]
    horizon_y = int(search_start + search.argmin()) if len(search) else h // 2
    horizon_drop = float(-deriv[horizon_y]) if horizon_y < len(deriv) else 0.0

    # --- Darkest 64x64 region ---
    darkest_y, darkest_x, darkest_val = 0, 0, 1e9
    for gy in range(0, h - 32, 32):
        for gx in range(0, w - 32, 32):
            block = gray[gy:gy + 64, gx:gx + 64]
            v = float(block.mean())
            if v < darkest_val:
                darkest_val = v
                darkest_y = gy
                darkest_x = gx

    # --- Warmth ---
    warmth = float((arr[..., 0].astype(float) - arr[..., 2].astype(float)).mean())

    # --- Vertical bright axis in the lower half (often: dock, path, reflection column) ---
    lower = gray[h // 2:, :]
    col_means = lower.mean(axis=0)
    # Find the column with highest mean brightness in the lower half
    bright_col_x = int(col_means.argmax())
    bright_col_brightness = float(col_means.max())

    return {
        "sun": {
            "x": sun_best["x"], "y": sun_best["y"],
            "brightness": sun_best["brightness"],
            "rgb": sun_best["rgb"],
        },
        "horizon_y": horizon_y,
        "horizon_drop": horizon_drop,
        "darkest_region": {
            "x": darkest_x, "y": darkest_y, "w": 64, "h": 64,
            "mean_brightness": darkest_val,
        },
        "warmth": warmth,
        "vertical_bright_axis_x": bright_col_x,
        "vertical_bright_axis_brightness": bright_col_brightness,
        "rule_of_thirds": {
            "x": [w // 3, 2 * w // 3],
            "y": [h // 3, 2 * h // 3],
        },
        "canvas_size": [w, h],
    }


def tool_analyze_target(_args: dict) -> dict:
    """One-shot comprehensive target inspection.

    Aggregates classification, palette, features, edges, gradient field into a
    single "painting strategy" dict. This is the recommended first call after
    load_target — it tells the agent everything it needs to pick parameters.
    """
    # Avoid a circular import: canvas.py imports from _common only, but this
    # handler composes with palette / features from there.
    from .canvas import tool_get_palette

    arr = _target_array()
    gray = arr.mean(axis=2)

    # Basic stats
    from painter.image_type import classify as _classify
    # Re-encode target to pass to classify
    img = Image.fromarray(arr)
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    classification = _classify(buf.getvalue())

    # Palette
    palette = tool_get_palette({"n": 8})
    # Features
    features = tool_find_features({})
    # Edges
    edges = tool_edge_map({"threshold": 85})
    # Gradient field
    field = tool_gradient_field({})

    # Suggested parameters based on complexity + direction
    complexity = "high" if edges["edge_density"] > 0.18 else ("medium" if edges["edge_density"] > 0.10 else "low")
    grid_size = 32 if complexity == "high" else (24 if complexity == "medium" else 16)
    direction = field["suggested_direction"]

    # Need fog? Only when the target is genuinely atmospheric:
    # - muted/dark image AND low edge density (few hard edges = foggy look)
    # - OR very low contrast AND low complexity
    # Don't apply fog on high-contrast images just because they're "muted" — it washes details.
    need_fog = False
    fog_hint = None
    is_atmospheric = (
        (classification["type"] == "muted" and edges["edge_density"] < 0.12)
        or (classification["std"] < 25 and complexity == "low")
        or (classification["type"] == "dark" and edges["edge_density"] < 0.10)
    )
    if is_atmospheric:
        need_fog = True
        # Sample fog color from the lighter end of the palette (avoid using the dominant
        # dark color, which would darken everything).
        light_colors = sorted(
            palette["colors"],
            key=lambda c: -(sum(c["rgb"]) / 3),
        )[:3]
        fog_color = light_colors[0]["hex"] if light_colors else "#c0c0c0"
        fog_hint = {
            "direction": "radial" if complexity == "low" else "vertical",
            "fade": 0.6,
            "alpha": 0.15,  # subtler than before
            "color": fog_color,
        }

    return {
        "classification": classification,
        "palette": palette["colors"],
        "features": features,
        "edges": {
            "density": edges["edge_density"],
            "subject_region": edges["subject_region"],
            "map_path": edges["path"],
        },
        "gradient_field": {
            "suggested_direction": field["suggested_direction"],
            "global_angle_deg": field["quadrants"]["global"]["angle_deg"],
            "coherence": field["quadrants"]["global"]["coherence"],
        },
        "strategy": {
            "grid_size": grid_size,
            "direction": direction,
            "complexity": complexity,
            "suggested_fog": fog_hint if need_fog else None,
            "reasoning": (
                f"{complexity} complexity (edge density {edges['edge_density']}), "
                f"{direction} stroke direction (coherence {field['quadrants']['global']['coherence']}). "
                + ("Atmospheric image — use fog." if need_fog else "No fog needed.")
            ),
        },
    }


def tool_detect_faces(args: dict) -> dict:
    """v15: detect human faces in the current target using opencv Haar cascades.

    Returns boxes in CANVAS coordinates (target is assumed already scaled to the
    active canvas via viewer's set_target). Runs both frontal AND profile
    cascades since masterworks (Caravaggio, etc.) often have angled poses.

    args: {
      min_size: int = 20,           # in canvas pixels
      scale_factor: float = 1.08,
      min_neighbors: int = 3,
    }
    Returns: {faces: [{x,y,w,h,confidence,source}], n}
    """
    try:
        import cv2
    except ImportError:
        return {"error": "opencv-python-headless not installed"}
    arr = _target_array()
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    min_size = int(args.get("min_size", 20))
    scale_factor = float(args.get("scale_factor", 1.08))
    min_neighbors = int(args.get("min_neighbors", 3))

    frontal_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    profile_path = cv2.data.haarcascades + "haarcascade_profileface.xml"
    frontal = cv2.CascadeClassifier(frontal_path)
    profile = cv2.CascadeClassifier(profile_path)

    faces: list[dict] = []
    for det_name, cascade in (("frontal", frontal), ("profile", profile)):
        rects = cascade.detectMultiScale(
            gray, scale_factor, min_neighbors, minSize=(min_size, min_size))
        for (x, y, w, h) in rects:
            faces.append({
                "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                "source": det_name,
            })
        # Also flipped (profile detector only catches one direction)
        if det_name == "profile":
            flipped = cv2.flip(gray, 1)
            rects2 = cascade.detectMultiScale(
                flipped, scale_factor, min_neighbors, minSize=(min_size, min_size))
            w_total = gray.shape[1]
            for (x, y, w, h) in rects2:
                faces.append({
                    "x": int(w_total - x - w), "y": int(y), "w": int(w), "h": int(h),
                    "source": "profile_flipped",
                })

    # Merge overlapping boxes (simple IoU-based dedup)
    merged: list[dict] = []
    for f in faces:
        keep = True
        for m in merged:
            ix0 = max(f["x"], m["x"]); iy0 = max(f["y"], m["y"])
            ix1 = min(f["x"] + f["w"], m["x"] + m["w"])
            iy1 = min(f["y"] + f["h"], m["y"] + m["h"])
            inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            area_f = f["w"] * f["h"]
            area_m = m["w"] * m["h"]
            iou = inter / max(1, min(area_f, area_m))
            if iou > 0.4:
                keep = False; break
        if keep:
            merged.append(f)
    return {"faces": merged, "n": len(merged), "canvas_size": arr.shape[:2]}


def tool_critique_canvas(args: dict) -> dict:
    """Run the failure-mode detectors on the current canvas.

    args: {
      last_strokes: list|None     # recent stroke batch enables stroke-level modes
    }

    Returns {findings, verdict, suggested_fixes}. See painter.failures for
    the full taxonomy (TOO_DARK_OUTLINES, SUBJECT_LOST_IN_BG, etc.) and
    the `painter-failure-modes` skill for severity policy.
    """
    from painter import failures as _failures
    state = json.loads(_viewer_get("/api/state"))
    if not state.get("canvas_png") or not state.get("has_target"):
        return {"error": "need both canvas and target set"}
    canvas_bytes = base64.b64decode(state["canvas_png"])
    target_resp = json.loads(_viewer_get("/api/target"))
    target_bytes = base64.b64decode(target_resp["target_png"])
    mask_bytes = None
    if _SALIENCY_PATH.exists():
        mask_bytes = _SALIENCY_PATH.read_bytes()
    return _failures.critique(
        canvas_bytes, target_bytes, mask_bytes=mask_bytes,
        strokes=args.get("last_strokes"),
    )


def tool_list_styles(_args: dict) -> dict:
    """Return the list of styles the painter knows about (built-in + community).

    Each entry includes name, whether it's built-in or community, its
    extends parent (for community), and its parameter vector. The agent
    can use this to discover styles it didn't know about and pass them
    to plan_style_schedule or style_schedule.
    """
    import sys as _sys
    _scripts = _SCRIPTS_DIR
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from paint_lib import morph as _morph

    _BUILTIN = frozenset({"default", "van_gogh", "tenebrism", "pointillism", "engraving"})

    styles = []
    for name, params in sorted(_morph.STYLE_DEFAULTS.items()):
        if name in _BUILTIN:
            styles.append({
                "name": name,
                "kind": "builtin",
                "parameters": params,
            })
        else:
            # Determine extends: find which builtin generator matches
            gen = _morph.STYLE_DISPATCH.get(name)
            extends = None
            for b in _BUILTIN:
                if _morph.STYLE_DISPATCH.get(b) is gen:
                    extends = b
                    break
            styles.append({
                "name": name,
                "kind": "community",
                "extends": extends,
                "parameters": params,
            })

    return {"styles": styles, "total": len(styles)}


def tool_plan_style_schedule(args: dict) -> dict:
    """Suggest a {start, end, rationale} morph for the current target.

    Rule-based decision over image_type + warmth + saturation +
    edge_density. v1 is hand-written heuristics; a follow-up PR can
    replace the scoring body with a journal.jsonl-learned ranker
    (marked below with a `# v2 hook:` comment).
    """
    import sys as _sys
    # morph lives under scripts/paint_lib
    _scripts = _SCRIPTS_DIR  # from _common
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from paint_lib import morph as _morph

    analysis = args.get("target_analysis")
    if analysis is None:
        # Call analyze_target internally so the tool works bare.
        analysis = tool_analyze_target({})

    classification = analysis.get("classification", {}) if isinstance(analysis, dict) else {}
    image_type = classification.get("type", "balanced")
    warmth = float(classification.get("warmth", 0.0))
    saturation = float(classification.get("saturation", 30.0))
    edge_density = float(analysis.get("edge_density", 0.08)) if isinstance(analysis, dict) else 0.08

    # v2 hook: read journal.jsonl for prior high-confidence schedules on
    # similar image_types and inject them as candidates with a "learned"
    # reason prefix. For v1 we only emit hand-written candidates below.

    candidates: list[dict] = []

    # Rule set. Each rule produces (start, end, base_score, reason).
    # Scores are tuned so the strongest heuristic wins on its archetype.
    if image_type == "high_contrast" and warmth > 10 and edge_density > 0.12:
        candidates.append({"start": "van_gogh", "end": "tenebrism", "score": 0.85,
                           "reason": "warm + high edges + high contrast → dramatic close"})
    if image_type == "dark":
        candidates.append({"start": "van_gogh", "end": "tenebrism", "score": 0.80,
                           "reason": "dark target favors tenebrist finish"})
        candidates.append({"start": "default", "end": "tenebrism", "score": 0.55,
                           "reason": "safe fallback for dark targets"})
    if image_type == "bright" and saturation > 40:
        candidates.append({"start": "default", "end": "van_gogh", "score": 0.75,
                           "reason": "bright saturated target invites expressive finish"})
        candidates.append({"start": "van_gogh", "end": "pointillism", "score": 0.60,
                           "reason": "stroke-texture translation on bright subjects"})
    if image_type == "muted":
        candidates.append({"start": "default", "end": "engraving", "score": 0.70,
                           "reason": "muted palette reads well as engraving"})
        candidates.append({"start": "default", "end": "pointillism", "score": 0.55,
                           "reason": "muted → dots is a gentle arc"})
    if image_type == "balanced":
        candidates.append({"start": "van_gogh", "end": "tenebrism", "score": 0.65,
                           "reason": "balanced targets morph well across expressive range"})
        candidates.append({"start": "default", "end": "van_gogh", "score": 0.55,
                           "reason": "didactic: default reveals van_gogh's signature"})

    # Degenerate fallback — always available if nothing else ranked.
    candidates.append({"start": "default", "end": "default", "score": 0.10,
                       "reason": "degenerate: uniform default when unsure"})

    # Sort desc by score; the primary is candidates[0].
    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates = candidates[:4]  # cap at 4 total (primary + 3)

    primary = candidates[0]
    schedule = {
        "start": primary["start"],
        "end": primary["end"],
        "rationale": primary["reason"],
    }

    return {
        "schedule": schedule,
        "candidates": candidates,
    }
