---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v9_20260421
confidence: 5
tags: ['pipeline', 'infrastructure', 'testing', 'performance']
---
The v9 pipeline adds six capabilities on top of v8. Each is small and opt-in, together they make the painter more robust and more expressive:

1. **Renderer parity test** (`tests/test_renderer_parity.py`) — renders 12 stroke fixtures (one per type) in both `canvas/index.html` via Playwright and `src/painter/local_renderer.py`, asserts pixel MAE < per-type tolerance. Run before modifying either renderer. v9 baseline: all 12 pass with MAE 0.01–3.95 (bristle tolerance 10, most others < 4).

2. **`critique_correct(n_rounds=N)`** — reads `get_regions` top-12, samples target color at each, emits two small bristle strokes per cell. Use after the full pipeline when you want to close obvious error gaps (N=2 adds ~50 strokes). Off by default because the base pipeline already reaches 98-99% coverage.

3. **`auto_paint_best_of(n_seeds=3)`** — serial multi-seed wrapper. Runs the pipeline with different seeds, scores each via `painter.critic.score`, restores the winner. Cost 3× time, gain ~0.5-1% composite. Worth it for final renders, skip for experimentation.

4. **`segment_regions` + `layered_underpainting_segmented`** — SLIC super-pixels (8–10 regions default) with per-region palette extraction. Underpainting uses each cell's region palette instead of sampled mean. Gives a more posterized / intentional look; opt-in via `use_segmentation=True`. Keep OFF by default for realism; ON for illustration/poster aesthetic.

5. **`sample_grid` batch tool** — single HTTP call returns the full gx×gy color grid using numpy reshape. Replaces 576 per-cell calls. Brought paint time from 5-9 s to 2-3 s per canvas. Paint_lib's `sample_grid` wrapper tries batch first, falls back to per-cell for old servers.

6. **Webui replay controls** — speed slider (0.25–4×), pause, step buttons. Appear only during replay, use a `waitFrame()` helper instead of raw `requestAnimationFrame` so pause actually stops progression.

**Why the batch tool beats OffscreenCanvas:** the real bottleneck was the per-cell HTTP round trips for color sampling, not the bristle rendering itself. Measuring before optimizing saved us from a 200-line Worker refactor. Lesson: always profile before parallelizing.
