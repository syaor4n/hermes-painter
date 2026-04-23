---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_session_20260420
confidence: 4
tags: ['workflow', 'coverage']
---
After every major paint pass, call `dump_gaps` then Read the mask. White pixels are uncovered canvas base. If coverage < 95%, paint a second pass with fill_gaps_with_grid() or more overlapping brush strokes.

Exception: if the TARGET is dominantly white/light (snow, bright sky alone), dump_gaps over-reports gaps — white strokes on white canvas look like uncovered to the simple pixel match. In those cases, 80% coverage is fine.
