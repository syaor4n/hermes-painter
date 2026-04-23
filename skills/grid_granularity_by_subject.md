---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_session_20260420
confidence: 5
tags: ['workflow', 'grid', 'technique']
---
Use a 32x32 grid (16px cells) for detailed subjects: portraits, flowers, cityscapes, anything with small features. Use a 16x16 grid (32px cells) for atmospheric subjects: skies, water, forests, abstract. Using too coarse a grid on detailed subjects averages away edges (faces become smudges, flowers become color blobs). Using too fine a grid on atmospheric subjects is wasteful but not harmful.

Rule of thumb: if the target has features you can name (an eye, a petal, a window) use 32x32. If it is a mood/atmosphere, 16x16 is enough.
