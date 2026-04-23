"""Download a curated set of real Unsplash photos into targets/unsplash/.

Pulls from images.unsplash.com with known-stable photo IDs spanning a range
of image_types (dark, high_contrast, muted, balanced, bright) so the
learning loop accumulates skills across the type spectrum.

Falls back to picsum.photos (which is itself Unsplash-curated) with a
deterministic seed when a direct Unsplash URL fails, so the script always
produces N real photos.

Usage:
  python scripts/download_unsplash.py            # download the full set
  python scripts/download_unsplash.py --limit 10
  python scripts/download_unsplash.py --out targets/unsplash_v2
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Curated list: (local_name, unsplash_photo_id, expected_image_type_hint).
# Photo IDs picked for subject + mood diversity. If any returns 404, the
# picsum fallback covers us.
CURATED = [
    # --- dark / night ---
    ("night_city",          "photo-1470225620780-dba8ba36b745",  "dark"),
    ("candle_room",         "photo-1481931098730-318b6f776db0",  "dark"),
    ("dark_forest",         "photo-1470071459604-3b5ec3a7fe05",  "dark"),
    ("starry_sky",          "photo-1441974231531-c6227db76b6e",  "dark"),
    ("storm_clouds",        "photo-1457269449834-928af64c684d",  "dark"),
    # --- high_contrast / strong light ---
    ("silhouette_sunset",   "photo-1464822759023-fed622ff2c3b",  "high_contrast"),
    ("neon_alley",          "photo-1493514789931-586cb221d7a7",  "high_contrast"),
    ("lightning",           "photo-1429552077091-836152271555",  "high_contrast"),
    ("bw_portrait",         "photo-1463453091185-61582044d556",  "high_contrast"),
    ("sun_through_trees",   "photo-1448375240586-882707db888b",  "high_contrast"),
    # --- muted / fog / pastel ---
    ("foggy_road",          "photo-1504450758481-7338eba7524a",  "muted"),
    ("misty_lake",          "photo-1475738197857-8bcb0c2c7faa",  "muted"),
    ("overcast_sea",        "photo-1505144808419-1957a94ca61e",  "muted"),
    ("pastel_interior",     "photo-1493809842364-78817add7ffb",  "muted"),
    ("gray_mountain",       "photo-1486870591958-9b9d0d1dda99",  "muted"),
    # --- balanced / classic landscape ---
    ("autumn_leaves",       "photo-1418065460487-3e41a6c84dc5",  "balanced"),
    ("mountain_lake",       "photo-1506905925346-21bda4d32df4",  "balanced"),
    ("riverside_village",   "photo-1499856871958-5b9627545d1a",  "balanced"),
    ("coffee_shop",         "photo-1445116572660-236099ec97a0",  "balanced"),
    ("wheat_field",         "photo-1464822759023-fed622ff2c3b",  "balanced"),
    # --- bright / high-key ---
    ("beach_noon",          "photo-1507525428034-b723cf961d3e",  "bright"),
    ("snow_field",          "photo-1478827217976-abaa2e16ee4d",  "bright"),
    ("white_architecture",  "photo-1503965830912-6d7b07921cd1",  "bright"),
    ("sunlit_hallway",      "photo-1486325212027-8081e485255e",  "bright"),
    ("cloudscape",          "photo-1502082553048-f009c37129b9",  "bright"),
]


def _download(url: str, out: Path, timeout: int = 30) -> tuple[bool, int]:
    """Fetch url into `out`. Returns (ok, bytes_written)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "painter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        # Sanity: JPEG or PNG magic
        if not (data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n"):
            return False, len(data)
        # Minimum size to reject error-page HTML disguised as JPG
        if len(data) < 8000:
            return False, len(data)
        out.write_bytes(data)
        return True, len(data)
    except (urllib.error.URLError, TimeoutError):
        return False, 0
    except Exception:
        return False, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="targets/unsplash",
                    help="destination directory (default: targets/unsplash)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap number of downloads (0 = all)")
    ap.add_argument("--size", type=int, default=800)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--overwrite", action="store_true",
                    help="re-download files that already exist")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    out_dir = (repo / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = CURATED if args.limit <= 0 else CURATED[: args.limit]
    n_ok = n_skipped = n_fallback = n_fail = 0
    print(f"[download] {len(entries)} targets → {out_dir}")

    for i, (name, photo_id, hint) in enumerate(entries, 1):
        out_path = out_dir / f"{name}.jpg"
        if out_path.exists() and not args.overwrite:
            n_skipped += 1
            print(f"  [{i:2}/{len(entries)}] {name:22} skip (exists)")
            continue

        # 1. Try direct Unsplash CDN
        direct = f"https://images.unsplash.com/{photo_id}?w={args.size}&q={args.quality}&fm=jpg"
        ok, nbytes = _download(direct, out_path)
        if ok:
            n_ok += 1
            print(f"  [{i:2}/{len(entries)}] {name:22} ok   ({nbytes//1024}KB, unsplash, hint={hint})")
            continue

        # 2. Fallback to picsum with a deterministic seed derived from name
        seed = int(hashlib.md5(name.encode()).hexdigest(), 16) % 10000
        picsum = f"https://picsum.photos/seed/{seed}/{args.size}/{args.size}"
        ok, nbytes = _download(picsum, out_path)
        if ok:
            n_fallback += 1
            print(f"  [{i:2}/{len(entries)}] {name:22} ok   ({nbytes//1024}KB, picsum seed={seed})")
        else:
            n_fail += 1
            print(f"  [{i:2}/{len(entries)}] {name:22} FAIL")
        # be polite to origins
        time.sleep(0.2)

    print(f"\n[download] ok={n_ok} fallback={n_fallback} skip={n_skipped} fail={n_fail}")
    final_count = len(list(out_dir.glob("*.jpg")))
    print(f"[download] {out_dir} now has {final_count} jpgs")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
