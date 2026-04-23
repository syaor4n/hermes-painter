"""Batch-learn from real reference images (NO synthetic rasterizations).

Paints every image in targets/, targets/unsplash/, targets/masterworks/ with
a chosen style_mode (or auto-detection), writes a reflection + journal entry
per run, then runs skill_promote across the accumulated reflections.

Each promoted skill is scoped to the target's detected image_type so that
subsequent runs on similar targets benefit from the accumulated effects.

Usage:
  python scripts/learn_from_targets.py              # all presets + unsplash + masterworks
  python scripts/learn_from_targets.py --dirs targets/masterworks
  python scripts/learn_from_targets.py --limit 5    # quick smoke test

Requires viewer + tools running (make demo or manually start both).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from paint_lib import auto_paint

STYLE_CYCLE = [None, "van_gogh", "tenebrism", "pointillism"]


def _viewer_alive(port: int = 8080) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/api/state", timeout=2)
        return True
    except Exception:
        return False


def _tools_alive(port: int = 8765) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/tool/manifest", timeout=2)
        return True
    except Exception:
        return False


def _post(tool: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://localhost:8765/tool/{tool}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def _collect_targets(dirs: list[str]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        p = REPO / d if not Path(d).is_absolute() else Path(d)
        if not p.exists():
            continue
        if p.is_file():
            out.append(p)
            continue
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            out.extend(sorted(p.glob(ext)))
    # De-dup in order
    seen, dedup = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            dedup.append(p)
    return dedup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+",
                    default=["targets", "targets/unsplash", "targets/masterworks"],
                    help="directories to scan for .jpg/.jpeg/.png")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap number of targets (0 = all)")
    ap.add_argument("--style-cycle", action="store_true",
                    help="cycle through style_modes instead of auto-detection")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-promote", action="store_true",
                    help="skip skill_promote at the end")
    ap.add_argument("--min-repeat", type=int, default=2,
                    help="min occurrence count for skill_promote")
    ap.add_argument("--two-pass", action="store_true",
                    help="after promote, repaint up to 5 targets to show applied feedback")
    args = ap.parse_args()

    if not _viewer_alive() or not _tools_alive():
        print("error: viewer (8080) or tools (8765) not running.", file=sys.stderr)
        return 2

    targets = _collect_targets(args.dirs)
    if args.limit > 0:
        targets = targets[: args.limit]
    if not targets:
        print("no targets found.", file=sys.stderr)
        return 2

    print(f"[learn] {len(targets)} targets from {args.dirs}")
    runs: list[dict] = []
    t_start = time.time()

    for i, tgt in enumerate(targets):
        style = STYLE_CYCLE[i % len(STYLE_CYCLE)] if args.style_cycle else None
        rel = tgt.relative_to(REPO) if tgt.is_absolute() else tgt
        print(f"\n[{i+1}/{len(targets)}] {rel} style={style or 'auto'}")
        t0 = time.time()
        try:
            result = auto_paint(str(tgt), seed=args.seed + i, verbose=False,
                                style_mode=style, auto_reflect=True)
            ssim = (result.get("final_score") or {}).get("ssim")
            n_applied = len(result.get("applied_skills") or [])
            eff = result.get("effective_params") or {}
            cb = eff.get("contrast_boost")
            cs = eff.get("complementary_shadow")
            ssim_s = f"{ssim:.3f}" if ssim is not None else "  ?  "
            print(f"  image_type={result.get('image_type'):13} "
                  f"ssim={ssim_s}  applied={n_applied}  "
                  f"contrast={cb}  comp_shadow={cs}  "
                  f"elapsed={time.time()-t0:.1f}s")
            runs.append({
                "target": str(rel),
                "image_type": result.get("image_type"),
                "style_mode": style,
                "ssim": ssim,
                "applied_skills": n_applied,
                "effective_params": eff,
            })
        except Exception as e:
            print(f"  ! failed: {type(e).__name__}: {e}")
            runs.append({"target": str(rel), "error": str(e)})

    print(f"\n[learn] painted {len(runs)} targets in {time.time()-t_start:.1f}s")

    if not args.no_promote:
        print("\n[promote] scanning reflections for recurring patterns...")
        r = _post("skill_promote", {"n": len(runs) + 10, "min_repeat": args.min_repeat,
                                      "max_promote": 8})
        print(f"  scanned={r['scanned']}  promoted={len(r['promoted'])}  bumped={len(r['bumped'])}")
        for p in r.get("promoted", []):
            print(f"    + {p['name']}  scope={p.get('scope', [])}  effects={p.get('effects', {})}")
        for b in r.get("bumped", []):
            print(f"    ↑ {b['name']}  new_conf={b.get('new_confidence')}  (+{b.get('based_on')} reflections)")

    pass2_runs: list[dict] = []
    if args.two_pass and not args.no_promote:
        print("\n[pass 2] re-painting first 5 targets to show accumulated feedback...")
        for tgt in targets[:5]:
            rel = tgt.relative_to(REPO) if tgt.is_absolute() else tgt
            try:
                result = auto_paint(str(tgt), seed=args.seed, verbose=False,
                                    auto_reflect=False)
                eff = result.get("effective_params") or {}
                n_applied = len(result.get("applied_skills") or [])
                ssim = (result.get("final_score") or {}).get("ssim")
                ssim_s = f"{ssim:.3f}" if ssim is not None else "  ?  "
                print(f"  {str(rel):40} ssim={ssim_s}  applied={n_applied}  "
                      f"contrast={eff.get('contrast_boost')}  "
                      f"comp_shadow={eff.get('complementary_shadow')}")
                pass2_runs.append({
                    "target": str(rel),
                    "image_type": result.get("image_type"),
                    "ssim": ssim,
                    "applied_skills": n_applied,
                    "effective_params": eff,
                })
            except Exception as e:
                print(f"  ! {rel}: {e}")

    summary = {
        "runs": runs,
        "pass2_runs": pass2_runs,
        "duration_s": round(time.time() - t_start, 1),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    out_path = REPO / "runs" / f"learn_from_targets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n[learn] summary: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
