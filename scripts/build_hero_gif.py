"""Build the README hero GIF: animated cross-fade through the learning arc.

Reads gallery/learning/run_00_cold.png → run_05_primed.png → run_15_primed.png
and produces gallery/learning/hero_arc.gif — a looping animation that
hold each snapshot for ~1s, cross-fades into the next over ~10 frames,
with a small caption strip ("cold" / "primed x5" / "primed x15") at the
bottom.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "gallery" / "learning"

SNAPSHOTS = [
    (GALLERY / "run_00_cold.png", "cold (0 priming runs)"),
    (GALLERY / "run_05_primed.png", "primed after 5"),
    (GALLERY / "run_15_primed.png", "primed after 15"),
]

FRAME_SIZE = 320                  # 512 → 320 for small file size
CAPTION_HEIGHT = 32
HOLD_FRAMES = 14                  # ~1s at 70ms/frame
FADE_FRAMES = 6                   # ~0.4s cross-fade
FRAME_MS = 70
PALETTE_COLORS = 128              # quantize to 128-color palette to shrink GIF
OUTPUT = GALLERY / "hero_arc.gif"


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


def main() -> None:
    frames_rgb = [(_load_square(p), c) for p, c in SNAPSHOTS]
    font = _load_font()

    composed = [_compose(img, cap, font) for img, cap in frames_rgb]

    out_frames: list[Image.Image] = []
    durations: list[int] = []

    n = len(composed)
    for i in range(n):
        cur = composed[i]
        nxt = composed[(i + 1) % n]
        cur_img, cur_cap = frames_rgb[i]
        nxt_img, nxt_cap = frames_rgb[(i + 1) % n]

        # Hold current frame
        for _ in range(HOLD_FRAMES):
            out_frames.append(cur)
            durations.append(FRAME_MS)

        # Cross-fade image; cut captions at the midpoint for readability
        for f in range(1, FADE_FRAMES):
            t = f / FADE_FRAMES
            blended_img = Image.blend(cur_img, nxt_img, t)
            caption = cur_cap if t < 0.5 else nxt_cap
            out_frames.append(_compose(blended_img, caption, font))
            durations.append(FRAME_MS)

    # Quantize to an adaptive palette for smaller GIF size; all frames share
    # the first frame's palette so transitions don't re-dither noisily.
    quantized = [f.quantize(colors=PALETTE_COLORS, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
                 for f in out_frames]

    quantized[0].save(
        OUTPUT,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"[hero-gif] wrote {OUTPUT}  frames={len(out_frames)}  "
          f"size={OUTPUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
