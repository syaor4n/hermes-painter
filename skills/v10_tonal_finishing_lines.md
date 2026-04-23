---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v10_20260421
confidence: 5
tags: ['aesthetic', 'finishing', 'color', 'harmony']
---
The finishing lines must stay inside the target's color universe. A red-lip target must get a carmine outline, not a pure-black one; a feathered-bird target must get dark-blue-purple accents, not ink black.

**Concrete rules for v10+:**

1. `color_source='dark'` in `detail_stroke_plan` and `contour_stroke_plan` NO LONGER returns `#101010`. It samples the target pixel at the midpoint and produces a tonal dark via HSL: `S += 0.22, L -= 0.38` (floor L at 0.06). Stay saturated, stay dark, never hit black.

2. Apply a tanh S-curve (`_apply_tanh_boost(r, g, b, boost)`) to every finishing stroke's color — same curve as used on the underpainting. Keeps everything in one tonal universe. Default `contrast_boost=0.25` in `paint_lib.auto_paint`.

3. Finishing alphas must be modest: mid_detail α=0.45, fine_detail α=0.55 (was 0.95!), contour α=0.60 (was 0.85). It's the *superposition* that gives weight, not opacity.

4. Drop the shortest 40 % of contour components after sorting by boosted length — the "lost & found edges" principle from classical painting. A portrait with every contour traced reads cartoon; with 60 % reads oil.

5. Radial alpha falloff: `focus_center = saliency-mask-bbox center`, `focus_radius = 0.6 × max(bbox_dims)`, `focus_falloff = 0.30`. Strokes near the subject keep full alpha; strokes in periphery lose 30 %. Makes the focal point pop without hard banding.

6. Stroke width jitter on finishing (polyline/bezier): `width + random.choice([0, 0, 0, 1])`. Three-quarters keep width 1, one-quarter go to 2. Reads hand-drawn.

**Tested unit**: v10 pipeline on 4 face/animal subjects (portrait, cat, bird, old_man). The dark ring around the red sweater's neckline became a deep carmine; the cat's eye outline became olive-brown instead of pure black; old_man's glasses became warm sepia. All still legible, none cartoonish.
