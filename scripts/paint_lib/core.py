"""Small helpers shared by every phase: HTTP tool call, color math,
scoring, phase tracking, the painterly_spread stroke transform, and the
P0.1 skill-effects feedback loop (used by auto_paint).
"""
import json
import math
import random
import sys
import colorsys as _colorsys
import urllib.request
from pathlib import Path
import base64 as _b64
import os as _os


def _viewer_base() -> str:
    """Resolve the viewer base URL from env (set by the viewer's subprocess
    spawn — see R2). Fallback to localhost:8080 for direct CLI usage."""
    return _os.environ.get("PAINTER_VIEWER_URL", "http://127.0.0.1:8080")


def _read_canvas_bytes() -> bytes | None:
    """Fetch the current canvas PNG bytes directly from the viewer's
    /api/state endpoint. No filesystem intermediary, so no race between
    the tool-server's dump_canvas and this read.

    Returns None if the viewer is unreachable or the response has no
    canvas_png field (blank canvas pre-paint).
    """
    try:
        with urllib.request.urlopen(_viewer_base() + "/api/state", timeout=10) as r:
            payload = r.read()
        import json as _json
        state = _json.loads(payload)
        b64 = state.get("canvas_png")
        if not b64:
            return None
        return _b64.b64decode(b64)
    except Exception:
        return None


def _tool_base() -> str:
    """Resolve the tool server base URL from env (set by the viewer's subprocess
    spawn or demo orchestrator — same shape as _viewer_base). Fallback to
    localhost:8765 for direct CLI usage."""
    return _os.environ.get("PAINTER_TOOL_URL", "http://localhost:8765")


def post(tool, p=None, port=None):
    """Post to the tool server. Prefers PAINTER_TOOL_URL env var; falls back to
    port kwarg (legacy callers) and ultimately the localhost:8765 default."""
    base = _tool_base() if port is None else f"http://localhost:{port}"
    req = urllib.request.Request(
        f'{base}/tool/{tool}',
        data=json.dumps(p or {}).encode(),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _regression_alert(target_path, final_score, verbose=True):
    """Compare current SSIM to the last journal entry for the same target.
    Drop > 0.02 logs a red warning. Non-fatal."""
    try:
        from painter.journal import JOURNAL_PATH as journal_path
        if not journal_path.exists():
            return None
        target_base = Path(target_path).name
        last = None
        with journal_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                t = e.get('target', '') or ''
                if target_base in t and e.get('final_ssim') is not None:
                    last = e
        if last is None:
            return None
        prev_ssim = float(last['final_ssim'])
        cur_ssim = float(final_score.get('ssim', 0.0))
        delta = cur_ssim - prev_ssim
        if verbose:
            if delta < -0.02:
                print(f'  ⚠ REGRESSION on {target_base}: SSIM {cur_ssim:.4f} vs last {prev_ssim:.4f} ({delta:+.4f})')
            elif delta > 0.02:
                print(f'  ✓ progress on {target_base}: SSIM {cur_ssim:.4f} vs last {prev_ssim:.4f} ({delta:+.4f})')
        return {'prev_ssim': prev_ssim, 'cur_ssim': cur_ssim, 'delta': delta,
                'prev_run': last.get('run')}
    except Exception:
        return None


def score_current_canvas(target_path):
    """Score the current canvas against target. Returns {ssim, mse, composite}
    or None on failure. Uses painter.critic — src/ must be importable."""
    try:
        import sys as _sys
        _here = Path(__file__).resolve().parent.parent
        _src = _here.parent / 'src'
        if str(_src) not in _sys.path:
            _sys.path.insert(0, str(_src))
        from painter.critic import score as _score
        target_bytes = Path(target_path).read_bytes()
        canvas_bytes = _read_canvas_bytes()
        if canvas_bytes is None:
            return None
        return _score(target_bytes, canvas_bytes)
    except Exception:
        return None


def track_phase(phase_name, phase_deltas, target_path, prev_score):
    """Dump canvas, score, record delta vs prev_score. Returns the new score."""
    post('dump_canvas', {})
    new_score = score_current_canvas(target_path)
    if new_score and prev_score:
        phase_deltas[phase_name] = {
            'ssim': round(new_score['ssim'] - prev_score['ssim'], 4),
            'mse': round(new_score['mse'] - prev_score['mse'], 5),
            'composite': round(new_score['composite'] - prev_score['composite'], 4),
        }
    elif new_score:
        phase_deltas[phase_name] = {
            'ssim': round(new_score['ssim'], 4),
            'mse': round(new_score['mse'], 5),
            'composite': round(new_score['composite'], 4),
            'baseline': True,
        }
    return new_score or prev_score


def safe_phase(name, fn, fallback=None, verbose=True):
    """Snapshot before the phase; restore on exception. Returns `fallback` on failure."""
    try:
        snap = post('snapshot', {}).get('id')
    except Exception:
        snap = None
    try:
        return fn()
    except Exception as e:
        if verbose:
            print(f'  ⚠ phase {name} failed ({type(e).__name__}: {e}); rolling back')
        if snap:
            try:
                post('restore', {'id': snap})
            except Exception:
                pass
        return fallback


def sample_cell(x, y, w=16, h=16):
    """Sample target color at a cell; returns hex."""
    return post('sample_target', {'x': x, 'y': y, 'w': w, 'h': h})['hex']


def sample_grid(gx=16, gy=16):
    """Return (grid, cell_w, cell_h) — batch-sampled in one HTTP call when possible."""
    try:
        r = post('sample_grid', {'gx': gx, 'gy': gy})
        return r['grid'], r['cell_w'], r['cell_h']
    except Exception:
        import os
        canvas_size = int(os.environ.get('PAINTER_CANVAS_SIZE', 512))
        cell_w = canvas_size // gx
        cell_h = canvas_size // gy
        grid = [[sample_cell(i * cell_w, j * cell_h, cell_w, cell_h)
                 for i in range(gx)] for j in range(gy)]
        return grid, cell_w, cell_h


def _hex_to_rgb(hx):
    return int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)


