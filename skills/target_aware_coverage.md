---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_v5_20260420
confidence: 4
tags: ['coverage', 'workflow']
---
`dump_gaps` now returns two metrics: `coverage_raw` (fraction of canvas painted away from base) and `coverage` (fraction of pixels that SHOULD be painted and are). Use `coverage` for decision-making.

Why: snow and bright-sky targets have large legitimately-white regions. The old absolute metric flagged those as gaps (80% "coverage" when actually the painting was complete). The new metric masks out pixels where target brightness > 225, giving true coverage 99%+ for those images.
