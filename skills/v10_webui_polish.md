---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v10_20260421
confidence: 4
tags: ['webui', 'ux', 'polish']
---
v10 webui additions, all purely client-side in `viewer.py`'s `INDEX_HTML`:

1. **Download button** — `downloadCanvas()` calls `canvas.toDataURL('image/png')` and triggers a filename `painting_{target}_{ISO-ts}.png`.

2. **Phase labels on history tiles** — each tile now shows the pipeline phase that produced it (`Phase 1 · underpainting`, `Phase 6 · contours`, etc.). Driven by `reasoning` in the stroke plan; paint_lib passes a phase label with every `draw_strokes` call.

3. **Phase overlay during replay** — `.phase-overlay` badge on the main canvas shows the current phase as the replay advances. Cleared on completion or returnToLive.

4. **Compare A vs B modal** — `toggleCompareMode()` switches tile clicks from replay to pair-selection. Click one tile → goes to slot A (green border). Click another → slot B (yellow border). Modal opens side-by-side. Escape closes.

5. **Style mode dropdown** (`balanced / tight / loose / segmented`) — picks a kwargs override passed to `auto_paint` via env var `PAINTER_STYLE_MODE`. `tight` = more contrast + details. `loose` = no highlights, less contrast. `segmented` = SLIC per-region palette.

6. **Letterbox aspect option** — checkbox on upload. `/api/target?fit=letterbox` preserves non-square photos by padding with white instead of center-cropping.

**Load-bearing detail**: the `drawStroke` port in `viewer.py` must keep parity with `canvas/index.html`. Any new stroke type added to the canvas must be mirrored in three places (canvas/index.html, local_renderer.py, viewer INDEX_HTML drawStroke) for live view, score_plan scoring, and replay to all agree. The parity test in `tests/test_renderer_parity.py` catches drift.
