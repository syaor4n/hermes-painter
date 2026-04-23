---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: webui_paint_style_wiring_20260421
confidence: 5
tags: ['webui', 'animation', 'infrastructure']
---
To let the viewer animate "each brush stroke coming to life" on a clicked iteration, four pieces must all be in place:

1. **Server state** — `STATE["stroke_log"]` in `viewer.py` (bounded `OrderedDict`, same cap as `snapshots`) stores the raw stroke list for each iteration, populated in `async_apply_plan`.
2. **Endpoint** — `GET /api/iteration/{N}/strokes` returns `{strokes, prev_canvas_png, iteration}`. The `prev_canvas_png` is `snapshots[N-1]`; without it we cannot reconstruct the state just before iteration N.
3. **Browser renderer parity** — The frontend in `INDEX_HTML` must include a `drawStroke(ctx, spec)` function that mirrors `canvas/index.html`'s exactly. If the two diverge, replays render differently than the live canvas. Keep them in sync when adding new stroke types.
4. **Animation engine** — `playIteration(N)` uses a cancellation token (`replayToken`) so the user can click a different tile mid-replay. Stroke batching is `Math.max(1, ceil(n / targetFrames))` with `targetFrames ≈ min(240, n_strokes)`, giving roughly 2–4 seconds per iteration regardless of stroke count.

History tiles are thumbnails from `/api/iteration/{N}` (PNG snapshots), laid out as a horizontal strip below the main canvas, NOT in the sidebar. A rebuild is gated on an `__sig` cache (serialized iteration numbers) so the 500ms poll only re-renders when the iteration set actually changes.

**Why:** The user asked to "see each brush stroke come to life" on click. Just showing the static snapshot is insufficient — the animation is the value. Keeping the drawStroke port in the frontend (instead of server-side) means replays are smooth (no HTTP round-trip per stroke).
**How to apply:** When adding a new stroke type to `canvas/index.html`, mirror it into the inline `drawStroke` in `viewer.py`'s `INDEX_HTML`. Otherwise replays will skip or mis-render those strokes.
