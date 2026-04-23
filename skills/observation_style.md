## Multi-Scale Observation Style — v5.0 FINAL

### The breakthrough: adaptive thresholds + multi-scale

Fixed thresholds (0-50-100-150-200) miss the image's actual structure.
Adaptive thresholds (15th/35th/65th/85th percentiles) match each image's natural value breaks.

Single scale (8px only) is either too coarse for large areas or too fine for efficiency.
Multi-scale (32→16→8→4px) captures both large zones and fine detail.

### 6-step process (auto_paint)

1. **32px blocks** (threshold 99, alpha 0.6, cap 300) → major color zones
2. **16px blocks** (threshold 12, alpha 0.55, cap 1000) → medium refinement
3. **8px blocks** (threshold 6-8, alpha 0.5, cap 3000) → detail
4. **4px fine fill** (threshold 6-8, alpha 0.5-0.7, cap 3000) → fine detail
5. **Edge contours** (Sobel, threshold 15) → structural boundaries
6. **Light glazes** (alpha 0.025-0.04) → artistic warmth

### Why caps matter

Without caps, the 2x2 or 4px phases create 50,000+ strokes that add noise.
Caps keep the painting clean while still covering the worst errors.

### Results

```
Image          SSIM    Strategy
Portrait       0.850   Multi-scale (pure)
Landscape      0.796   Multi-scale (pure)
Sunset         0.749   Multi-scale + glazes
Portrait       0.730   Multi-scale + glazed style
Landscape      0.673   Auto-paint (multi-scale + edges + glazes)
Portrait       0.661   Auto-paint
Forest         0.648   Multi-scale (pure)
City           0.627   Multi-scale (pure)
```

### What determines image difficulty

The SSIM ceiling is proportional to how well 8x8 block averages can represent the image:
- Shapes with flat colors: ~0.95
- Smooth gradients: ~0.70
- Mixed content: ~0.65-0.75
- Dense textures: ~0.45-0.65

### Adapted strategy by difficulty

Easy (variance < 30): Standard multi-scale, threshold 8
Medium (variance 30-60): Multi-scale with glazes, threshold 6
Hard (variance > 60): Multi-scale with 4px fine, threshold 5, more edges