def _rgb_to_hex(r, g, b):
    return '#%02x%02x%02x' % (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))


def _apply_contrast_boost(hex_color, boost):
    """S-curve contrast via tanh: darks darker, lights brighter. boost in [0, 0.5]."""
    if boost <= 0:
        return hex_color
    r, g, b = _hex_to_rgb(hex_color)
    k = 1.0 + 3.0 * boost
    def f(v):
        x = (v / 255.0 - 0.5) * k
        return 255 * 0.5 * (1 + math.tanh(x))
    return _rgb_to_hex(f(r), f(g), f(b))


def _to_luma(hex_color):
    """Rec. 601 grayscale triplet — preserves tone, removes chroma."""
    r, g, b = _hex_to_rgb(hex_color)
    lum = int(0.299 * r + 0.587 * g + 0.114 * b)
    return _rgb_to_hex(lum, lum, lum)


def _bezier_sample_pts(p0, c1, c2, p1, n=4):
    """Sample n+1 points along a cubic bezier curve."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t**2 * c2[0] + t**3 * p1[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t**2 * c2[1] + t**3 * p1[1]
        pts.append([int(x), int(y)])
    return pts


def _canvas_area_from_result(saliency_info):
    """Infer canvas total area. Uses env fallback."""
    import os
    cs = int(os.environ.get('PAINTER_CANVAS_SIZE', 512))
    return cs * cs


def _apply_complementary_shadow(hex_color, strength=0.12):
    """Monet-style: shadows contain the complementary hue of the light.
    Applied only when L < 0.45. strength: 0..0.3."""
    if strength <= 0:
        return hex_color
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = _colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    if l >= 0.45:
        return hex_color
    comp_h = (h + 0.5) % 1.0
    cr, cg, cb = _colorsys.hls_to_rgb(comp_h, l, max(0.4, s))
    falloff = min(1.0, (0.45 - l) / 0.40)
    mix = strength * falloff
    nr = int(r * (1 - mix) + cr * 255 * mix)
    ng = int(g * (1 - mix) + cg * 255 * mix)
    nb = int(b * (1 - mix) + cb * 255 * mix)
    return _rgb_to_hex(nr, ng, nb)


def detect_grayscale_target(target_path):
    """True iff the target is essentially monochrome.
    Uses per-pixel chroma + hue concentration (guards against colorful-muted photos).
    """
    try:
        from PIL import Image
        import numpy as np
        arr = np.asarray(Image.open(target_path).convert('RGB')).astype(float)
        chroma = arr.max(axis=2) - arr.min(axis=2)
        mean_c = float(chroma.mean())
        p50 = float(np.percentile(chroma, 50))
        p95 = float(np.percentile(chroma, 95))
        if not (mean_c < 30 and p50 < 30 and p95 < 50):
            return False
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        maxv = np.max(arr, axis=2); minv = np.min(arr, axis=2)
        delta = maxv - minv
        mask = delta > 10
        if not mask.any():
            return True
        H = np.zeros_like(maxv)
        rm = (maxv == r) & mask
        gm = (maxv == g) & mask & ~rm
        bm = (maxv == b) & mask & ~rm & ~gm
        H[rm] = ((g[rm] - b[rm]) / delta[rm]) % 6
        H[gm] = ((b[gm] - r[gm]) / delta[gm]) + 2
        H[bm] = ((r[bm] - g[bm]) / delta[bm]) + 4
        H = H * 60
        rad = np.deg2rad(H[mask])
        mean_cos = float(np.cos(rad).mean())
        mean_sin = float(np.sin(rad).mean())
        concentration = (mean_cos ** 2 + mean_sin ** 2) ** 0.5
        return concentration > 0.85
    except Exception:
        return False


def painterly_spread(strokes, halo_width_mult=4.0, halo_alpha=0.14,
                     anchor_alpha_scale=0.55):
    """Transform thin detail strokes into painterly marks.

    For each polyline/bezier with width ≤ 2:
      1. Halo: wide soft same-color brush (scumble/glaze)
      2. Softer anchor: same stroke, lower alpha

    Strokes that aren't thin details pass through unchanged.
    """
    out: list[dict] = []
    for s in strokes:
        stype = s.get('type', '')
        w = int(s.get('width', 1))
        if stype not in ('polyline', 'bezier') or w > 2:
            out.append(s)
            continue
        if stype == 'bezier':
            pts = s.get('points', [])
            if len(pts) != 4:
                out.append(s)
                continue
            halo_pts = _bezier_sample_pts(pts[0], pts[1], pts[2], pts[3], n=4)
        else:
            halo_pts = [list(p) for p in s.get('points', [])]
            if len(halo_pts) < 2:
                out.append(s)
                continue

        halo = {
            'type': 'brush',
            'points': halo_pts,
            'color': s.get('color', '#000000'),
            'width': max(4, int(w * halo_width_mult)),
            'alpha': halo_alpha,
            'texture': 'smooth',
        }
        out.append(halo)
        anchor = dict(s)
        orig_alpha = float(s.get('alpha', 0.5))
        anchor['alpha'] = orig_alpha * anchor_alpha_scale
        out.append(anchor)
    return out


# --- P0.1 feedback loop (used by auto_paint) ---

def apply_skill_effects(image_type: str, style_mode: str | None,
                         auto_paint_kwargs: dict) -> tuple[str | None, dict, dict, list]:
    """Read skills applicable to `image_type`, sum their dimensional_effects,
    clamp, and return (effective_style, effective_kwargs, effective_params,
    applied_skills_summary).

    auto_paint calls this before entering the pipeline. Skills with
    `scope.image_types = [T]` apply only when image_type == T; skills
    with empty scope (universal) apply everywhere.
    """
    _src = Path(__file__).resolve().parent.parent.parent / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from painter.skills import applicable_skills_for, effects_vector, clamp_effect

    applied = [s for s in applicable_skills_for(image_type) if s.effects]
    effects = effects_vector(applied)

    base_cb = float(auto_paint_kwargs.get("contrast_boost") or 0.25)
    base_cs = float(auto_paint_kwargs.get("complementary_shadow") or 0.12)

    cb = clamp_effect("contrast_boost", base_cb + effects.get("contrast_boost", 0.0))
    cs = clamp_effect("complementary_shadow", base_cs + effects.get("complementary_shadow", 0.0))

    base_cr = int(auto_paint_kwargs.get("critique_rounds") or 0)
    delta_cr = int(round(clamp_effect("critique_rounds", effects.get("critique_rounds", 0.0))))
    cr = base_cr + delta_cr

    pd_bias = clamp_effect("painterly_details_bias", effects.get("painterly_details_bias", 0.0))
    pd = bool(auto_paint_kwargs.get("painterly_details")) or pd_bias >= 0.5

    effective_style = style_mode
    auto_style = None
    if style_mode is None:
        scores = {
            mode: clamp_effect(f"{mode}_bias", effects.get(f"{mode}_bias", 0.0))
            for mode in ("van_gogh", "tenebrism", "pointillism", "engraving")
        }
        best_mode, best_score = max(scores.items(), key=lambda x: (x[1], -ord(x[0][0])))
        if best_score >= 0.5:
            effective_style = best_mode
            auto_style = best_mode

    effective_kwargs = dict(auto_paint_kwargs)
    effective_kwargs["contrast_boost"] = cb
    effective_kwargs["complementary_shadow"] = cs
    effective_kwargs["painterly_details"] = pd
    effective_kwargs["critique_rounds"] = cr

    effective_params = {
        "image_type": image_type,
        "contrast_boost": round(cb, 4),
        "complementary_shadow": round(cs, 4),
        "critique_rounds": cr,
        "painterly_details": pd,
        "style_mode": effective_style,
        "style_mode_auto": auto_style,
        "deltas": {
            "contrast_boost": round(cb - base_cb, 4),
            "complementary_shadow": round(cs - base_cs, 4),
            "critique_rounds": cr - base_cr,
            "painterly_details_activated_by_skills": (not auto_paint_kwargs.get("painterly_details")) and pd,
        },
    }
    applied_summary = [
        {"name": s.name, "confidence": s.confidence, "effects": s.effects,
         "scope": s.scope_types or ["*"]}
        for s in applied
    ]
    return effective_style, effective_kwargs, effective_params, applied_summary
