"""Deterministic detectors for the painter failure-mode taxonomy.

Each detector takes the current canvas bytes + (optionally) target bytes
+ (optionally) recent stroke list, and returns a finding dict or None.

Returning None means "not detected". Returning a dict means the failure
was observed; include `severity` (1..3) and `metric` (a short evidence
string the agent can cite in a reflection).

These are intentionally simple. If a heuristic is wrong, FIX the heuristic
don't remove it — missing a mode is worse than a false positive because
the agent has no other way to know.
"""
from __future__ import annotations

import io
import sys
from typing import Any

import numpy as np
from PIL import Image


# --- Helper loaders ---

def _load_rgb(png_bytes: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGB"))


def _load_gray(png_bytes: bytes) -> np.ndarray:
    return _load_rgb(png_bytes).mean(axis=2)


# --- Detectors (one per failure mode) ---

def detect_too_dark_outlines(strokes: list[dict] | None, **_) -> dict | None:
    """TOO_DARK_OUTLINES — near-pure-black in thin finishing strokes."""
    if not strokes:
        return None
    thin = [s for s in strokes
            if s.get("type") in ("polyline", "bezier")
            and int(s.get("width", 2)) <= 2]
    if not thin:
        return None
    n_dark = 0
    for s in thin:
        c = s.get("color", "#ffffff")
        if isinstance(c, str) and len(c) == 7 and c.startswith("#"):
            r = int(c[1:3], 16); g = int(c[3:5], 16); b = int(c[5:7], 16)
            if r + g + b < 30 and abs(r - g) < 6 and abs(g - b) < 6:
                n_dark += 1
    ratio = n_dark / len(thin)
    if ratio <= 0.05:
        return None
    return {
        "mode": "TOO_DARK_OUTLINES",
        "severity": 3 if ratio > 0.15 else 2,
        "metric": f"{ratio:.1%} of thin strokes are near-black ({n_dark}/{len(thin)})",
        "fix": "Ensure color_source='dark' uses _tonal_dark, not #101010. Reduce contour budget or lower alpha.",
    }


def detect_subject_lost_in_bg(canvas: bytes, target: bytes,
                                mask: bytes | None = None, **_) -> dict | None:
    """SUBJECT_LOST_IN_BG — silhouette of subject not distinguishable.

    v11.1 (G1 fix): only fire when the TARGET itself has DOF structure.
    Paintings, ukiyo-e, engravings, ads — anything without real lens blur —
    has uniform detail across subject and background, so this heuristic
    (designed for DOF photos) must not apply.
    """
    if mask is None:
        return None
    m = _load_gray(mask)
    fg_mask = m > 100
    if fg_mask.sum() < 1000:
        return None

    # Pre-check: does the TARGET have DOF? If target variance inside ≈ outside,
    # the source isn't a DOF photo — skip this detector entirely.
    t = _load_rgb(target).astype(np.float32)
    t_in = t[fg_mask]
    t_out = t[~fg_mask]
    if len(t_in) < 100 or len(t_out) < 100:
        return None
    t_ratio = float(t_in.std(axis=0).mean() / (t_out.std(axis=0).mean() + 1e-6))
    # Threshold 1.15: subject needs ~15% more local variance than bg for DOF.
    if t_ratio < 1.15:
        return None

    # Now the canvas check, but compare PRESERVATION of the target's ratio
    # (not absolute canvas ratio). The canvas should maintain or amplify it.
    c = _load_rgb(canvas).astype(np.float32)
    c_in = c[fg_mask]
    c_out = c[~fg_mask]
    c_ratio = float(c_in.std(axis=0).mean() / (c_out.std(axis=0).mean() + 1e-6))
    preservation = c_ratio / t_ratio
    if preservation >= 0.70:
        return None
    return {
        "mode": "SUBJECT_LOST_IN_BG",
        "severity": 3 if preservation < 0.45 else 2,
        "metric": f"canvas/target variance preservation = {preservation:.2f} "
                   f"(target DOF ratio {t_ratio:.2f}, canvas {c_ratio:.2f})",
        "fix": "Raise focus_falloff to 0.5, set contour mask_boost=3.0, lower detail mask_threshold.",
    }


def detect_muddy_underpaint(canvas: bytes, target: bytes, **_) -> dict | None:
    """MUDDY_UNDERPAINT — canvas variance much lower than target's."""
    c = _load_rgb(canvas).astype(np.float32)
    t = _load_rgb(target).astype(np.float32)
    # Mean per-pixel std across channels
    canvas_std = float(c.std(axis=2).mean())
    target_std = float(t.std(axis=2).mean())
    if target_std < 5:
        # Target itself is uniform (e.g., sky) — not a bug
        return None
    ratio = canvas_std / target_std
    if ratio >= 0.5:
        return None
    return {
        "mode": "MUDDY_UNDERPAINT",
        "severity": 2 if ratio < 0.3 else 1,
        "metric": f"canvas color-variance / target = {ratio:.2f}",
        "fix": "Raise contrast_boost to 0.35-0.4. Reduce grid cell size (use smaller grid_size).",
    }


def detect_over_rendered_bg(strokes: list[dict] | None, mask: bytes | None = None, **_) -> dict | None:
    """OVER_RENDERED_BG — too many finishing strokes outside the saliency mask."""
    if not strokes or mask is None:
        return None
    m = _load_gray(mask)
    finishing = [s for s in strokes
                 if s.get("type") in ("polyline", "bezier", "dab")]
    if len(finishing) < 20:
        return None
    inside, outside = 0, 0
    for s in finishing:
        # Extract a representative (x, y) per stroke
        if s.get("type") == "dab":
            x, y = int(s.get("x", 0)), int(s.get("y", 0))
        else:
            pts = s.get("points") or []
            if not pts:
                continue
            if len(pts) >= 4 and isinstance(pts[0], list):
                # bezier: midpoint between p0 and p1
                x = (int(pts[0][0]) + int(pts[-1][0])) // 2
                y = (int(pts[0][1]) + int(pts[-1][1])) // 2
            else:
                mid = pts[len(pts) // 2]
                x, y = int(mid[0]), int(mid[1])
        x = max(0, min(511, x)); y = max(0, min(511, y))
        if m[y, x] > 100:
            inside += 1
        else:
            outside += 1
    total = inside + outside
    if total < 20:
        return None
    out_ratio = outside / total
    if out_ratio <= 0.55:
        return None
    return {
        "mode": "OVER_RENDERED_BG",
        "severity": 2 if out_ratio > 0.7 else 1,
        "metric": f"{out_ratio:.1%} of finishing strokes outside saliency mask",
        "fix": "Pass mask_path to detail_stroke_plan and contour_stroke_plan. Raise mask_threshold.",
    }


def detect_under_covered(canvas: bytes, **_) -> dict | None:
    """UNDER_COVERED — off-white linen visible in large patches."""
    c = _load_rgb(canvas).astype(np.float32)
    # Linen base is #fbf7ee ≈ (251, 247, 238). Count near-base pixels.
    base = np.array([251, 247, 238], dtype=np.float32)
    dist = np.abs(c - base).sum(axis=2)
    near_base_frac = float((dist < 20).mean())
    # >10% pixels untouched = under-covered
    if near_base_frac <= 0.10:
        return None
    return {
        "mode": "UNDER_COVERED",
        "severity": 3 if near_base_frac > 0.25 else 2,
        "metric": f"{near_base_frac:.1%} of canvas still near the linen base color",
        "fix": "Rerun gap-fill with lower threshold; increase underpainting pass count.",
    }


def detect_over_rendered_fg(strokes: list[dict] | None, **_) -> dict | None:
    """OVER_RENDERED_FG — total finishing strokes > 40% of underpainting.

    Without the raw per-phase breakdown we approximate: count thin
    (width ≤ 2) finishing strokes vs brush strokes.
    """
    if not strokes:
        return None
    brush = sum(1 for s in strokes if s.get("type") == "brush")
    finishing = sum(1 for s in strokes
                    if s.get("type") in ("polyline", "bezier", "dab")
                    and int(s.get("width", 2)) <= 2)
    if brush < 100:
        return None
    ratio = finishing / brush
    if ratio <= 0.40:
        return None
    return {
        "mode": "OVER_RENDERED_FG",
        "severity": 2 if ratio > 0.6 else 1,
        "metric": f"finishing/brush ratio = {ratio:.2f} (target ≤ 0.40)",
        "fix": "Lower detail alphas and contour budget; cap finishing at 25% of underpaint strokes.",
    }


def detect_hard_banding(canvas: bytes, **_) -> dict | None:
    """HARD_BANDING — FFT peaks at grid frequency in low-frequency regions."""
    g = _load_gray(canvas)
    # Sample a 128×128 patch from a smooth-ish region (upper-left, typically sky)
    patch = g[30:158, 30:158]
    # FFT magnitude; look for peaks at frequencies corresponding to 16 or 21 px period
    F = np.fft.rfft2(patch)
    mag = np.abs(F)
    # Zero out DC
    mag[0, 0] = 0
    # Expected grid periods (cell widths) for common grid sizes
    h, w = patch.shape
    candidates = []
    for cell_px in (16, 21, 32):
        f_row = int(round(h / cell_px))
        f_col = int(round(w / cell_px))
        if 1 <= f_row < mag.shape[0] and 1 <= f_col < mag.shape[1]:
            candidates.append(float(mag[f_row, f_col]))
    if not candidates:
        return None
    peak = max(candidates)
    mean = float(mag.mean())
    ratio = peak / (mean + 1e-6)
    if ratio <= 8.0:
        return None
    return {
        "mode": "HARD_BANDING",
        "severity": 2 if ratio > 14 else 1,
        "metric": f"FFT peak at grid frequency is {ratio:.1f}× mean",
        "fix": "Lengthen underpainting strokes (1.4× cell size). Add a fog phase if subject is atmospheric.",
    }


def detect_direction_mismatch(strokes: list[dict] | None, target: bytes, **_) -> dict | None:
    """DIRECTION_MISMATCH — underpainting strokes angle vs target local gradient."""
    if not strokes:
        return None
    brush_strokes = [s for s in strokes if s.get("type") == "brush"]
    if len(brush_strokes) < 30:
        return None
    # Compute target gradient orientation field (sobel)
    from scipy.ndimage import sobel
    gray = _load_gray(target)
    gx = sobel(gray, axis=1)
    gy = sobel(gray, axis=0)
    # Target "stroke direction" = perpendicular to gradient
    # Sample at brush stroke midpoints
    import math as _m
    disagreements = []
    for s in brush_strokes[:200]:  # cap for speed
        pts = s.get("points") or []
        if len(pts) < 3:
            continue
        p0, _, p2 = pts[0], pts[1], pts[-1]
        dx = p2[0] - p0[0]; dy = p2[1] - p0[1]
        if dx == 0 and dy == 0:
            continue
        stroke_angle = _m.atan2(dy, dx)  # radians
        mx = int(max(0, min(511, (p0[0] + p2[0]) // 2)))
        my = int(max(0, min(511, (p0[1] + p2[1]) // 2)))
        tgx = gx[my, mx]; tgy = gy[my, mx]
        tmag = (tgx * tgx + tgy * tgy) ** 0.5
        if tmag < 10:
            continue  # low-gradient, direction is arbitrary
        # Target stroke direction = perpendicular to gradient
        target_angle = _m.atan2(tgx, -tgy)  # rotate 90°
        # Angular difference, wrapped to [0, π/2] (strokes are undirected)
        diff = abs(((stroke_angle - target_angle + _m.pi / 2) % _m.pi) - _m.pi / 2)
        disagreements.append(diff)
    if len(disagreements) < 15:
        return None
    mean_diff = sum(disagreements) / len(disagreements)
    if mean_diff <= _m.pi / 3:
        return None
    return {
        "mode": "DIRECTION_MISMATCH",
        "severity": 1,
        "metric": f"mean angular disagreement = {_m.degrees(mean_diff):.0f}° (threshold 60°)",
        "fix": "Enable use_local_direction=True in auto_paint (per-cell structure tensor).",
    }


# --- Orchestrator ---

DETECTORS = [
    detect_too_dark_outlines,
    detect_subject_lost_in_bg,
    detect_muddy_underpaint,
    detect_over_rendered_bg,
    detect_under_covered,
    detect_over_rendered_fg,
    detect_hard_banding,
    detect_direction_mismatch,
]


def critique(canvas_bytes: bytes, target_bytes: bytes,
             mask_bytes: bytes | None = None,
             strokes: list[dict] | None = None) -> dict:
    """Run all detectors. Returns {findings, verdict, suggested_fixes}."""
    ctx = {"canvas": canvas_bytes, "target": target_bytes,
           "mask": mask_bytes, "strokes": strokes}
    findings: list[dict] = []
    for fn in DETECTORS:
        try:
            result = fn(**ctx)
        except Exception as e:
            # Never let a single detector break the whole critique, but do
            # surface it so a broken heuristic is visible (silent detector
            # failures were how MUDDY_UNDERPAINT went stale for a week).
            print(f"[failures] detector {fn.__name__} crashed: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            continue
        if result is not None:
            findings.append(result)
    max_sev = max((f["severity"] for f in findings), default=0)
    if max_sev >= 3:
        verdict = "fail"
    elif max_sev == 2:
        verdict = "warn"
    elif max_sev == 1:
        verdict = "minor"
    else:
        verdict = "ok"
    return {
        "findings": findings,
        "verdict": verdict,
        "suggested_fixes": [f["fix"] for f in findings if "fix" in f],
    }
