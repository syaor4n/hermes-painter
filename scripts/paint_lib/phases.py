"""Post-underpainting phases that live outside the style library:
critique_correct (worst-cells touch-up loop) and fill_gaps_with_grid."""
import math
import os
import random
import urllib.request

from .core import post, sample_cell, _viewer_base


def critique_correct(n_rounds=2, strokes_per_round=40, top_regions=12,
                     seed=0, verbose=True):
    """For each of the worst 8×8 cells, sample target color and paint small
    bristle strokes. Runs after the main pipeline. Returns total strokes added.
    """
    added = 0
    for r in range(n_rounds):
        try:
            regs = post('get_regions', {'top': top_regions})
        except Exception:
            break
        regions = regs.get('regions', [])
        if not regions:
            break
        strokes = []
        random.seed(seed + 100 * (r + 1))
        for reg in regions[:top_regions]:
            x = int(reg.get('x', reg.get('cx', 0)))
            y = int(reg.get('y', reg.get('cy', 0)))
            w = int(reg.get('w', reg.get('width', 64)))
            h = int(reg.get('h', reg.get('height', 64)))
            _cs = int(os.environ.get('PAINTER_CANVAS_SIZE', 512))
            w = max(16, min(w, _cs))
            h = max(16, min(h, _cs))
            try:
                c = sample_cell(x, y, w, h)
            except Exception:
                continue
            cx, cy = x + w // 2, y + h // 2
            for _ in range(2):
                angle = random.uniform(0, math.pi)
                length = int((w + h) / 2 * random.uniform(0.8, 1.2))
                dx = math.cos(angle) * length / 2
                dy = math.sin(angle) * length / 2
                ox = random.randint(-w // 4, w // 4)
                oy = random.randint(-h // 4, h // 4)
                strokes.append({
                    'type': 'brush',
                    'points': [[int(cx + ox - dx), int(cy + oy - dy)],
                               [int(cx + ox), int(cy + oy)],
                               [int(cx + ox + dx), int(cy + oy + dy)]],
                    'color': c,
                    'width': max(8, min(w, h) + random.randint(-2, 4)),
                    'alpha': random.uniform(0.55, 0.8),
                })
                if len(strokes) >= strokes_per_round:
                    break
            if len(strokes) >= strokes_per_round:
                break
        if not strokes:
            break
        post('draw_strokes', {'strokes': strokes, 'reasoning': f'critique round {r+1}'})
        added += len(strokes)
        if verbose:
            print(f'  critique r{r+1}: +{len(strokes)} strokes on top-{top_regions} error cells')
    return added


def fill_gaps_with_grid(grid, cell_w, cell_h, seed=1):
    """After dump_gaps shows uncovered regions, generate small brush strokes
    in those cells. Returns a stroke list (caller posts draw_strokes)."""
    from PIL import Image
    import numpy as np

    with urllib.request.urlopen(_viewer_base() + '/api/state') as r:
        pass  # confirm reachable
    post('dump_gaps', {})
    mask = Image.open('/tmp/painter_gaps.png').convert('L')
    m = np.asarray(mask)  # 255 = gap, 0 = covered
    random.seed(seed)
    strokes = []
    rows = len(grid)
    cols = len(grid[0])
    for j in range(rows):
        for i in range(cols):
            y0 = j * cell_h
            x0 = i * cell_w
            cell = m[y0:y0+cell_h, x0:x0+cell_w]
            gap_frac = cell.mean() / 255.0
            if gap_frac > 0.15:
                color = grid[j][i]
                n_fill = max(2, int(gap_frac * 6))
                for _ in range(n_fill):
                    cx = x0 + random.randint(2, cell_w-2)
                    cy = y0 + random.randint(2, cell_h-2)
                    length = cell_w * 2 // 3
                    strokes.append({
                        'type': 'brush',
                        'points': [[cx-length//2, cy+random.randint(-1,1)],
                                   [cx, cy+random.randint(-1,1)],
                                   [cx+length//2, cy+random.randint(-1,1)]],
                        'color': color,
                        'width': random.randint(8, cell_h+4),
                        'alpha': random.uniform(0.55, 0.80),
                    })
    return strokes
