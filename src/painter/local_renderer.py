"""Render a stroke plan onto a PIL canvas — no browser needed.

The purpose is twofold:
  1. Let the agent "imagine" the outcome of a plan before committing.
  2. Score candidate plans locally (fast, cheap) and only apply the best one.

This mirrors canvas/index.html as closely as PIL allows. Exact parity is
impossible (subpixel anti-aliasing differs) but the similarity is high
enough that imagined-SSIM is a reliable proxy for real-browser SSIM.
"""
from __future__ import annotations

import io
import math
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw

CANVAS_SIZE = (512, 512)
_WHITE_RGBA = (255, 255, 255, 255)

# Per-type default alpha when `alpha` is missing on a stroke. Matches
# canvas/index.html's drawStroke() behavior exactly — without this parity,
# `critic.score_plan()` would diverge from the real canvas for any plan that
# omits alpha on brush/dab/splat.
_DEFAULT_ALPHA = {
    "brush": 0.85,
    "dab": 0.9,
    "splat": 0.7,
}


def _stroke_alpha(stroke: dict[str, Any]) -> float:
    if "alpha" in stroke and stroke["alpha"] is not None:
        return float(stroke["alpha"])
    return _DEFAULT_ALPHA.get(stroke.get("type", ""), 1.0)


def _parse_color(color: Any) -> tuple[int, int, int]:
    if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
        return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return int(color[0]), int(color[1]), int(color[2])
    return 0, 0, 0


def _rgba(color: Any, alpha: float) -> tuple[int, int, int, int]:
    r, g, b = _parse_color(color)
    a = max(0, min(255, int(round(alpha * 255))))
    return r, g, b, a


def _ribbon_points(points: Sequence[Sequence[float]], width: float) -> list[tuple[float, float]]:
    """Build the polygon outline used for a brush ribbon (same math as canvas)."""
    if len(points) < 2:
        return []
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for i, p1 in enumerate(points):
        p0 = points[max(0, i - 1)]
        p2 = points[min(len(points) - 1, i + 1)]
        dx = p2[0] - p0[0]
        dy = p2[1] - p0[1]
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        hw = width / 2
        left.append((p1[0] + nx * hw, p1[1] + ny * hw))
        right.append((p1[0] - nx * hw, p1[1] - ny * hw))
    return left + right[::-1]


