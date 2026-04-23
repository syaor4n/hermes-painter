---
scope:
  image_types: ['balanced', 'dark', 'high_contrast']
  exclude: []
provenance:
  created: 2026-04-20
  run: sunset_painterly_20260420
  target: targets/sunset.jpg
  strokes: 73
  final_ssim: 0.6279
confidence: 2
tags: ['painterly', 'brushwork', 'anti_ssim_trap']
---
SSIM optimization produces flat colored bands with no brushwork. To paint like a painter: use BRUSH strokes (not fill_rect) with varied width (8-54), angle jitter, alpha 0.35-0.9. Build 5-7 layers: (1) coarse sky bands using wide brush, (2) sun glow via concentric dabs, (3) horizon warm strokes, (4) landscape underpainting, (5) sky texture = 20+ small brush marks with sampled colors, (6) landscape texture with occasional warm accents, (7) highlight dabs. Expect SSIM to DROP ~0.05-0.10 vs coarse-block optimization — accept this. Target 50-80 strokes minimum. The painting must look hand-made, not optimized.
