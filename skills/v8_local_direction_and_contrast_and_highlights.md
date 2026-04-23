---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v8_20260421
confidence: 5
tags: ['technique', 'direction', 'contrast', 'highlights']
---
Three small changes in the underpainting + final phase give the biggest visible leap on faces and animals since bristle brush was introduced:

1. **Per-cell direction field** (`direction_field_grid` tool, 16×16 grid of structure-tensor angles). Underpainting strokes follow local orientation — cat fur points out from the face, old man's beard follows its growth, fabric folds show direction. Coherence floor 0.08: cells below threshold use random angles (avoids aligning in textureless zones).

2. **Contrast S-curve** (`contrast_boost=0.25` in `layered_underpainting`). A tanh curve applied to each cell's sampled color pushes darks darker and lights lighter. Removes the muddy mid-grey look. `tanh(k*(v-0.5))` with `k = 1 + 3*boost` — 0.25 is a good default, 0.4 for moody subjects, 0.0 to disable.

3. **Highlight dabs** (`highlight_stroke_plan`, final phase). `maximum_filter` to find local brightness maxima, filter by local contrast ≥ 30 vs 15-px neighborhood, emit small warm-white dabs (size 3–6 px, α 0.85). Brings life to eyes, lips, metal, foam. Budget scales 10–60 with candidate count, capped low so highlights stay sparse.

**Order matters:** underpainting → fog → edges → gap-fill → mid-detail → fine-detail → contours → highlights. Highlights MUST be last or subsequent phases paint over them.

**Computational cost:** ~0.3s total for all three additions on a 512² canvas; pipeline stays at 5–9 s/image.
