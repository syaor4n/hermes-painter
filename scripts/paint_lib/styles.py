"""Underpainting variants — one per style_mode (plus the default layered).

Each function returns a list of stroke dicts; none of them posts to the
tool server. The pipeline layer wraps them in `draw_strokes` calls.
"""
import math
import random
import colorsys as _colorsys

from .core import (
    _hex_to_rgb,
    _rgb_to_hex,
    _to_luma,
    _apply_contrast_boost,
    _apply_complementary_shadow,
)


def layered_underpainting(grid, cell_w, cell_h, seed=0, direction='horizontal',
                          direction_grid=None, contrast_boost=0.0,
                          complementary_shadow=0.12):
    """Dense bristle-brush underpainting sampling colors from target grid.

    direction: 'horizontal' | 'vertical' | 'random' global fallback.
    direction_grid: optional per-cell {angle, coherence, mode} override.
    contrast_boost: 0..0.5 tanh S-curve.
    """
    random.seed(seed)
    strokes = []
    rows = len(grid)
    cols = len(grid[0])

    dgrid_rows = len(direction_grid) if direction_grid else 0
    dgrid_cols = len(direction_grid[0]) if dgrid_rows else 0

    def resolve_angle(i, j):
        if direction_grid and dgrid_rows and dgrid_cols:
            dj = min(dgrid_rows - 1, (j * dgrid_rows) // rows)
            di = min(dgrid_cols - 1, (i * dgrid_cols) // cols)
            cell = direction_grid[dj][di]
            if cell.get('mode') == 'angle':
                return float(cell['angle']), False
            return random.uniform(0, math.pi), True
        if direction == 'horizontal':
            return 0.0, False
        if direction == 'vertical':
            return math.pi / 2, False
        return random.uniform(0, math.pi), True

    for pass_i in range(2):
        for j in range(rows):
            for i in range(cols):
                color = grid[j][i]
                color = _apply_complementary_shadow(color, complementary_shadow)
                color = _apply_contrast_boost(color, contrast_boost)
                cx = i * cell_w + cell_w // 2
                cy = j * cell_h + cell_h // 2
                n = 2 if pass_i == 0 else 1
                for _ in range(n):
                    ox = random.randint(-cell_w // 3, cell_w // 3)
                    oy = random.randint(-cell_h // 3, cell_h // 3)
                    angle, is_rand = resolve_angle(i, j)
                    base = (cell_w + cell_h) / 2
                    length = int(base * random.uniform(1.2, 1.7))
                    dx = math.cos(angle) * length / 2
                    dy = math.sin(angle) * length / 2
                    x = cx + ox; y = cy + oy
                    pts = [[int(x - dx + random.randint(-1, 1)),
                            int(y - dy + random.randint(-1, 1))],
                           [int(x + random.randint(-1, 1)),
                            int(y + random.randint(-1, 1))],
                           [int(x + dx + random.randint(-1, 1)),
                            int(y + dy + random.randint(-1, 1))]]
                    if is_rand:
                        width = max(8, min(cell_w, cell_h) + random.randint(-2, 6))
                    else:
                        nx, ny = -math.sin(angle), math.cos(angle)
                        thickness = abs(nx) * cell_w + abs(ny) * cell_h
                        width = max(8, int(thickness * 0.9) + random.randint(-2, 6))
                    strokes.append({
                        'type': 'brush',
                        'points': pts,
                        'color': color,
                        'width': width,
                        'alpha': random.uniform(0.60, 0.85) if pass_i == 0
                                 else random.uniform(0.35, 0.55),
                    })
    return strokes


def layered_underpainting_segmented(regions, labels, cell_w, cell_h,
                                    seed=0, contrast_boost=0.25,
                                    complementary_shadow=0.12,
                                    fine_grid=None):
    """Region-aware underpainting. Prefers fine_grid cell color when the cell
    is an "accent" (high chroma) — preserves small saturated regions that
    SLIC merges into the nearest big region.
    """
    import numpy as np
    random.seed(seed)
    reg_by_id = {r['id']: r for r in regions}
    rows = labels.shape[0] // cell_h
    cols = labels.shape[1] // cell_w
    strokes = []
    for pass_i in range(2):
        for j in range(rows):
            for i in range(cols):
                y0, y1 = j * cell_h, min(labels.shape[0], (j + 1) * cell_h)
                x0, x1 = i * cell_w, min(labels.shape[1], (i + 1) * cell_w)
                patch = labels[y0:y1, x0:x1]
                vals, cnts = np.unique(patch, return_counts=True)
                rid = int(vals[cnts.argmax()])
                reg = reg_by_id.get(rid)
                if reg is None:
                    continue
                accent_color = None
                if fine_grid is not None:
                    fg_rows = len(fine_grid)
                    fg_cols = len(fine_grid[0]) if fg_rows else 0
                    if fg_rows and fg_cols:
                        fj = min(fg_rows - 1, (j * fg_rows) // rows)
                        fi = min(fg_cols - 1, (i * fg_cols) // cols)
                        fc = fine_grid[fj][fi]
                        r_, g_, b_ = _hex_to_rgb(fc)
                        chroma = max(r_, g_, b_) - min(r_, g_, b_)
                        if chroma > 55:
                            accent_color = fc
                if accent_color:
                    color = accent_color
                else:
                    palette = reg['palette'] or [reg['mean_rgb']]
                    rgb = list(palette[random.randint(0, len(palette) - 1)])
                    for k in range(3):
                        rgb[k] = int(0.7 * rgb[k] + 0.3 * reg['mean_rgb'][k])
                    color = '#%02x%02x%02x' % (max(0, min(255, rgb[0])),
                                                max(0, min(255, rgb[1])),
                                                max(0, min(255, rgb[2])))
                color = _apply_complementary_shadow(color, complementary_shadow)
                color = _apply_contrast_boost(color, contrast_boost)
                if reg['coherence'] > 0.1:
                    angle = reg['dominant_angle'] + random.uniform(-0.2, 0.2)
                else:
                    angle = random.uniform(0, math.pi)
                cx = i * cell_w + cell_w // 2
                cy = j * cell_h + cell_h // 2
                n = 2 if pass_i == 0 else 1
                for _ in range(n):
                    ox = random.randint(-cell_w // 3, cell_w // 3)
                    oy = random.randint(-cell_h // 3, cell_h // 3)
                    base = (cell_w + cell_h) / 2
                    length = int(base * random.uniform(1.2, 1.7))
                    dx = math.cos(angle) * length / 2
                    dy = math.sin(angle) * length / 2
                    x = cx + ox; y = cy + oy
                    pts = [[int(x - dx + random.randint(-1, 1)),
                            int(y - dy + random.randint(-1, 1))],
                           [int(x + random.randint(-1, 1)),
                            int(y + random.randint(-1, 1))],
                           [int(x + dx + random.randint(-1, 1)),
                            int(y + dy + random.randint(-1, 1))]]
                    nx_, ny_ = -math.sin(angle), math.cos(angle)
                    thickness = abs(nx_) * cell_w + abs(ny_) * cell_h
                    width = max(8, int(thickness * 0.9) + random.randint(-2, 6))
                    strokes.append({
                        'type': 'brush',
                        'points': pts,
                        'color': color,
                        'width': width,
                        'alpha': random.uniform(0.60, 0.85) if pass_i == 0
                                 else random.uniform(0.35, 0.55),
                    })
    return strokes


def pointillism_underpainting(grid, cell_w, cell_h, seed=0,
                              contrast_boost=0.25, complementary_shadow=0.18,
                              fine_grid=None):
    """Dense colored dots building form through optical mixing (Seurat).

    `fine_grid` should be a higher-resolution color table (e.g. 64×64)
    so dots retain chromatic specificity.
    """
    random.seed(seed)
    strokes = []
    source_grid = fine_grid if fine_grid is not None else grid
    rows, cols = len(source_grid), len(source_grid[0])
    canvas_w = cell_w * cols
    canvas_h = cell_h * rows
    fine_cw = canvas_w // cols
    fine_ch = canvas_h // rows
    jit_h_range = 0.015
    jit_l_range = 0.06
    jit_s_range = 0.05

    for j in range(rows):
        for i in range(cols):
            base = source_grid[j][i]
            r, g, b = _hex_to_rgb(base)
            h, l, s = _colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            comp_color = None
            if l < 0.5 and complementary_shadow > 0:
                cr, cg, cb = _colorsys.hls_to_rgb((h + 0.5) % 1.0, l, max(0.5, s))
                comp_color = _rgb_to_hex(int(cr*255), int(cg*255), int(cb*255))
            cx0 = i * fine_cw
            cy0 = j * fine_ch
            for k in range(3):
                x = cx0 + random.randint(0, fine_cw - 1)
                y = cy0 + random.randint(0, fine_ch - 1)
                if comp_color and random.random() < 0.12:
                    color = comp_color
                else:
                    jit_h = (h + random.uniform(-jit_h_range, jit_h_range)) % 1.0
                    jit_l = min(0.95, max(0.05, l + random.uniform(-jit_l_range, jit_l_range)))
                    jit_s = min(1.0, max(0.3, s + random.uniform(-jit_s_range, jit_s_range)))
                    rr, gg, bb = _colorsys.hls_to_rgb(jit_h, jit_l, jit_s)
                    color = _rgb_to_hex(int(rr*255), int(gg*255), int(bb*255))
                color = _apply_contrast_boost(color, contrast_boost)
                size = random.randint(max(3, fine_cw - 1), max(4, fine_cw + 2))
                strokes.append({
                    'type': 'dab',
                    'x': int(x), 'y': int(y),
                    'w': size, 'h': size,
                    'angle': 0.0,
                    'color': color,
                    'alpha': random.uniform(0.85, 1.0),
                })
    return strokes


def tenebrism_underpainting(grid, cell_w, cell_h, seed=0,
                             contrast_boost=0.40, complementary_shadow=0.0,
                             fine_grid=None):
    """Deep-dark warm base + fine-scale lit cells + transitional mid-L zone.
    Caravaggio-style chiaroscuro.
    """
    random.seed(seed)
    strokes = []
    coarse_rows = len(grid); coarse_cols = len(grid[0])
    canvas_w = cell_w * coarse_cols
    canvas_h = cell_h * coarse_rows
    strokes.append({
        'type': 'fill_rect',
        'x': 0, 'y': 0,
        'w': canvas_w, 'h': canvas_h,
        'color': '#14100a',
        'alpha': 1.0,
    })
    use_grid = fine_grid if fine_grid is not None else grid
    rows, cols = len(use_grid), len(use_grid[0])
    ucw = canvas_w // cols
    uch = canvas_h // rows

    for j in range(rows):
        for i in range(cols):
            base = use_grid[j][i]
            r, g, b = _hex_to_rgb(base)
            h, l, s = _colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            cx = i * ucw + ucw // 2
            cy = j * uch + uch // 2

            if l < 0.18:
                continue
            if l < 0.28:
                if random.random() > 0.5:
                    continue
                color = _apply_contrast_boost(base, contrast_boost * 0.5)
                angle = random.uniform(0, math.pi)
                length = int(ucw * 1.2)
                dx = math.cos(angle) * length / 2
                dy = math.sin(angle) * length / 2
                strokes.append({
                    'type': 'brush',
                    'points': [[int(cx - dx), int(cy - dy)],
                               [int(cx), int(cy)],
                               [int(cx + dx), int(cy + dy)]],
                    'color': color,
                    'width': max(6, ucw),
                    'alpha': 0.30,
                })
                continue

            boosted_l = min(0.92, l * 1.10 + 0.03)
            rr, gg, bb = _colorsys.hls_to_rgb(h, boosted_l, s)
            color = _apply_contrast_boost(
                _rgb_to_hex(int(rr*255), int(gg*255), int(bb*255)),
                contrast_boost)
            for pass_i in range(3):
                angle = random.uniform(0, math.pi)
                length = int(ucw * random.uniform(1.0, 1.5))
                dx = math.cos(angle) * length / 2
                dy = math.sin(angle) * length / 2
                ox = random.randint(-ucw // 3, ucw // 3)
                oy = random.randint(-uch // 3, uch // 3)
                x = cx + ox; y = cy + oy
                nx_, ny_ = -math.sin(angle), math.cos(angle)
                thickness = abs(nx_) * ucw + abs(ny_) * uch
                width = max(5, int(thickness * 0.7) + random.randint(-1, 3))
                alpha = (0.75, 0.55, 0.38)[pass_i]
                strokes.append({
                    'type': 'brush',
                    'points': [[int(x - dx), int(y - dy)],
                               [int(x), int(y)],
                               [int(x + dx), int(y + dy)]],
                    'color': color,
                    'width': width,
                    'alpha': alpha,
                })
    return strokes


def van_gogh_underpainting(grid, cell_w, cell_h, direction_grid,
                            seed=0, contrast_boost=0.40,
                            complementary_shadow=0.18):
    """Long, directional, saturated bristles — 3 passes, confident strokes.
    Requires a direction_grid (per-cell angles from direction_field_grid tool).
    """
    random.seed(seed)
    strokes = []
    rows, cols = len(grid), len(grid[0])
    dgrid_rows = len(direction_grid) if direction_grid else 0
    dgrid_cols = len(direction_grid[0]) if dgrid_rows else 0

    def cell_angle(i, j):
        if not dgrid_rows:
            return random.uniform(0, math.pi)
        dj = min(dgrid_rows - 1, (j * dgrid_rows) // rows)
        di = min(dgrid_cols - 1, (i * dgrid_cols) // cols)
        cell = direction_grid[dj][di]
        if cell.get('mode') == 'angle':
            return float(cell['angle'])
        return random.uniform(0, math.pi)

    for pass_i in range(3):
        for j in range(rows):
            for i in range(cols):
                color = grid[j][i]
                color = _apply_complementary_shadow(color, complementary_shadow)
                color = _apply_contrast_boost(color, contrast_boost)
                cx = i * cell_w + cell_w // 2
                cy = j * cell_h + cell_h // 2
                angle = cell_angle(i, j)
                ox = random.randint(-cell_w // 3, cell_w // 3)
                oy = random.randint(-cell_h // 3, cell_h // 3)
                length = int((cell_w + cell_h) / 2 * random.uniform(1.5, 2.0))
                dx = math.cos(angle) * length / 2
                dy = math.sin(angle) * length / 2
                x = cx + ox; y = cy + oy
                pts = [[int(x - dx), int(y - dy)],
                       [int(x + random.randint(-1, 1)), int(y + random.randint(-1, 1))],
                       [int(x + dx), int(y + dy)]]
                nx_, ny_ = -math.sin(angle), math.cos(angle)
                thickness = abs(nx_) * cell_w + abs(ny_) * cell_h
                width = max(10, int(thickness * 0.85) + random.randint(-2, 4))
                base_alpha = (0.75, 0.55, 0.40)[pass_i]
                strokes.append({
                    'type': 'brush',
                    'points': pts,
                    'color': color,
                    'width': width,
                    'alpha': base_alpha + random.uniform(-0.08, 0.08),
                })
    return strokes


def engraving_underpainting(grid, cell_w, cell_h, seed=0):
    """Hachure + crosshatching: density inversely proportional to luma.
    Produces a recognizable engraving/mezzotint texture.
    """
    random.seed(seed)
    strokes = []
    rows, cols = len(grid), len(grid[0])
    for j in range(rows):
        for i in range(cols):
            color = _to_luma(grid[j][i])
            lum = _hex_to_rgb(color)[0] / 255.0
            density = max(1, int(round(10 * (1.0 - lum) ** 1.3)))
            cx = i * cell_w + cell_w // 2
            cy = j * cell_h + cell_h // 2
            for angle_sign in (1, -1):
                if angle_sign == -1 and lum > 0.5:
                    continue
                n_lines = density if angle_sign == 1 else max(1, density - 3)
                for k in range(n_lines):
                    offset = (k / max(1, n_lines)) * cell_w - cell_w / 2
                    dx = math.cos(angle_sign * math.pi / 4)
                    dy = math.sin(angle_sign * math.pi / 4)
                    px = cx - dy * offset + random.uniform(-1, 1)
                    py = cy + dx * offset + random.uniform(-1, 1)
                    length = cell_w * 1.3
                    p0x = int(px - dx * length / 2)
                    p0y = int(py - dy * length / 2)
                    p1x = int(px + dx * length / 2)
                    p1y = int(py + dy * length / 2)
                    strokes.append({
                        'type': 'polyline',
                        'points': [[p0x, p0y], [p1x, p1y]],
                        'color': color,
                        'width': 1,
                        'alpha': random.uniform(0.45, 0.75),
                    })
    return strokes
