"""Build the README hero GIF: animated three-frame arc through the memory demo.

Reads the output of scripts/demo_memory_arc.py (target + run_cold.png +
run_primed.png) and produces gallery/learning/hero_arc.gif — a looping
animation holding each frame for ~1s with a short crossfade.

Default inputs: gallery/learning/{target.png, run_cold.png, run_primed.png}.
Override with --target / --cold / --primed CLI flags.

The GIF frames:
  1. the target reference image (what the agent is trying to paint)
  2. the cold run (apply_feedback=False, zero promoted skills)
  3. the primed run (apply_feedback=True after 5 priming paints)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "gallery" / "learning"

# Visual tuning
FRAME_SIZE = 320
CAPTION_HEIGHT = 32
HOLD_FRAMES = 14                  # ~1s at 70ms/frame
FADE_FRAMES = 6                   # ~0.4s crossfade
FRAME_MS = 70
PALETTE_COLORS = 128


def _load_square(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return im.resize((FRAME_SIZE, FRAME_SIZE), Image.LANCZOS)


def _load_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(p, 18)
        except OSError:
            continue
    return ImageFont.load_default()


def _compose(image: Image.Image, caption: str, font) -> Image.Image:
    canvas = Image.new("RGB", (FRAME_SIZE, FRAME_SIZE + CAPTION_HEIGHT), (248, 248, 246))
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    text_w = draw.textlength(caption, font=font)
    draw.text(
        ((FRAME_SIZE - text_w) / 2, FRAME_SIZE + (CAPTION_HEIGHT - 18) / 2 - 2),
        caption,
        fill=(50, 50, 60),
        font=font,
    )
    return canvas


def build(target_path: Path, cold_path: Path, primed_path: Path, out_path: Path) -> None:
    snapshots = [
        (target_path, "target"),
        (cold_path, "cold (0 priming runs)"),
        (primed_path, "primed after 5 priming runs"),
    ]
    frames_rgb = [(_load_square(p), c) for p, c in snapshots]
    font = _load_font()

    composed = [_compose(img, cap, font) for img, cap in frames_rgb]

    out_frames: list[Image.Image] = []
    durations: list[int] = []

    n = len(composed)
    for i in range(n):
        cur = composed[i]
        cur_img, cur_cap = frames_rgb[i]
        nxt_img, nxt_cap = frames_rgb[(i + 1) % n]

        for _ in range(HOLD_FRAMES):
            out_frames.append(cur)
            durations.append(FRAME_MS)

        for f in range(1, FADE_FRAMES):
            t = f / FADE_FRAMES
            blended_img = Image.blend(cur_img, nxt_img, t)
            caption = cur_cap if t < 0.5 else nxt_cap
            out_frames.append(_compose(blended_img, caption, font))
            durations.append(FRAME_MS)

    quantized = [
        f.quantize(colors=PALETTE_COLORS, method=Image.MEDIANCUT,
                    dither=Image.FLOYDSTEINBERG)
        for f in out_frames
    ]

    quantized[0].save(
        out_path,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"[hero-gif] wrote {out_path}  frames={len(out_frames)}  "
          f"size={out_path.stat().st_size // 1024} KB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=Path, default=GALLERY / "target.png")
    ap.add_argument("--cold", type=Path, default=GALLERY / "run_cold.png")
    ap.add_argument("--primed", type=Path, default=GALLERY / "run_primed.png")
    ap.add_argument("--out", type=Path, default=GALLERY / "hero_arc.gif")
    args = ap.parse_args()

    for path in (args.target, args.cold, args.primed):
        if not path.exists():
            ap.error(f"input not found: {path}")

    build(args.target, args.cold, args.primed, args.out)


if __name__ == "__main__":
    main()
