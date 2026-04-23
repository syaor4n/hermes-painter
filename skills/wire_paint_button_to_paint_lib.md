---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: webui_paint_style_wiring_20260421
confidence: 5
tags: ['webui', 'integration', 'infrastructure']
---
The webui's "Paint This Image" button fires `POST /api/paint`, which `scripts/viewer.py` implements as `subprocess.run([python, "scripts/auto_paint.py"])`. If `auto_paint.py` has its own stroke logic, the button will paint in whatever style that script defines — not in the style of the current `paint_lib.py` pipeline.

**Keep `scripts/auto_paint.py` as a thin shim** that imports `paint_lib.auto_paint` and hands off to it, so the button always paints in the current style. Whenever the v{N} pipeline is upgraded (in `paint_lib.py`), the webui follows automatically.

Flow:
1. `auto_paint.py` probes the tool server on :8765 and fails fast if not running.
2. Fetches the viewer's current target PNG via `/api/target` and writes it to `/tmp/current_target.png`.
3. Calls `paint_lib.auto_paint(path)` which drives the full 5-phase pipeline via the tool server (which cascades to the viewer's canvas via `/api/plan`).

**Why:** Previous `auto_paint.py` had 5 hand-coded phases (multi-scale + edges + glazes + impasto + signature) that diverged from `paint_lib.py`. Running the button painted in an outdated style. User noticed and asked for fix.
**How to apply:** Never inline stroke logic in `auto_paint.py`. If you add a new pipeline phase (new detail pass, new color strategy, etc.), put it in `paint_lib.py`. The shim is ~50 lines and just bridges viewer state → paint_lib → viewer canvas.
