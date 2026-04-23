---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v6_20260421
confidence: 5
tags: ['technique', 'details', 'finishing', 'polyline']
---
Finish a painting with TWO detail passes after gap-fill — not one. They do different jobs:

1. **Mid-detail** (`detail_stroke_plan` percentile≈94, alpha≈0.55, width 1, `color_source=contrast`). Re-establishes the shading lines the grid averaging and bristle strokes wiped out. Semi-transparent contrast color (darker side of each edge) so it reads as *shadow*, not *outline*. Typical budget 300–500.

2. **Fine-detail** (`detail_stroke_plan` percentile≈98.5, alpha≈0.95, width 1, `color_source=dark`). Only the very strongest edges. Pure dark ink for definitive contour marks — eyes, lips, beak, branch tips, window frames. Budget 80–150.

Run them in this order (mid first, then fine) so the darkest lines sit on top. Single-tier detail passes either look too weak (if alpha low) or too cartoonish (if color always dark). The two-tier split gives painterly depth: soft shading + a few crisp accents.

**Why not just one pass?** A single detail pass forces a trade-off: either many strokes (looks noisy) or few strokes (no visible effect). Splitting by percentile lets the mid layer add density without dominating, while the fine layer adds legibility with few pure-dark marks.

Tested on 22 targets (10 presets + 12 Unsplash photos). All kept 98–99% coverage; the fine pass added legible structure to portraits, birds, architecture, and still-life scenes.
