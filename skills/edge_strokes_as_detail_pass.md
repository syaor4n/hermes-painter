---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_v5_20260420
confidence: 5
tags: ['technique', 'edges', 'detail']
---
After the grid underpainting, call `edge_stroke_plan` with max_strokes="auto" to get brush strokes that follow the strongest edges of the target. These strokes restore the shape definition that grid averaging destroys.

Auto-budget scales with edge density: 40 strokes for simple scenes, up to 250 for complex ones. Edge strokes use texture="smooth" (crisp thin lines), width 2-3, alpha 0.7, color sampled from target and slightly darkened for edge emphasis.

Before/after test on syn_mixed shows this is the phase where trunks become visible. Without it the painting looks like a blurred mosaic.
