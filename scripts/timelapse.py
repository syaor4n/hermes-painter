"""Stitch step_*.png frames from a run dir into an animated GIF.

Usage:
  python scripts/timelapse.py runs/20260420_162504_photo
  python scripts/timelapse.py runs/painting_forest_latest --fps 4 --hold 1.5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def build_gif(run_dir: Path, out: Path, fps: float, hold_last: float) -> Path:
    if fps <= 0:
        raise SystemExit(f"fps must be > 0, got {fps}")
    frames = sorted(run_dir.glob("step_*.png"))
    if not frames:
        raise SystemExit(f"No step_*.png frames in {run_dir}")
    images = [Image.open(f).convert("P", palette=Image.ADAPTIVE) for f in frames]
    # Prepend the target as frame 0 if present
    target = run_dir / "target.png"
    if target.exists():
        images.insert(0, Image.open(target).convert("P", palette=Image.ADAPTIVE))

    per_frame_ms = max(60, int(1000 / fps))
    durations = [per_frame_ms] * len(images)
    if hold_last > 0 and durations:
        durations[-1] = int(hold_last * 1000)

    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        optimize=True,
        duration=durations,
        loop=0,
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--hold", type=float, default=2.0, help="seconds to hold the last frame")
    ap.add_argument("--phase-strip", action="store_true",
                    help="Emit an 8-panel horizontal strip labeled with "
                         "phase name and blend weight, instead of a GIF.")
    ap.add_argument("--strip-labels", type=str, default=None,
                    help="Comma-separated 8 labels, e.g. "
                         "'underpaint(0.00),fog(0.14),...'. If omitted, "
                         "falls back to phase index.")
    args = ap.parse_args()

    run_dir = args.run_dir

    if args.phase_strip:
        from PIL import Image, ImageDraw, ImageFont
        frames = sorted(run_dir.glob("step_*.png"))
        if len(frames) < 8:
            print(f"[timelapse] --phase-strip needs >=8 step images, "
                  f"found {len(frames)}; using all {len(frames)} frames",
                  file=sys.stderr)
        # Pick 8 evenly-spaced frames if more than 8, else use what we have
        if len(frames) >= 8:
            indices = [int(i * (len(frames) - 1) / 7) for i in range(8)]
            picked = [frames[i] for i in indices]
        else:
            picked = frames
        images = [Image.open(p).convert("RGB") for p in picked]
        w, h = images[0].size
        label_h = 28
        strip = Image.new("RGB", (w * len(images), h + label_h), (255, 255, 255))
        labels = (args.strip_labels.split(",")
                  if args.strip_labels
                  else [f"phase {i}" for i in range(len(images))])
        labels = labels[:len(images)] + [""] * (len(images) - len(labels))
        draw = ImageDraw.Draw(strip)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        for i, (img, lbl) in enumerate(zip(images, labels)):
            strip.paste(img, (i * w, label_h))
            draw.text((i * w + 8, 6), lbl, fill=(0, 0, 0), font=font)
        out_path = run_dir / "phase_strip.png"
        strip.save(out_path)
        print(f"[timelapse] wrote {out_path}")
        return

    out = args.out or (run_dir / "timelapse.gif")
    path = build_gif(run_dir, out, args.fps, args.hold)
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
