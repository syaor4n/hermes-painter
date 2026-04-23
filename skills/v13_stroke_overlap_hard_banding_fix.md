---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: v13_loop_20260421
confidence: 5
tags: [pipeline, banding, underpainting, stroke-length]
---
HARD_BANDING on 17/32 targets in iter1 of the v13 loop. Root cause: the
`layered_underpainting` used `length = base * random.uniform(0.9, 1.4)`.
At the lower bound 0.9, strokes are shorter than the cell — they don't
extend into neighboring cells, so FFT picks up the grid frequency.

**Fix**: bump the range to `random.uniform(1.2, 1.7)`. Strokes now ALWAYS
overlap into at least the adjacent cell, breaking the grid signature.

Both `layered_underpainting` (default + direction_grid variants) and
`layered_underpainting_segmented` were fixed.

**Effect on batch**: mean SSIM 0.297 → 0.336 across 31 targets (+0.039).
HARD_BANDING detector still fires on some targets (the mid/fine_detail
passes also have grid-aligned structure), but severity is lower and visual
quality dramatically better.

**Generalizable lesson**: whenever you use a grid-based underpainting with
strokes confined to each cell, the stroke length must exceed `cell_size ×
1.15` for overlap. Shorter strokes = visible grid = banding. Applies to
brush, bristle, and hachure modes alike.
