---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v10_20260421
confidence: 4
tags: ['infrastructure', 'tests', 'robustness']
---
v10 added a safety layer around the painter's moving parts:

1. **`safe_phase(name, fn, fallback)`** — wraps a pipeline phase with implicit `snapshot()` / `restore()` on exception. If a phase crashes, the canvas rolls back and the pipeline continues. Applied to saliency + segmentation (both optional) so a single failure doesn't abort the whole paint.

2. **`_cleanup_tmp()` at tool-server startup** — removes stale `/tmp/painter_*.png` files. Keeps debug PNGs from accumulating across restart.

3. **Paint-lock (`STATE["busy"]`)** in viewer — `/api/paint` returns HTTP 409 if a paint is already in flight instead of stacking up.

4. **`/api/iteration/{N}/strokes`** stores gzipped JSON (compresslevel=6). Typical 2300-stroke iteration: 500 KB raw → 80 KB gzipped. For 40 iterations: ~3 MB instead of ~20 MB.

5. **`tests/test_pipeline_orchestration.py`** — pytest-runnable smoke test:
   - auto_paint fires all phases (under ≥500, edges ≥10, mid/fine > 0, contour > 10, coverage ≥0.95)
   - saliency fires on portraits (mask_used == True)
   - no `#101010`-class pure-black strokes in finishing passes (guards v10 contract)

6. **Auto-regression alert (`_regression_alert`)** — compares current SSIM to the last journal entry for the same target; logs a visible warning if SSIM dropped > 0.02 compared to the last recorded run. Non-fatal but surfaces silent regressions.

7. **`tool_decay_skills(days=30, dry_run=false)`** — drops 1 confidence point on skills whose file mtime is older than N days. Never goes below 0. Opt-in via explicit tool call, not automatic.

**Why this matters**: before v10, one broken phase could leave the canvas in a half-rendered state that the user had to Clear manually. And silent regressions were only noticed when visually comparing batches. Both are now caught.
