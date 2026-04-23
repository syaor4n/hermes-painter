"""Painter benchmark runner.

Paints a frozen set of canonical targets with a frozen seed, compares
results to `benches/<version>_baseline.json`, and writes a fresh result
to `benches/current.json` + a diff report to `benches/last_diff.md`.

Usage:
  python scripts/run_bench.py                    # compare to v10_baseline
  python scripts/run_bench.py --freeze v11       # write new baseline as v11
  python scripts/run_bench.py --targets cat,bird # run subset

Exit code:
  0 = all within tolerance
  1 = at least one target regressed beyond tolerance
  2 = infra error (services down, missing targets)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "benches"
sys.path.insert(0, str(ROOT / "scripts"))

CANONICAL_TARGETS = [
    ("cat", "targets/unsplash/cat.jpg"),
    ("old_man", "targets/unsplash/old_man.jpg"),
    ("bird", "targets/unsplash/bird.jpg"),
    ("portrait", "targets/unsplash/portrait.jpg"),
    ("mountain", "targets/unsplash/mountain.jpg"),
]

DEFAULT_TOLERANCE_SSIM = 0.02   # regression threshold
DEFAULT_SEED = 42


def run_one(name, path):
    from paint_lib import auto_paint
    t0 = time.time()
    result = auto_paint(path, seed=DEFAULT_SEED, verbose=False)
    return {
        "name": name,
        "target": path,
        "seed": DEFAULT_SEED,
        "final_ssim": result["final_score"]["ssim"] if result.get("final_score") else None,
        "final_composite": result["final_score"]["composite"] if result.get("final_score") else None,
        "phase_deltas": result.get("phase_deltas", {}),
        "mask_used": result.get("mask_used"),
        "coverage": result.get("coverage"),
        "total_strokes": sum([result.get(k, 0) for k in (
            "underpaint_strokes", "edge_strokes", "fill_strokes",
            "mid_detail_strokes", "fine_detail_strokes",
            "contour_strokes", "highlight_strokes", "critique_strokes")]),
        "elapsed_s": round(time.time() - t0, 2),
    }


def compare_to_baseline(current: list, baseline: list, tolerance: float):
    """Return (n_regressions, rows) for diff report."""
    by_name = {r["name"]: r for r in baseline}
    rows, n_regress = [], 0
    for cur in current:
        base = by_name.get(cur["name"])
        if base is None:
            rows.append({"name": cur["name"], "status": "NEW",
                          "ssim_current": cur["final_ssim"]})
            continue
        delta = (cur["final_ssim"] or 0) - (base["final_ssim"] or 0)
        status = "OK"
        if delta < -tolerance:
            status = "REGRESS"
            n_regress += 1
        elif delta > tolerance:
            status = "GAIN"
        rows.append({
            "name": cur["name"],
            "status": status,
            "ssim_baseline": base["final_ssim"],
            "ssim_current": cur["final_ssim"],
            "delta": round(delta, 4),
        })
    return n_regress, rows


def write_diff_md(rows, out_path: Path, baseline_version: str):
    lines = [f"# Bench diff vs {baseline_version}\n",
             f"Ran at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"]
    lines.append("| target | status | baseline ssim | current ssim | Δ |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        base = f"{r.get('ssim_baseline', '—'):.4f}" if isinstance(r.get("ssim_baseline"), (int, float)) else "—"
        cur = f"{r.get('ssim_current', '—'):.4f}" if isinstance(r.get("ssim_current"), (int, float)) else "—"
        delta = f"{r.get('delta', 0):+.4f}" if "delta" in r else "—"
        lines.append(f"| {r['name']} | **{r['status']}** | {base} | {cur} | {delta} |")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="v10", help="baseline version tag")
    ap.add_argument("--freeze", help="write a new baseline under this version tag")
    ap.add_argument("--targets", help="comma-separated subset of target names")
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_SSIM)
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    wanted_names = set((args.targets or "").split(",")) if args.targets else None
    targets = [t for t in CANONICAL_TARGETS
               if wanted_names is None or t[0] in wanted_names]
    if not targets:
        print("ERROR: no targets matched", file=sys.stderr)
        return 2

    # Probe services
    import urllib.request
    for url in ("http://localhost:8765/tool/manifest",
                "http://localhost:8080/api/state"):
        try:
            urllib.request.urlopen(url, timeout=3).read()
        except Exception:
            print(f"ERROR: {url} not reachable", file=sys.stderr)
            return 2

    print(f"Bench: {len(targets)} targets, seed={DEFAULT_SEED}, baseline={args.baseline}")
    current = []
    for name, path in targets:
        print(f"  painting {name} ...")
        row = run_one(name, path)
        current.append(row)
        print(f"    ssim={row['final_ssim']:.4f} coverage={row['coverage']:.1%} ({row['elapsed_s']}s)")

    current_path = BENCH_DIR / "current.json"
    current_path.write_text(json.dumps({
        "version": "current",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": DEFAULT_SEED,
        "results": current,
    }, indent=2), encoding="utf-8")

    if args.freeze:
        frozen = BENCH_DIR / f"{args.freeze}_baseline.json"
        shutil.copy(current_path, frozen)
        print(f"\nFrozen baseline: {frozen}")
        return 0

    baseline_path = BENCH_DIR / f"{args.baseline}_baseline.json"
    if not baseline_path.exists():
        print(f"No baseline at {baseline_path}. Use --freeze {args.baseline} first.")
        return 0
    baseline = json.loads(baseline_path.read_text())["results"]
    n_regress, rows = compare_to_baseline(current, baseline, args.tolerance)
    diff_path = BENCH_DIR / "last_diff.md"
    write_diff_md(rows, diff_path, args.baseline)
    print(f"\nDiff written: {diff_path}")
    for r in rows:
        if r["status"] != "OK":
            print(f"  [{r['status']}] {r['name']}: Δ={r.get('delta', '—')}")
    return 1 if n_regress > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
