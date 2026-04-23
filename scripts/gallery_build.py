"""Paint a curated set of masterworks with various style modes and dump
the resulting canvases into gallery/. One run per (target, style) pair.

Usage:
    python scripts/gallery_build.py            # paints all rows below
    python scripts/gallery_build.py --limit 2  # quick sample

Assumes viewer on :8080 and hermes_tools on :8765 are running.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from paint_lib import auto_paint  # noqa: E402

TOOL_URL = "http://127.0.0.1:8765"

# (target, style_mode, output_slug)
GALLERY = [
    ("targets/masterworks/great_wave.jpg",            None,           "great_wave_default"),
    ("targets/masterworks/the_bedroom.jpg",           "van_gogh",     "the_bedroom_van_gogh"),
    ("targets/masterworks/caravaggio_resurrection.jpg", "tenebrism",  "caravaggio_tenebrism"),
    ("targets/masterworks/seurat_grande_jatte.jpg",   "pointillism",  "seurat_pointillism"),
]

# (target, style_schedule, output_slug) for morph demos
MORPH_GALLERY = [
    ("targets/masterworks/caravaggio_resurrection.jpg",
     {"start": "van_gogh", "end": "tenebrism",
      "rationale": "warm dramatic portrait — expressive open, dramatic close"},
     "caravaggio_van_gogh_to_tenebrism"),
    ("targets/masterworks/mona_lisa.jpg",
     {"start": "van_gogh", "end": "tenebrism",
      "rationale": "classical portrait reinterpreted through expressive→dramatic arc"},
     "mona_lisa_van_gogh_to_tenebrism"),
    ("targets/masterworks/great_wave.jpg",
     {"start": "van_gogh", "end": "pointillism",
      "rationale": "texture → dot translation on a famously textured subject"},
     "great_wave_van_gogh_to_pointillism"),
]

# (target, [persona_A, persona_B], output_slug) for duet demos
DUET_GALLERY = [
    ("targets/masterworks/mona_lisa.jpg",
     ["van_gogh_voice", "tenebrist_voice"],
     "mona_lisa_vangogh_vs_tenebrist"),
    ("targets/masterworks/great_wave.jpg",
     ["van_gogh_voice", "pointillist_voice"],
     "great_wave_vangogh_vs_pointillist"),
    ("targets/masterworks/caravaggio_resurrection.jpg",
     ["tenebrist_voice", "van_gogh_voice"],
     "caravaggio_tenebrist_vs_vangogh"),
]


def post(tool: str, payload: dict | None = None, timeout: int = 30) -> dict | None:
    req = urllib.request.Request(
        f"{TOOL_URL}/tool/{tool}",
        data=json.dumps(payload or {}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def paint_one(target: str, style_mode: str | None, slug: str,
              out_dir: Path) -> dict:
    print(f"\n=== {slug} (style={style_mode or 'default'}) ===")
    # Load target
    post("load_target", {"path": target})
    # Paint
    t0 = time.time()
    kwargs = {"seed": 42, "verbose": False}
    if style_mode:
        kwargs["style_mode"] = style_mode
    result = auto_paint(target, **kwargs)
    dt = time.time() - t0
    fs = result.get("final_score") or {}
    ssim = fs.get("ssim") or 0.0
    coverage = result.get("coverage") or 0.0
    print(f"  painted in {dt:.1f}s · "
          f"ssim={ssim:.3f} · "
          f"coverage={coverage:.1%} · "
          f"strokes={result.get('underpaint_strokes', 0)} (underpaint)")
    # Dump canvas
    post("dump_canvas")
    src = Path("/tmp/painter_canvas.png")
    dst_canvas = out_dir / f"{slug}.png"
    dst_target = out_dir / f"{slug}_target.jpg"
    shutil.copyfile(src, dst_canvas)
    shutil.copyfile(ROOT / target, dst_target)
    print(f"  → {dst_canvas.relative_to(ROOT)}")
    return {
        "slug": slug,
        "target": target,
        "style_mode": style_mode,
        "ssim": fs.get("ssim"),
        "coverage": result.get("coverage"),
        "duration_s": round(dt, 1),
        "underpaint_strokes": result.get("underpaint_strokes"),
        "total_strokes": (
            result.get("underpaint_strokes", 0)
            + result.get("edge_strokes", 0)
            + result.get("mid_detail_strokes", 0)
            + result.get("fine_detail_strokes", 0)
            + result.get("contour_strokes", 0)
            + result.get("highlight_strokes", 0)
        ),
    }


def paint_one_morph(target: str, schedule: dict, slug: str,
                    out_dir: Path) -> dict:
    print(f"\n=== {slug} (schedule={schedule['start']}→{schedule['end']}) ===")
    post("load_target", {"path": target})
    t0 = time.time()
    result = auto_paint(target, seed=42, verbose=False, style_schedule=schedule)
    dt = time.time() - t0
    fs = result.get("final_score") or {}
    ssim = fs.get("ssim") or 0.0
    coverage = result.get("coverage") or 0.0
    print(f"  painted in {dt:.1f}s · "
          f"ssim={ssim:.3f} · coverage={coverage:.1%}")
    post("dump_canvas")
    src = Path("/tmp/painter_canvas.png")
    dst_canvas = out_dir / f"{slug}.png"
    dst_target = out_dir / f"{slug}_target.jpg"
    shutil.copyfile(src, dst_canvas)
    shutil.copyfile(ROOT / target, dst_target)

    # Also paint a uniform-end control for side-by-side comparison
    post("clear")
    post("load_target", {"path": target})
    control_result = auto_paint(target, seed=42, verbose=False,
                                 style_mode=schedule["end"])
    post("dump_canvas")
    dst_control = out_dir / f"{slug}_uniform.png"
    shutil.copyfile(src, dst_control)

    return {
        "slug": slug,
        "target": target,
        "schedule": schedule,
        "ssim": ssim,
        "coverage": coverage,
        "duration_s": round(dt, 1),
        "underpaint_strokes": result.get("underpaint_strokes"),
        "control_ssim": (control_result.get("final_score") or {}).get("ssim"),
    }


def paint_one_duet(target: str, personas: list, slug: str,
                   out_dir: Path) -> dict:
    """Paint one duet (multi-turn critique-and-correct) + a solo-opening control."""
    print(f"\n=== {slug} (duet={personas[0]} × {personas[1]}) ===")
    from paint_lib.duet import paint_duet
    # Full duet
    result = paint_duet(target, personas=personas, max_turns=6,
                        seed=42, out_dir=out_dir / slug, verbose=True)
    print(f"  {result['reason']} · final_ssim={result['final_ssim']:.3f} · "
          f"{len(result['turns'])} turns")

    # Solo-opening control: persona[0] opens alone, no corrections
    control_dir = out_dir / slug / "_control"
    control_dir.mkdir(parents=True, exist_ok=True)
    control = paint_duet(target, personas=[personas[0], personas[0]],
                         max_turns=1, seed=42, out_dir=control_dir,
                         verbose=False)
    src = Path(control["canvas_path"])
    dst = out_dir / slug / "control.png"
    if src.exists():
        shutil.copyfile(src, dst)

    # Copy target for README
    shutil.copyfile(ROOT / target, out_dir / slug / "target.jpg")

    return {
        "slug": slug,
        "target": target,
        "personas": personas,
        "final_ssim": result["final_ssim"],
        "reason": result["reason"],
        "early_stopped": result["early_stopped"],
        "n_turns": len(result["turns"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=len(GALLERY),
                    help="paint only the first N rows")
    ap.add_argument("--out", default="gallery",
                    help="output directory (default: gallery/)")
    ap.add_argument("--mode", choices=("single", "morph", "duet"), default="single",
                    help="single: existing behavior. morph: paint the 3 "
                         "morph pairings to gallery/morph/ with uniform-end "
                         "control PNGs. duet: paint the 3 duet pairings to "
                         "gallery/duet/ with solo-opening control PNGs.")
    args = ap.parse_args()

    if args.mode == "morph":
        out_dir = ROOT / "gallery" / "morph"
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = []
        for target, schedule, slug in MORPH_GALLERY[: args.limit]:
            try:
                summary.append(paint_one_morph(target, schedule, slug, out_dir))
            except Exception as exc:
                print(f"  FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"\nWrote {summary_path.relative_to(ROOT)} "
              f"({len(summary)} successful rows)")
        # Write rationales.md for the hackathon artifact
        rats = ["# Morph rationales\n",
                "Plain-text record of each demo run's `plan_style_schedule` rationale.\n"]
        for row in summary:
            rats.append(f"\n## {row['slug']}")
            rats.append(f"- Target: `{row['target']}`")
            rats.append(f"- Schedule: `{row['schedule']['start']} → {row['schedule']['end']}`")
            rats.append(f"- Rationale: {row['schedule'].get('rationale', '')}")
            cs = row.get('control_ssim')
            if cs is not None:
                rats.append(f"- Morph SSIM: {row['ssim']:.3f} · Uniform control SSIM: {cs:.3f}")
        (out_dir / "rationales.md").write_text("\n".join(rats) + "\n")
        return

    if args.mode == "duet":
        out_dir = ROOT / "gallery" / "duet"
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = []
        for target, personas, slug in DUET_GALLERY[: args.limit]:
            try:
                summary.append(paint_one_duet(target, personas, slug, out_dir))
            except Exception as exc:
                print(f"  FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"\nWrote {summary_path.relative_to(ROOT)} "
              f"({len(summary)} successful rows)")
        return

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for target, style, slug in GALLERY[: args.limit]:
        try:
            summary.append(paint_one(target, style, slug, out_dir))
        except Exception as exc:
            print(f"  FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)

    # Persist the summary so the README can cite real numbers.
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nWrote {summary_path.relative_to(ROOT)} "
          f"({len(summary)} successful rows)")


if __name__ == "__main__":
    main()
