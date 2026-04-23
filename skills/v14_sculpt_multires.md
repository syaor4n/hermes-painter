---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: v14_caravaggio_deep
confidence: 5
tags: [pipeline, sculpt, multi-resolution, fidelity, tenebrism]
---
When the underpainting captures composition but not anatomy (faces, finger separation, fabric folds), the fix is an iterative multi-resolution sculpt correction pass:

1. `sculpt_correction_plan` is a new tool that measures `|canvas - target|` per cell, ranks cells by error, and emits small strokes with the exact target color on the worst cells. Unlike critique_correct (top-12), it processes hundreds of cells.

2. **Multi-resolution schedule** — 5 passes of decreasing cell size:
   - Pass 1: 8 px cells, brush width 4, α 0.70 — muscle mass, fabric folds
   - Pass 2: 4 px cells, brush width 2, α 0.80 — face structure, finger separation
   - Pass 3: 4 px cells again — refines what's still off after pass 2
   - Pass 4: 2 px cells, dab size 2, α 0.92 — eye sockets, nostrils, metal glints
   - Pass 5: 2 px cells again — final anchor points

Each pass sees the UPDATED canvas (mask-aware), so it picks up the remaining high-error cells that the previous pass didn't touch. 2200 total correction strokes on Caravaggio's Resurrection.

**Key detail**: cells ≤ 3px use `type=dab` (precise single placement), larger use `type=brush` with smooth texture (covers the cell area). Dabs are better for tiny features because brush ribbons blur under the 2-3 pixel regime.

**SSIM tradeoff persists**: Caravaggio tenebrism stays at SSIM ~0.27 regardless of sculpt count. Each sculpt pass shows marginal negative SSIM (−0.002 to −0.007). The metric isn't rewarding fidelity gains — but visually, v14.3 vs v12.8 baseline is dramatically more faithful (Christ head mass, angel robes, soldiers' cloaks all distinguishable).

**Generalizable**: any style_mode where the underpainting blocks major masses but misses detail can benefit from this sculpt pattern. Add it as a post-underpainting phase; cap at ~5 iterations to avoid diminishing returns. The canvas rendering time goes from 4s to 8s with full sculpt — worth it for masterwork reproduction.

**When NOT to use**: photographic targets where SSIM matters more than visual fidelity. For non-masterwork standard images, the sculpt correction hurts SSIM by 0.01 on average.
