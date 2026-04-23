"""Auto-paint the current viewer target using the v6 pipeline (paint_lib).

Called by the viewer's /api/paint endpoint. Assumes:
  - Viewer is up on :8080 (with a target already set)
  - Hermes tool server is up on :8765 (shares the viewer canvas)

Flow: fetch the current target from the viewer, dump it to a file path,
then hand off to paint_lib.auto_paint which orchestrates the full 5-phase
pipeline via the tool server:
  1. underpainting (grid-sampled bristle brush, direction auto-detected)
  2. fog (optional, for atmospheric subjects)
  3. edge-following brush strokes (shape definition)
  4. gap-fill (coverage > 95%)
  5. two-tier detail pass (mid + fine thin polylines)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paint_lib import auto_paint  # noqa: E402

VIEWER = os.environ.get("PAINTER_VIEWER_URL", "http://127.0.0.1:8080")
TOOL_SERVER = os.environ.get("PAINTER_TOOL_URL", "http://127.0.0.1:8765")


def viewer_get(path: str) -> dict:
    with urllib.request.urlopen(VIEWER + path, timeout=30) as r:
        return json.loads(r.read())


def probe_tool_server() -> bool:
    try:
        with urllib.request.urlopen(TOOL_SERVER + "/tool/manifest", timeout=5) as r:
            json.loads(r.read())
        return True
    except Exception:
        return False


def main() -> int:
    if not probe_tool_server():
        print(
            f"ERROR: tool server not reachable at {TOOL_SERVER}. "
            "Start it first: python scripts/hermes_tools.py --port 8765",
            file=sys.stderr,
        )
        return 2

    try:
        state = viewer_get("/api/state")
    except urllib.error.URLError as e:
        print(f"ERROR: viewer not reachable at {VIEWER}: {e.reason}", file=sys.stderr)
        return 2

    if not state.get("has_target"):
        print("ERROR: no target set on the viewer — upload one first.", file=sys.stderr)
        return 1

    target_resp = viewer_get("/api/target")
    target_png = base64.b64decode(target_resp["target_png"])
    target_file = Path("/tmp/current_target.png")
    target_file.write_bytes(target_png)

    name = state.get("target_name", "uploaded")
    import os
    # Three env vars with deliberately distinct responsibilities:
    #   PAINTER_STYLE_MODE         — pipeline intensity preset (shim-level):
    #                                balanced / tight / loose / segmented.
    #                                Controls stroke density, contrast_boost,
    #                                segmentation toggle, etc.
    #   PAINTER_STYLE_PERSONALITY  — style personality (pipeline-level):
    #                                van_gogh / tenebrism / pointillism /
    #                                engraving / lumiere_doree / "".
    #                                Maps 1:1 to the auto_paint(style_mode=)
    #                                kwarg. Empty string means default
    #                                "classical" look.
    #   PAINTER_STYLE_SCHEDULE     — JSON-encoded morph schedule:
    #                                {"start": str, "end": str, "rationale": str}.
    #                                Maps 1:1 to auto_paint(style_schedule=)
    #                                kwarg. Empty string means no morph
    #                                (uniform style from STYLE_MODE /
    #                                STYLE_PERSONALITY instead). When both
    #                                STYLE_PERSONALITY and STYLE_SCHEDULE are
    #                                set, the viewer clears PERSONALITY before
    #                                subprocess spawn so schedule wins.
    # These are independent. They can be combined (intensity + personality, or
    # intensity + schedule) without conflict at the shim level.
    pipeline_intensity = os.environ.get("PAINTER_STYLE_MODE", "balanced")
    style_personality = os.environ.get("PAINTER_STYLE_PERSONALITY", "") or None
    style_schedule_raw = os.environ.get("PAINTER_STYLE_SCHEDULE", "")
    style_schedule = None
    if style_schedule_raw:
        try:
            style_schedule = json.loads(style_schedule_raw)
        except Exception as exc:
            print(f"[warn] PAINTER_STYLE_SCHEDULE JSON parse failed ({exc}); "
                  "falling back to uniform paint", file=sys.stderr)
            style_schedule = None
    if style_schedule is not None:
        schedule_label = f"{style_schedule['start']}→{style_schedule['end']}"
    elif style_personality:
        schedule_label = style_personality
    else:
        schedule_label = "classical"
    print(f"Painting: {name} ({len(target_png)} bytes) · "
          f"intensity={pipeline_intensity} · style={schedule_label}")

    # Pipeline intensity → shim-level kwargs override
    style_kwargs = {
        "balanced": {},
        "tight": {"contrast_boost": 0.35, "use_segmentation": False},
        "loose": {"contrast_boost": 0.18, "use_segmentation": False,
                  "use_highlights": False},
        "segmented": {"contrast_boost": 0.25, "use_segmentation": True,
                      "n_segments": 10},
    }.get(pipeline_intensity, {})

    # Style personality / schedule → pipeline-level kwargs. Schedule wins
    # if both are somehow set here (viewer already enforces precedence).
    if style_schedule is not None:
        style_kwargs["style_schedule"] = style_schedule
    elif style_personality:
        style_kwargs["style_mode"] = style_personality

    result = auto_paint(str(target_file), seed=42, verbose=True, **style_kwargs)

    print()
    print(f"DONE. Strategy: {result['strategy']['reasoning']}")
    print(
        f"  underpaint={result['underpaint_strokes']}  "
        f"edges={result['edge_strokes']}  "
        f"fill={result['fill_strokes']}  "
        f"mid_detail={result['mid_detail_strokes']}  "
        f"fine_detail={result['fine_detail_strokes']}  "
        f"coverage={result['coverage']:.1%}"
    )
    # Pull final score from viewer for the caller's log
    final = viewer_get("/api/state")
    if final.get("score"):
        s = final["score"]
        print(f"  SSIM={s['ssim']:.4f}  MSE={s['mse']:.6f}  Composite={s['composite']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
