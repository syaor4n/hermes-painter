---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_v5_20260420
confidence: 5
tags: ['workflow', 'auto', 'meta']
---
Call `analyze_target` once per session — it returns a comprehensive strategy dict: suggested grid_size, stroke direction, fog hint, complexity, palette, edge density, subject region. Use those values directly instead of guessing.

The strategy is based on: edge density → grid_size (high density = 32, low = 16); structure tensor analysis per quadrant → stroke direction (horizontal/vertical/random); classification + edge density → fog hint (only for genuinely atmospheric images).

If you disagree with a suggestion, override it — but analyze_target starts correct in 80% of cases and saves you guessing time.
