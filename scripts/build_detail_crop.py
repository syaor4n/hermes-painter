"""Build gallery/learning/detail_crop.png — a 4× zoom on where cold and
primed canvases diverge most.

The cold→primed SSIM delta is small by design, and full-canvas viewing
can make it look like nothing changed. This helper finds the 128×128
patch with the biggest Euclidean pixel difference between the two
canvases, crops it from each, upscales nearest-neighbor to 512×512, and
composes them side-by-side with a caption that locates the region.

Reads `gallery/learning/{run_cold,run_primed}.png` by default;
writes `gallery/learning/detail_crop.png`.

Run:
    .venv/bin/python scripts/build_detail_crop.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "gallery" / "learning"

CROP_SIZE = 128        # source crop edge in the 512×512 canvas
ZOOM = 4               # upscale factor (128 → 512)
SEARCH_STRIDE = 8      # pixel stride when sweeping for the max-diff patch


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def _find_max_diff_patch(
    a: np.ndarray, b: np.ndarray, size: int, stride: int
) -> tuple[int, int, float]:
    """Return (y, x, total_diff) for the size×size window with the
    highest summed pixel-distance between a and b."""
    diff = np.linalg.norm(a.astype(np.int16) - b.astype(np.int16), axis=2)
    h, w = diff.shape
    if h < size or w < size:
        raise ValueError(f"images too small: {h}x{w} < {size}x{size}")

    best = (0, 0, -1.0)
    for y in range(0, h - size + 1, stride):
        for x in range(0, w - size + 1, stride):
            total = float(diff[y : y + size, x : x + size].sum())
            if total > best[2]:
                best = (y, x, total)
    return best


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_detail_crop(
    cold_path: Path,
    primed_path: Path,
    out_path: Path,
    *,
    crop_size: int = CROP_SIZE,
    zoom: int = ZOOM,
    stride: int = SEARCH_STRIDE,
) -> dict:
    """Write the 4× zoom side-by-side. Returns metadata {x,y,crop_size,mean_diff}."""
    cold = _load_rgb(cold_path)
    primed = _load_rgb(primed_path)
    if cold.shape != primed.shape:
        raise ValueError(f"shape mismatch: {cold.shape} vs {primed.shape}")

    y, x, total = _find_max_diff_patch(cold, primed, crop_size, stride)
    mean_diff = total / (crop_size * crop_size)

    cold_crop = Image.fromarray(cold[y : y + crop_size, x : x + crop_size])
    primed_crop = Image.fromarray(primed[y : y + crop_size, x : x + crop_size])

    zoomed = crop_size * zoom
    cold_big = cold_crop.resize((zoomed, zoomed), Image.NEAREST)
    primed_big = primed_crop.resize((zoomed, zoomed), Image.NEAREST)

    gap = 16
    label_band = 32
    caption_band = 40
    total_w = 2 * zoomed + gap
    total_h = zoomed + label_band + caption_band

    canvas = Image.new("RGB", (total_w, total_h), (248, 248, 246))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(16)
    mono = _load_font(13)

    canvas.paste(cold_big, (0, 0))
    canvas.paste(primed_big, (zoomed + gap, 0))

    # Labels under each crop
    for i, label in enumerate(("cold (detail)", "primed (detail)")):
        tx = i * (zoomed + gap) + (zoomed - draw.textlength(label, font=font)) / 2
        draw.text((tx, zoomed + 6), label, fill=(40, 40, 40), font=font)

    # Caption strip with coordinates + mean diff
    caption_y = zoomed + label_band
    draw.rectangle(
        [0, caption_y, total_w, caption_y + caption_band],
        fill=(250, 248, 244),
    )
    draw.line(
        [0, caption_y, total_w, caption_y], fill=(210, 205, 195), width=1
    )
    caption = (
        f"4× zoom on the 128×128 patch with the largest color delta "
        f"(source coords y={y} x={x},  mean per-pixel RGB distance {mean_diff:.2f}). "
        f"The region is where the applied contrast_boost skill had the most "
        f"visible effect."
    )
    # Wrap caption to two lines if needed
    words = caption.split()
    line_a, line_b = "", ""
    for w in words:
        test = (line_a + " " + w).strip()
        if draw.textlength(test, font=mono) < total_w - 24:
            line_a = test
        else:
            line_b = (line_b + " " + w).strip()
    draw.text((12, caption_y + 4), line_a, fill=(55, 55, 70), font=mono)
    if line_b:
        draw.text((12, caption_y + 20), line_b, fill=(55, 55, 70), font=mono)

    canvas.save(out_path)
    return {"x": x, "y": y, "crop_size": crop_size, "mean_diff": round(mean_diff, 3)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cold", type=Path, default=GALLERY / "run_cold.png")
    ap.add_argument("--primed", type=Path, default=GALLERY / "run_primed.png")
    ap.add_argument("--out", type=Path, default=GALLERY / "detail_crop.png")
    ap.add_argument("--crop-size", type=int, default=CROP_SIZE)
    ap.add_argument("--zoom", type=int, default=ZOOM)
    args = ap.parse_args()

    for p in (args.cold, args.primed):
        if not p.exists():
            ap.error(f"input not found: {p}")

    meta = build_detail_crop(
        args.cold,
        args.primed,
        args.out,
        crop_size=args.crop_size,
        zoom=args.zoom,
    )
    size_kb = args.out.stat().st_size // 1024
    print(
        f"[detail-crop] wrote {args.out}  "
        f"patch=({meta['x']}, {meta['y']}) {meta['crop_size']}px  "
        f"mean_diff={meta['mean_diff']}  "
        f"size={size_kb} KB"
    )


if __name__ == "__main__":
    main()
