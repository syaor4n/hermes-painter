"""Reflect on a finished run directory and write a signed skill.

Usage:
  python scripts/reflect.py runs/20260420_162504_photo
  python scripts/reflect.py runs/20260420_162504_photo --image-type portrait --tags portrait,warm

The reflection is deterministic and heuristic — for richer lessons, the CLI
agent itself can call the `save_skill` tool at the end of a run with a
self-authored body.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from painter import reflection


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--image-type", type=str, default=None)
    ap.add_argument("--tags", type=str, default="", help="comma-separated tags")
    args = ap.parse_args()

    if not args.run_dir.exists():
        raise SystemExit(f"run dir not found: {args.run_dir}")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] or None
    path = reflection.reflect(
        args.run_dir,
        image_type=args.image_type,
        tags=tags,
    )
    if path:
        print(f"wrote {path}")
    else:
        print("no significant improvement — no skill written")


if __name__ == "__main__":
    main()
