"""Repeatable ablation bench for detail precision.

Paints N targets through auto_paint (with feedback disabled to isolate pipeline
changes from accumulated skills), scores SSIM + MS-SSIM + detail_fidelity, and
writes a comparable row per target + an aggregate.

Use before/after a pipeline change to measure the real impact:

  python scripts/bench_detail.py --tag baseline
  # ...change pipeline...
  python scripts/bench_detail.py --tag after_impasto
  python scripts/bench_detail.py --compare baseline after_impasto
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from paint_lib import auto_paint
from painter.critic import score as score_fn

BENCH_TARGETS_SMALL = [
    ("targets/unsplash/old_man.jpg",        None),
    ("targets/unsplash/mountain.jpg",       None),
    ("targets/unsplash/night_city.jpg",     None),
    ("targets/unsplash/bird.jpg",           None),
    ("targets/masterworks/mona_lisa.jpg",   None),
]

# 28-target expanded bench covering all 5 image_types plus masterworks. Built
# from classification data; ratios reflect how many we have per type.
BENCH_TARGETS_LARGE = [
    # --- portraits / subjects (balanced / muted) ---
    ("targets/unsplash/old_man.jpg",        None),   # muted
    ("targets/unsplash/portrait.jpg",       None),   # balanced
    ("targets/unsplash/bw_portrait.jpg",    None),   # balanced
    ("targets/unsplash/cat.jpg",            None),   # balanced
    ("targets/unsplash/bird.jpg",           None),   # high_contrast
    ("targets/portrait.jpg",                None),   # preset
    # --- balanced landscapes / scenes ---
    ("targets/unsplash/mountain.jpg",       None),
    ("targets/unsplash/mountain_lake.jpg",  None),
    ("targets/unsplash/riverside_village.jpg", None),
    ("targets/unsplash/autumn_leaves.jpg",  None),
    ("targets/sunset.jpg",                  None),
    ("targets/forest.jpg",                  None),
    # --- high_contrast ---
    ("targets/unsplash/beach.jpg",          None),
    ("targets/unsplash/cloudscape.jpg",     None),
    ("targets/unsplash/snow_field.jpg",     None),
    ("targets/unsplash/interior.jpg",       None),
    ("targets/unsplash/misty_lake.jpg",     None),
    # --- dark ---
    ("targets/unsplash/night_city.jpg",     None),
    ("targets/unsplash/lightning.jpg",      None),
    ("targets/unsplash/starry_sky.jpg",     None),
    ("targets/unsplash/foggy_road.jpg",     None),
    ("targets/unsplash/neon_alley.jpg",     None),
    ("targets/night.jpg",                   None),
    # --- muted ---
    ("targets/unsplash/dark_forest.jpg",    None),
    # --- masterworks ---
    ("targets/masterworks/mona_lisa.jpg",   None),
    ("targets/masterworks/great_wave.jpg",  None),
    ("targets/masterworks/the_bedroom.jpg", None),
    ("targets/masterworks/water_lilies.jpg", None),
]

BENCH_TARGETS = BENCH_TARGETS_LARGE


def _bench_one(target_path: str, style_mode: str | None, seed: int,
                out_dir: Path) -> dict:
    t0 = time.time()
    result = auto_paint(target_path, seed=seed, verbose=False,
                        style_mode=style_mode,
                        apply_feedback=False,  # isolate pipeline
                        auto_reflect=False)
    elapsed = time.time() - t0
    canvas_bytes = Path("/tmp/painter_canvas.png").read_bytes()
    target_bytes = Path(target_path).read_bytes()
    s = score_fn(target_bytes, canvas_bytes, with_detail=True)

    stem = Path(target_path).stem
    out_path = out_dir / f"{stem}.png"
    out_path.write_bytes(canvas_bytes)

    return {
        "target": target_path,
        "image_type": result.get("image_type"),
        "style_mode": style_mode,
        "elapsed_s": round(elapsed, 2),
        "strokes": {
            "under": result.get("underpaint_strokes", 0),
            "edges": result.get("edge_strokes", 0),
            "mid_detail": result.get("mid_detail_strokes", 0),
            "fine_detail": result.get("fine_detail_strokes", 0),
            "contour": result.get("contour_strokes", 0),
            "highlight": result.get("highlight_strokes", 0),
            "critique": result.get("critique_strokes", 0),
        },
        "coverage": result.get("coverage"),
        "ssim": round(s["ssim"], 4),
        "ms_ssim": round(s["ms_ssim"], 4),
        "mse": round(s["mse"], 5),
        "detail_fidelity": round(s["detail"]["fidelity"], 4),
        "detail_iou": round(s["detail"]["iou"], 4),
        "detail_ratio": round(s["detail"]["ratio"], 4),
        "canvas_png": str(out_path),
    }


def _bench(args) -> dict:
    tag = args.tag
    seed = args.seed
    targets = BENCH_TARGETS[: args.limit] if args.limit > 0 else BENCH_TARGETS

    out_dir = REPO / "benches" / f"detail_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    print(f"[bench:{tag}] {len(targets)} targets · seed={seed}")
    for i, (tgt, style) in enumerate(targets, 1):
        print(f"  [{i}/{len(targets)}] {tgt} style={style or 'auto'}")
        try:
            row = _bench_one(tgt, style, seed, out_dir)
            print(f"    ssim={row['ssim']:.3f} ms_ssim={row['ms_ssim']:.3f} "
                  f"detail_fidelity={row['detail_fidelity']:.3f} "
                  f"strokes={sum(row['strokes'].values())}")
            rows.append(row)
        except Exception as e:
            print(f"    ! failed: {type(e).__name__}: {e}")
            rows.append({"target": tgt, "error": str(e)})

    # Aggregate
    ok = [r for r in rows if "ssim" in r]
    agg = {
        "n": len(ok),
        "mean_ssim": round(sum(r["ssim"] for r in ok) / max(1, len(ok)), 4),
        "mean_ms_ssim": round(sum(r["ms_ssim"] for r in ok) / max(1, len(ok)), 4),
        "mean_detail_fidelity": round(sum(r["detail_fidelity"] for r in ok) / max(1, len(ok)), 4),
        "mean_detail_iou": round(sum(r["detail_iou"] for r in ok) / max(1, len(ok)), 4),
        "mean_strokes": int(sum(sum(r["strokes"].values()) for r in ok) / max(1, len(ok))),
    }

    summary = {
        "tag": tag, "seed": seed, "rows": rows, "agg": agg,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / "bench.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[bench:{tag}] agg: ssim={agg['mean_ssim']:.3f} "
          f"ms_ssim={agg['mean_ms_ssim']:.3f} "
          f"detail_fidelity={agg['mean_detail_fidelity']:.3f} "
          f"iou={agg['mean_detail_iou']:.3f}")
    print(f"[bench:{tag}] saved to {out_dir}/bench.json")
    return summary


def _compare(args) -> None:
    a_path = REPO / "benches" / f"detail_{args.compare[0]}" / "bench.json"
    b_path = REPO / "benches" / f"detail_{args.compare[1]}" / "bench.json"
    if not (a_path.exists() and b_path.exists()):
        print(f"missing: {a_path.exists()=} {b_path.exists()=}", file=sys.stderr)
        sys.exit(2)
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())

    print(f"\n=== {args.compare[0]} → {args.compare[1]} ===")
    print(f"{'target':45} {'ssim_Δ':>8} {'ms_ssim_Δ':>10} {'detail_Δ':>9} {'iou_Δ':>8}")
    for ra, rb in zip(a["rows"], b["rows"]):
        if "ssim" not in ra or "ssim" not in rb:
            continue
        stem = Path(ra["target"]).name[:44]
        dssim = rb["ssim"] - ra["ssim"]
        dmss = rb["ms_ssim"] - ra["ms_ssim"]
        ddet = rb["detail_fidelity"] - ra["detail_fidelity"]
        diou = rb["detail_iou"] - ra["detail_iou"]
        print(f"{stem:45} {dssim:+8.4f} {dmss:+10.4f} {ddet:+9.4f} {diou:+8.4f}")
    print()
    ag_a, ag_b = a["agg"], b["agg"]
    print(f"{'AGG':45} {ag_b['mean_ssim']-ag_a['mean_ssim']:+8.4f} "
          f"{ag_b['mean_ms_ssim']-ag_a['mean_ms_ssim']:+10.4f} "
          f"{ag_b['mean_detail_fidelity']-ag_a['mean_detail_fidelity']:+9.4f} "
          f"{ag_b['mean_detail_iou']-ag_a['mean_detail_iou']:+8.4f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run",
                    help="tag for this bench run (used in benches/detail_<tag>/)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--compare", nargs=2, metavar=("TAG_A", "TAG_B"),
                    help="print a delta table between two previous runs")
    ap.add_argument("--small", action="store_true",
                    help="use the 5-target small bench instead of the 28-target large one")
    args = ap.parse_args()
    if args.small:
        global BENCH_TARGETS
        BENCH_TARGETS = BENCH_TARGETS_SMALL
    if args.compare:
        _compare(args)
        return 0
    _bench(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
