---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v7_20260421
confidence: 5
tags: ['technique', 'details', 'faces', 'animals', 'finishing', 'bezier']
---
For faces, animals, and any subject where object boundaries matter, the final pass must be **connected-component contour tracing**, not random high-gradient walks.

Use `contour_stroke_plan` (Canny + skeletonize + connected-component labeling + Douglas-Peucker simplification, emitted as bezier curves). Good defaults for most subjects:
```
sigma=1.8, min_length=12, width=1, alpha=0.85,
color_source='contrast', stroke_type='bezier', simplify_tolerance=1.2
```
This phase comes AFTER the two-tier detail pass so contours sit on top.

**Why not rely on detail_stroke_plan alone?** `detail_stroke_plan` walks random edge pixels, so each stroke is 4–5 scattered points — looks like scribbled tic-marks. `contour_stroke_plan` extracts the actual connected edge curve first, then emits one stroke per curve following the real shape. Result on faces: glasses frames, lip outline, nose bridge and brows become legible as connected curves. Result on animals: beaks, eye outlines, ear/snout contours appear as one continuous line.

**Budget behavior:** `auto_budget = max(30, min(400, n_components // 2))`. A bird photo yields 300+ components (150 strokes); a blurred portrait yields 60–80 components (30–42 strokes). The floor keeps portraits legible; the ceiling keeps busy scenes (street, food) from getting cluttered.

**focus_box option** — if a face/subject region is known (e.g. from a future detect_faces tool), pass `focus_box=[x,y,w,h]` and `focus_boost=2.0` to weight contours inside that box higher when sorting by length. This ensures eye/mouth contours beat background clutter for a limited budget.

Tested on 22 targets. Contour counts ranged from 30 (blurred-background portraits) to 392 (dense still-life of vegetables). Coverage unaffected (98–99%). The improvement is most visible on: `old_man` (glasses + nose + mouth legible), `portrait` (lip outline), `cat` (eye outlines + whisker hints), `bird` (beak contour), `city` (window frames), `street` (individual fruit shapes).
