# My painting style

## What I optimize for
- Recognizable composition with visible brushwork. Every stroke should show
  the "bristle" texture of a real brush, not a flat ribbon.
- Many short overlapping strokes (200-500 per canvas) rather than few long ones.
- Shape through stroke clustering, not through fill_rect/fill_circle. A sun is
  not a circle — it's 30-60 overlapping brush strokes with color variation.
- Broken color: adjacent areas share some hues. Real paintings are not
  uniform zones but a mosaic of related colors.

## What I avoid
- Optimizing SSIM. It's a compass for fidelity, not a proxy for painterly quality.
- Painting without looking. Every session starts with `dump_target` + Read,
  and every batch ends with `dump_canvas` + Read.
- Flat geometric shapes (perfect trapezoids, perfect circles, perfect bands).
- The "smooth" brush texture, except for thin geometric strokes (branches,
  edge outlines, structure lines) where clean lines are desired.

## My evolution
- 2026-04-21: 2026-04-21 (v10): Finishing and underpainting now live in the same tonal universe. No more #101010 — tonal dark samples the local color, shifts saturation up and luminance down, so a red lip gets a carmine outline not a cartoon outline. Alphas dropped across all finishing passes; superposition carries the weight. 40% of contour components dropped (lost & found edges) and radial alpha falloff around the saliency center keeps the focal point sharp while peripheries soften. Infrastructure caught up: paint-lock, gzipped stroke log, safe_phase wrappers, pipeline pytest, auto-regression alert, parity test, LAB palette. webui gained Compare A/B, style mode dropdown, Download PNG, phase labels + overlay, letterbox aspect. 35 tools.
- 2026-04-21: 2026-04-21 (v9): Infrastructure maturation. Parity tests lock renderer drift. critique_correct + best_of_N refine final outputs at acceptable cost. Segmentation gives a posterized alternative mode (off by default). Batch sample_grid makes the pipeline 3× faster. Replay controls polish the viewer. Pipeline is now 8 phases, 33 tools, 2-3s per canvas.
- 2026-04-21: 2026-04-21 (v8): Four coordinated additions turn the painter from descriptive to interpretive. (a) Laplacian saliency mask gates which pixels get detail/contour effort — backgrounds stay soft. (b) Per-cell structure-tensor angles drive local stroke direction — fur, hair, fabric all align correctly. (c) Tanh contrast S-curve in underpainting pushes darks+lights apart — no more muddy greys. (d) Bright warm dabs at local maxima — eyes, lips, metal, water now read alive. Pipeline is 7 phases: under → fog → edges → fill → mid+fine detail → contours → highlights. The order is load-bearing: highlights MUST be last.
- 2026-04-21: 2026-04-21 (v7): Added a Phase 6 CONTOUR pass using Canny edge detection + skeletonize + connected-component tracing. Emits bezier curves that actually follow real object boundaries (glasses frames, eye outlines, beaks, lip shapes). This is the difference between a painting that reads as impressionist-abstract and one where faces/animals are recognizable. Random-walk detail passes produce scribbles; ordered-path contour tracing produces drawing. For faces + animals, this is now the critical pass. Default budget scales with n_components/2, floor 30, ceiling 400.
- 2026-04-21: 2026-04-21 (v6): Added a two-tier DETAIL finishing pass after gap-fill. Mid-detail (percentile 94, alpha 0.55, contrast color) lays soft shading. Fine-detail (percentile 98.5, alpha 0.95, pure dark) adds crisp contour accents. Polylines, not brush strokes — these are ink-like marks that read as drawing over paint. A finished canvas is now 2200-2300 strokes across 5 layers: underpainting (1728) + fog (optional) + edge brushwork + gap-fill + two detail tiers. Learned to train on real Unsplash photos instead of synthetic gradients — synthetic targets gave false 99% coverage confidence that hid weak detail rendering.
- 2026-04-20: v4 run: always call find_features first (60px error avoided on sun). Glow stroke with 6-stop radial gradient produces buttery sun instead of bullseye rings. Dock now aligned with sun vertical axis (x=258).
- 2026-04-20 (a): Learned not to optimize SSIM directly (produces flat bands).
- 2026-04-20 (b): Learned to always `dump_canvas` + Read (can't judge painterly
  quality from scores alone).
- 2026-04-20 (c): Learned that the default brush was a highlighter ribbon,
  not a real brush. The canvas and local renderer now produce bristle textures
  with color variation. My strokes should be many, short, and overlapping.
  A "painting" is 400-800 strokes, not 80.
