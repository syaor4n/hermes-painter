---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: v13_loop_20260421
confidence: 5
tags: [pipeline, tenebrism, caravaggio, fine-grid, faithful]
---
For faithful reproduction of Caravaggio-class tenebrist paintings, the v12.8 tenebrism mode was too coarse. The breakthrough in v13 came from FOUR combined changes:

1. **Fine-grid sampling at 64×64 cells (8 px each)** for lit-region placements. The default 24×24 grid (21 px cells) averages skin + robe + armor colors into a single cell mean, producing anatomy-less blobs. At 64×64, figures gain color variation that reveals body structure.

2. **3 passes of thinner bristles per lit cell** instead of 2 thick bristles. Alphas 0.75/0.55/0.38. Dense layering builds form like Caravaggio's glazed oil layers — light from beneath, darks on top that don't obliterate.

3. **Transition-zone capture (L 0.18–0.28)**. Previously cells below L 0.28 were pure dark. Adding a sparse dim-bristle pass in the transition band (50 % chance per cell, α 0.30) captures the critical edge where figures emerge from shadow — the Caravaggio signature.

4. **Scoped edge + fine_detail + thick contour phases** after the underpainting:
   - `edge_stroke_plan` percentile 88, width 2, α 0.75, color_source='target'
   - `detail_stroke_plan` percentile 92, mask_threshold 0.15 (permissive into penumbra)
   - `contour_stroke_plan` sigma 1.2, width 3, mask_boost 3.5, skip 10 % (keep short segments for faces)

Result on Cecco del Caravaggio's Resurrection: figures (Christ, angel, soldiers) clearly distinguishable with their correct colors (red cloak, blue flag, tan figures). Going from blob masses to readable composition.

**SSIM tradeoff**: the improvements produced SIMILAR SSIM (~0.28) but dramatically better RECOGNIZABILITY. Tenebrism underpainting alone contributes the full +0.29 SSIM; all finishing phases are slightly negative (each -0.001 to -0.005). This is consistent with v9+ observations — SSIM is a compass, not a goal. Visual fidelity improved while SSIM plateaued.

**Generalizable lesson**: when a style_mode's visual output is right-structured but low-detail, the fix is almost always **finer sampling** of the source color grid, NOT more strokes or higher contrast. Fine grid → accurate local color → strokes that respect shape.
