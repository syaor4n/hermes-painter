"""Image-similarity metrics + heatmap + score_plan (imagination mode)."""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim

from . import local_renderer


def _to_np(png_bytes: bytes, size: tuple[int, int] = (512, 512)) -> np.ndarray:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    return np.asarray(img, dtype=np.float32) / 255.0


def _ms_ssim(t: np.ndarray, c: np.ndarray, levels: int = 3) -> float:
    """Cheap multi-scale SSIM: average SSIM across `levels` pyramid levels."""
    scores: list[float] = []
    ti, ci = t, c
    for _ in range(levels):
        if min(ti.shape[:2]) < 32:
            break
        scores.append(float(ssim(ti, ci, channel_axis=2, data_range=1.0)))
        h, w = ti.shape[:2]
        new = (h // 2, w // 2)
        ti = np.asarray(Image.fromarray((ti * 255).astype(np.uint8)).resize(new[::-1], Image.LANCZOS), dtype=np.float32) / 255.0
        ci = np.asarray(Image.fromarray((ci * 255).astype(np.uint8)).resize(new[::-1], Image.LANCZOS), dtype=np.float32) / 255.0
    return float(np.mean(scores)) if scores else 0.0


def _detail_fidelity(t: np.ndarray, c: np.ndarray, sigma: float = 1.5) -> dict[str, float]:
    """Edge-density agreement between canvas and target. Useful for detail
    precision where SSIM is too blunt (averages over 7×7 windows).

    Returns:
      - target_density, canvas_density : fraction of pixels flagged as edges
      - ratio  : canvas_density / target_density (1.0 = ideal)
      - iou    : intersection-over-union of edge pixels (0..1, higher=better)
      - fidelity : geometric mean of min(ratio, 1/ratio) and iou — single
                   score in [0,1], higher=better detail preservation
    """
    from skimage import feature
    tg = t.mean(axis=2)
    cg = c.mean(axis=2)
    t_edges = feature.canny(tg, sigma=sigma)
    c_edges = feature.canny(cg, sigma=sigma)
    td = float(t_edges.mean())
    cd = float(c_edges.mean())
    ratio = cd / td if td > 1e-6 else 0.0
    # IoU on edges
    inter = float((t_edges & c_edges).sum())
    union = float((t_edges | c_edges).sum())
    iou = inter / union if union > 0 else 0.0
    # Symmetric ratio penalty: ideal is 1.0, penalize both under- and over-texturing
    balance = min(ratio, 1.0 / ratio) if ratio > 1e-6 else 0.0
    fidelity = (balance * iou) ** 0.5 if (balance > 0 and iou > 0) else 0.0
    return {
        "target_density": td,
        "canvas_density": cd,
        "ratio": ratio,
        "iou": iou,
        "fidelity": fidelity,
    }


def score(target_png: bytes, current_png: bytes,
          *, with_detail: bool = True) -> dict:
    """Full score dict: SSIM, MS-SSIM, MSE, composite, and (optionally)
    detail_fidelity. Set with_detail=False to skip the canny computation
    when timing matters."""
    t = _to_np(target_png)
    c = _to_np(current_png)
    mse = float(np.mean((t - c) ** 2))
    s = float(ssim(t, c, channel_axis=2, data_range=1.0))
    ms = _ms_ssim(t, c)
    composite = float(0.5 * (1 - s) + 0.5 * mse)
    out: dict = {"ssim": s, "ms_ssim": ms, "mse": mse, "composite": composite}
    if with_detail:
        out["detail"] = _detail_fidelity(t, c)
    return out


def heatmap_bytes(
    target_png: bytes, current_png: bytes, *, gamma: float = 0.7
) -> bytes:
    """Per-pixel error map as PNG. Black = match, white = maximum divergence.

    gamma < 1 boosts small errors (more visible), gamma > 1 suppresses noise.
    """
    t = _to_np(target_png)
    c = _to_np(current_png)
    err = np.sqrt(np.mean((t - c) ** 2, axis=2))
    err = np.power(err, gamma)
    err = (err - err.min()) / max(err.max() - err.min(), 1e-6)
    img = Image.fromarray((err * 255).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def region_errors(
    target_png: bytes, current_png: bytes, *, grid: int = 8
) -> list[dict[str, Any]]:
    """Return a list of cells sorted by error desc.

    Each cell = {x, y, w, h, error, target_mean (RGB), current_mean (RGB)}.
    Useful so the planner can be told "the top-3 worst regions are…".
    """
    t = _to_np(target_png)
    c = _to_np(current_png)
    h, w = t.shape[:2]
    cell_h = h // grid
    cell_w = w // grid
    cells: list[dict[str, Any]] = []
    for gy in range(grid):
        for gx in range(grid):
            y0 = gy * cell_h
            x0 = gx * cell_w
            y1 = (gy + 1) * cell_h if gy < grid - 1 else h
            x1 = (gx + 1) * cell_w if gx < grid - 1 else w
            t_block = t[y0:y1, x0:x1]
            c_block = c[y0:y1, x0:x1]
            err = float(np.mean((t_block - c_block) ** 2))
            cells.append({
                "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                "error": err,
                "target_rgb": [int(v * 255) for v in t_block.mean(axis=(0, 1)).tolist()],
                "current_rgb": [int(v * 255) for v in c_block.mean(axis=(0, 1)).tolist()],
            })
    cells.sort(key=lambda x: x["error"], reverse=True)
    return cells


def score_plan(
    plan: dict[str, Any],
    *,
    target_png: bytes,
    current_png: bytes | None = None,
) -> dict[str, float]:
    """Imagine the outcome of `plan` (render locally, score against target).

    This is the agent's "imagination": simulate a candidate plan without
    committing it to the real canvas. Returns the same dict as `score()`
    plus a `delta` field (improvement vs. current).
    """
    imagined = local_renderer.render_to_png(
        plan.get("strokes", []), base_png=current_png
    )
    out = score(target_png, imagined)
    if current_png is not None:
        base = score(target_png, current_png)
        out["delta_ssim"] = out["ssim"] - base["ssim"]
        out["delta_mse"] = base["mse"] - out["mse"]  # positive = better
        out["delta_composite"] = base["composite"] - out["composite"]
    return out