def _draw_one(stroke: dict[str, Any], base: Image.Image) -> None:
    stype = stroke.get("type", "")
    alpha = _stroke_alpha(stroke)
    color = _rgba(stroke.get("color", "#000000"), alpha)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    if stype == "fill_rect":
        x = stroke["x"]; y = stroke["y"]; w = stroke["w"]; h = stroke["h"]
        d.rectangle([x, y, x + w, y + h], fill=color)

    elif stype == "fill_circle":
        x = stroke["x"]; y = stroke["y"]; r = stroke["r"]
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    elif stype == "fill_poly":
        pts = [tuple(p) for p in stroke.get("points", [])]
        if len(pts) >= 3:
            d.polygon(pts, fill=color)

    elif stype == "polyline":
        pts = [tuple(p) for p in stroke.get("points", [])]
        if len(pts) >= 2:
            d.line(pts, fill=color, width=int(stroke.get("width", 2)), joint="curve")

    elif stype == "line":
        pts = [tuple(p) for p in stroke.get("points", [])]
        if len(pts) >= 2:
            d.line([pts[0], pts[-1]], fill=color, width=int(stroke.get("width", 2)))

    elif stype == "bezier":
        # PIL has no native bezier — approximate with a short polyline
        pts = stroke.get("points", [])
        if len(pts) == 4:
            p0, c1, c2, p1 = pts
            samples = []
            for t in [i / 20 for i in range(21)]:
                mt = 1 - t
                x = mt**3 * p0[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t**2 * c2[0] + t**3 * p1[0]
                y = mt**3 * p0[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t**2 * c2[1] + t**3 * p1[1]
                samples.append((x, y))
            d.line(samples, fill=color, width=int(stroke.get("width", 2)), joint="curve")

    elif stype == "brush":
        pts = [tuple(p) for p in stroke.get("points", [])]
        if len(pts) >= 2:
            w = float(stroke.get("width", 20))
            texture = stroke.get("texture", "bristle")
            base_alpha = _stroke_alpha(stroke)
            base_rgb = _parse_color(stroke.get("color", "#000000"))

            if texture == "smooth":
                # Legacy smooth ribbon
                ribbon = _ribbon_points(pts, w)
                if ribbon:
                    d.polygon(ribbon, fill=color)
                hw = w / 2
                d.ellipse([pts[0][0] - hw, pts[0][1] - hw, pts[0][0] + hw, pts[0][1] + hw], fill=color)
                d.ellipse([pts[-1][0] - hw, pts[-1][1] - hw, pts[-1][0] + hw, pts[-1][1] + hw], fill=color)
            else:
                # Textured bristle brush — mirrors canvas/index.html
                r_i, g_i, b_i = base_rgb
                seed = int(
                    (pts[0][0] * 73 + pts[0][1] * 37 + w * 13 + r_i * 7 + g_i * 11 + b_i * 17)
                ) % 2147483646
                if seed <= 0:
                    seed = 1

                def _rand() -> float:
                    nonlocal seed
                    seed = (seed * 16807) % 2147483647
                    return (seed - 1) / 2147483646

                # Pre-compute normals at each waypoint
                normals: list[tuple[float, float]] = []
                for i, p1 in enumerate(pts):
                    p0 = pts[max(0, i - 1)]
                    p2 = pts[min(len(pts) - 1, i + 1)]
                    dx = p2[0] - p0[0]
                    dy = p2[1] - p0[1]
                    length = math.hypot(dx, dy) or 1.0
                    normals.append((-dy / length, dx / length))

                # Subdivide path so bristles have enough sample points to wobble over
                SUB = 8
                dense: list[tuple[float, float]] = []
                dense_normals: list[tuple[float, float]] = []
                for i in range(len(pts) - 1):
                    p1_, p2_ = pts[i], pts[i + 1]
                    n1_, n2_ = normals[i], normals[i + 1]
                    steps = SUB + 1 if i == len(pts) - 2 else SUB
                    for k in range(steps):
                        t = k / SUB
                        dense.append((p1_[0] + (p2_[0] - p1_[0]) * t, p1_[1] + (p2_[1] - p1_[1]) * t))
                        dense_normals.append((n1_[0] + (n2_[0] - n1_[0]) * t, n1_[1] + (n2_[1] - n1_[1]) * t))

                # Layer 1: narrow wash — fills gaps between bristles
                wash_alpha = max(1, int(base_alpha * 0.18 * 255))
                wash_color = (r_i, g_i, b_i, wash_alpha)
                wash_ribbon = _ribbon_points(list(dense), w * 0.9)
                if wash_ribbon:
                    wo = Image.new("RGBA", base.size, (0, 0, 0, 0))
                    ImageDraw.Draw(wo).polygon(wash_ribbon, fill=wash_color)
                    base.alpha_composite(wo)

                # Layer 2: bristle streaks
                n_bristles = max(12, min(32, int(w * 0.9)))
                bo = Image.new("RGBA", base.size, (0, 0, 0, 0))
                bd = ImageDraw.Draw(bo)
                for bi in range(n_bristles):
                    t = bi / max(1, n_bristles - 1)
                    offset = (t - 0.5) * w * (0.95 + _rand() * 0.1) + (_rand() - 0.5) * 2.5
                    edge_dist = abs(t - 0.5) * 2
                    hue_shift = (_rand() - 0.5) * 28
                    val_shift = (_rand() - 0.5) * 30 - edge_dist * 8
                    br = int(max(0, min(255, r_i + hue_shift + val_shift)))
                    bg = int(max(0, min(255, g_i + hue_shift * 0.7 + val_shift * 0.95)))
                    bb = int(max(0, min(255, b_i + hue_shift * 1.3 + val_shift * 0.85)))
                    bristle_alpha = base_alpha * (0.45 + _rand() * 0.55)
                    bristle_w = 0.7 + _rand() * 1.4
                    start_trim = _rand() * 0.05
                    end_trim = _rand() * 0.08

                    path: list[tuple[float, float]] = []
                    for j in range(len(dense)):
                        tau = 0.0 if len(dense) == 1 else j / (len(dense) - 1)
                        if tau < start_trim or tau > 1 - end_trim:
                            continue
                        nx, ny = dense_normals[j]
                        wobble_x = (_rand() - 0.5) * 2.5
                        wobble_y = (_rand() - 0.5) * 2.5
                        path.append((dense[j][0] + nx * offset + wobble_x, dense[j][1] + ny * offset + wobble_y))
                    if len(path) >= 2:
                        bd.line(
                            path,
                            fill=(br, bg, bb, max(1, int(bristle_alpha * 255))),
                            width=max(1, int(round(bristle_w))),
                            joint="curve",
                        )
                base.alpha_composite(bo)

                # Layer 3: dark wet accents
                ao = Image.new("RGBA", base.size, (0, 0, 0, 0))
                ad = ImageDraw.Draw(ao)
                n_accents = 3 + int(_rand() * 3)
                for _ in range(n_accents):
                    t = _rand()
                    offset = (t - 0.5) * w * 0.85
                    dr = int(max(0, r_i - 25 - _rand() * 20))
                    dg = int(max(0, g_i - 25 - _rand() * 20))
                    db = int(max(0, b_i - 25 - _rand() * 20))
                    a_alpha = max(1, int(base_alpha * 0.4 * 255))
                    a_width = max(1, int(round(0.6 + _rand() * 0.7)))
                    s_trim = 0.05 + _rand() * 0.3
                    e_trim = 0.05 + _rand() * 0.3
                    path = []
                    for j in range(len(dense)):
                        tau = 0.0 if len(dense) == 1 else j / (len(dense) - 1)
                        if tau < s_trim or tau > 1 - e_trim:
                            continue
                        nx, ny = dense_normals[j]
                        path.append((dense[j][0] + nx * offset + (_rand() - 0.5) * 2,
                                     dense[j][1] + ny * offset + (_rand() - 0.5) * 2))
                    if len(path) >= 2:
                        ad.line(path, fill=(dr, dg, db, a_alpha), width=a_width, joint="curve")
                base.alpha_composite(ao)

    elif stype == "dab":
        cx = stroke["x"]; cy = stroke["y"]
        dw = stroke.get("w", 20); dh = stroke.get("h", dw * 0.6)
        angle = float(stroke.get("angle", 0))
        # Build an ellipse polygon then rotate
        samples = 24
        pts = []
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for i in range(samples):
            t = 2 * math.pi * i / samples
            x = math.cos(t) * dw / 2
            y = math.sin(t) * dh / 2
            pts.append((cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a))
        d.polygon(pts, fill=color)

    elif stype == "fog":
        x = int(stroke.get("x", 0))
        y = int(stroke.get("y", 0))
        w_f = int(stroke.get("w", base.size[0]))
        h_f = int(stroke.get("h", base.size[1]))
        a_base = _stroke_alpha(stroke)
        color_hex = stroke.get("color", "#cccccc")
        r_i, g_i, b_i = _parse_color(color_hex)
        direction = stroke.get("direction", "horizontal")
        fade = float(stroke.get("fade", 0.4))

        yy, xx = np.mgrid[0:h_f, 0:w_f].astype(np.float32)
        if direction == "vertical":
            t = yy / max(h_f - 1, 1)
        elif direction == "radial":
            cx_f = (w_f - 1) / 2
            cy_f = (h_f - 1) / 2
            r_max = max(w_f, h_f) / 2
            dist = np.sqrt((xx - cx_f) ** 2 + (yy - cy_f) ** 2) / max(r_max, 1e-6)
            t = dist
        else:  # horizontal
            t = xx / max(w_f - 1, 1)

        if direction == "radial":
            # Fade inward from edge
            alpha_map = np.clip((1.0 - t) / max(fade, 1e-6), 0.0, 1.0)
        else:
            # Fade in, hold, fade out
            alpha_map = np.where(
                t < fade, t / max(fade, 1e-6),
                np.where(t > 1 - fade, (1 - t) / max(fade, 1e-6), 1.0)
            )
            alpha_map = np.clip(alpha_map, 0.0, 1.0)

        alpha_px = (alpha_map * a_base * 255).astype(np.uint8)
        fog_layer = np.stack([
            np.full_like(alpha_px, r_i),
            np.full_like(alpha_px, g_i),
            np.full_like(alpha_px, b_i),
            alpha_px,
        ], axis=-1)
        fog_img = Image.fromarray(fog_layer, mode="RGBA")
        # Paste at (x, y)
        region = Image.new("RGBA", base.size, (0, 0, 0, 0))
        region.paste(fog_img, (x, y), fog_img)
        base.alpha_composite(region)

    elif stype == "glow":
        cx = float(stroke["x"]); cy = float(stroke["y"]); r = float(stroke.get("r", 30))
        a_base = _stroke_alpha(stroke)
        stops = stroke.get("stops")
        if stops is None:
            base_hex = stroke.get("color", "#ffd870")
            stops = [
                (0.00, "#ffffff", 1.0),
                (0.20, "#fff2b0", 1.0),
                (0.50, base_hex, 1.0),
                (1.00, base_hex, 0.0),
            ]
        else:
            # Normalize: each stop is [t, color_string]. Extract alpha if "rgba(..)", else default 1
            parsed: list[tuple[float, str, float]] = []
            for s in stops:
                t, col = s[0], s[1]
                col_s = str(col).strip()
                if col_s.startswith("rgba"):
                    # rgba(r,g,b,a)
                    inner = col_s[col_s.index("(")+1: col_s.rindex(")")]
                    parts = [p.strip() for p in inner.split(",")]
                    parsed.append((float(t), f"#{int(parts[0]):02x}{int(parts[1]):02x}{int(parts[2]):02x}",
                                   float(parts[3])))
                else:
                    parsed.append((float(t), col_s, 1.0))
            stops = parsed

        # Build radial mask with numpy, blend on top of base
        yy, xx = np.mgrid[0:base.size[1], 0:base.size[0]].astype(np.float32)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max(r, 1e-6)
        mask = np.clip(dist, 0, 1)
        # Build RGBA layer per-pixel by interpolating between successive stops
        stops_sorted = sorted(stops, key=lambda s: s[0])
        out_r = np.zeros_like(mask)
        out_g = np.zeros_like(mask)
        out_b = np.zeros_like(mask)
        out_a = np.zeros_like(mask)
        for i in range(len(stops_sorted) - 1):
            t0, c0, a0 = stops_sorted[i]
            t1, c1, a1 = stops_sorted[i + 1]
            r0, g0, b0 = _parse_color(c0)
            r1, g1, b1 = _parse_color(c1)
            segment = (mask >= t0) & (mask <= t1)
            if t1 - t0 < 1e-6:
                k = np.zeros_like(mask)
            else:
                k = (mask - t0) / (t1 - t0)
            out_r = np.where(segment, r0 + (r1 - r0) * k, out_r)
            out_g = np.where(segment, g0 + (g1 - g0) * k, out_g)
            out_b = np.where(segment, b0 + (b1 - b0) * k, out_b)
            out_a = np.where(segment, a0 + (a1 - a0) * k, out_a)
        # Beyond the last stop → fully transparent (matches canvas behavior when radius reaches max)
        outside = mask > stops_sorted[-1][0]
        out_a = np.where(outside, 0.0, out_a)
        # Clip circle boundary: mask>1 is fully transparent
        out_a = np.where(mask > 1.0, 0.0, out_a)
        # Apply the stroke's base alpha
        out_a = np.clip(out_a * a_base * 255, 0, 255).astype(np.uint8)
        layer = np.stack([
            np.clip(out_r, 0, 255).astype(np.uint8),
            np.clip(out_g, 0, 255).astype(np.uint8),
            np.clip(out_b, 0, 255).astype(np.uint8),
            out_a,
        ], axis=-1)
        glow_img = Image.fromarray(layer, mode="RGBA")
        base.alpha_composite(glow_img)

    elif stype == "splat":
        cx = stroke["x"]; cy = stroke["y"]
        r = stroke.get("r", 15); count = int(stroke.get("count", 5))
        # Match canvas's deterministic PRNG so splats look identical across both renderers
        seed = (cx * 73 + cy * 37 + r * 13) % 1000
        def _rand() -> float:
            nonlocal seed
            seed = (seed * 16807) % 2147483647
            return (seed - 1) / 2147483646
        for _ in range(count):
            sx = cx + (_rand() - 0.5) * r * 1.5
            sy = cy + (_rand() - 0.5) * r * 1.5
            sr = r * (0.3 + _rand() * 0.7)
            d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=color)

    # Unknown types: silently skip (matches canvas behavior)
    base.alpha_composite(overlay)


def render(
    strokes: Iterable[dict[str, Any]],
    *,
    base_png: bytes | None = None,
    size: tuple[int, int] = CANVAS_SIZE,
) -> Image.Image:
    """Render `strokes` on top of `base_png` (or a white canvas). Returns RGB image."""
    if base_png is None:
        canvas = Image.new("RGBA", size, _WHITE_RGBA)
    else:
        canvas = Image.open(io.BytesIO(base_png)).convert("RGBA")
        if canvas.size != size:
            canvas = canvas.resize(size, Image.LANCZOS)
    for s in strokes:
        _draw_one(s, canvas)
    return canvas.convert("RGB")


def render_to_png(
    strokes: Iterable[dict[str, Any]],
    *,
    base_png: bytes | None = None,
    size: tuple[int, int] = CANVAS_SIZE,
) -> bytes:
    img = render(strokes, base_png=base_png, size=size)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
