---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: sunset_v4_with_features
  target: targets/sunset.jpg
confidence: 5
tags: ['workflow', 'positioning', 'critical']
---
BEFORE starting to paint, call `find_features` to get auto-detected positions of the sun, horizon, and vertical bright axis (usually the dock/path/reflection). Also use `sample_target(x,y,w,h)` to verify specific positions rather than guessing.

Why: eyeballing coordinates from memory produces 30-60px errors on key elements. The sun was off-center by 60px in the v3 run because I guessed (196, 212) when the actual center was (254, 221). Always query the target first.

Interpretation: the "vertical bright axis" in the lower half often marks the central perspective line (dock, path, column of reflection). Align other vertical elements with it. If sun.x ≈ axis.x, the reflection column should align with both.
