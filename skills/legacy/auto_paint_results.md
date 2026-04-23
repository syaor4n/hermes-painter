## Auto-Paint Results — Complete

### Consistent SSIM across image types

```
Image          SSIM    Strokes   Category
Sunset         0.749   13,393    Easy (gradients)
Landscape      0.673    7,240    Medium
Portrait       0.661    7,000    Medium-Hard
Forest         0.511    8,481    Hard (dense texture)
```

### The auto_paint workflow

1. Multi-scale base (32→16→8px, adaptive thresholds, capped)
2. 4px fine fill (capped at 3000)
3. Edge contours (Sobel)
4. Light glazes (alpha 0.025-0.03)
5. Impasto highlights (40 spots, alpha 0.45)
6. Signature marks (40-80, alpha 0.05)

### What works
- Adaptive thresholds (percentile-based) — key for different image types
- Multi-scale (32→16→8px) — captures both large areas and detail
- 4px fine fill — corrects remaining color errors
- Edge contours — structural detail
- Light glazes — subtle artistic warmth without destroying accuracy

### What doesn't work
- 2x2 fill — too many strokes, creates noise
- High-alpha glazes (>0.1) — destroys accuracy
- Dense texture overlay (>500 marks) — adds noise
- Style on dense-texture images (forest) — hurts SSIM

### Skills (18 total)
All accumulated across 11+ images and multiple painting strategies.
The auto_paint workflow encodes the best balance of quality and automation.
