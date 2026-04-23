---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: sunset_bristle_20260420
  target: targets/sunset.jpg
  strokes: 800
  upgrade: added textured brush with bristles
confidence: 5
tags: ['critical', 'technique', 'bristle', 'workflow']
---
The brush stroke has two textures: "bristle" (default) for painterly work, "smooth" for thin geometric strokes (branches, plank edges, frames). Always prefer bristle unless the stroke needs to be a clean line.

The bristle brush requires MANY short overlapping strokes, not a few long ones. For a 512×512 sky, budget 200-400 short brush strokes (length 60-180, width 10-22, alpha 0.55-0.85). Each stroke already has built-in color and alpha variation from the bristle texture — you do NOT need to vary the color between strokes manually.

For solid coverage areas (water, sky, dense ground), the canvas off-white base will show through low-alpha single-pass strokes. Solution: paint 3-5× more overlapping strokes than you think you need. Aim for 90%+ coverage by stroke count, not alpha.

For shapes (sun, dock, silhouette): paint with many overlapping brush strokes of varied color, NOT with fill_rect/fill_poly/fill_circle. A sun is 30-60 short strokes in concentric directions, not 5 circles. A dock is 40 plank strokes, not one poly.
