---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: masterworks2_20260421
confidence: 5
tags: [pipeline, style-modes, pointillism, tenebrism]
---
Two more style_modes added after the second masterworks test revealed gaps in v12:

**v12.7 `style_mode='pointillism'`** — fine-grid (64×64) sampling + 3 small dabs per cell with tight color jitter. Alpha 0.85–1.0 so dots retain chromatic identity. No edges/detail/contour passes — dots are the whole picture.

The breakthrough was **fine-grid sampling**. Coarse 24×24 cells average too many distinct Seurat hues into grey, producing muddy dabs. 64×64 cells keep local chromatic variation, so the dots have real color specificity.

Tested on Seurat's "A Sunday on La Grande Jatte": SSIM 0.032 (no mode) → 0.201 (pointillism). Visually transformed from noise to recognizable pointillist composition.

**v12.8 `style_mode='tenebrism'`** — canvas starts with `#14100a` deep warm-dark fill. Only cells with L > 0.28 get bristle strokes, and those are brightness-boosted ×1.12. Highlights use `warm_tint=0.35` (strong candle-warm), `threshold=200` (catch more). Contours use `color_source='contrast'` not dark — Caravaggio's outlines are umber, not ink.

Tested on Cecco del Caravaggio's Resurrection: SSIM 0.167 (night_scene recipe) → 0.282 (tenebrism). Figures become readable against properly dark ground.

**Grayscale detector bug fix (v12 addendum)** — mean chroma < 30 AND p50 < 30 was too permissive: fired on colorful muted paintings (Seurat mean 23, Caravaggio mean 25). Added p95 < 50 requirement: Cole engraving p95 = 47 (stays), Seurat p95 = 56 (excluded), Caravaggio p95 = 73 (excluded). Clean separation between true monochrome and muted-color.

**Broader lesson**: when a new style_mode fails to produce expected aesthetic, first check if auxiliary detectors (grayscale, saliency, segmentation) are firing incorrectly and suppressing the real pipeline. Both new modes were initially sabotaged by the overly-permissive grayscale detector.
