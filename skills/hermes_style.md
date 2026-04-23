## Hermes Painting Style — v1.0

### Philosophy
Not reproducing the image — reinterpreting it. Visible brush strokes, warm tones,
soft edges, atmospheric depth. The painting should look like a painting.

### Style characteristics
- **Warm underpainting**: First layer shifts all colors +15 red, -5 green, -8 blue
- **Cool highlights**: Areas > 180 brightness get +10 blue shift
- **Visible brush strokes**: Horizontal, width 10-22px, alpha 0.4-0.55
- **Alternating angles**: Every 30 rows, stroke angle varies (horizontal / slight up / slight down)
- **Signature dabs**: 150-200 scattered dabs for painterly texture
- **Loose detail**: Not precise — soft, impressionistic

### 4-Layer painting process

**Layer 1: Warm underpainting** (12px rows, 48px segments, width 22, alpha 0.55)
- Covers the canvas with warm-shifted base colors
- My signature: everything starts warmer than the reference
- Threshold: 99 (paint everything)

**Layer 2: Color blocking** (10px rows, 40px segments, width 16, alpha 0.5)
- Corrects the warm base with target colors
- Alternating stroke angles for texture
- Threshold: 15

**Layer 3: Loose detail** (8px rows, 32px segments, width 10, alpha 0.4)
- Fine brush strokes for detail areas
- Cool shift on bright areas
- Threshold: 12

**Layer 4: Signature dabs** (150-200 random dabs)
- Scattered painterly texture
- Each dab is 12x7 ellipse at random angle
- Threshold: 6-8

### Results with style vs standard

```
Image          Style SSIM  Standard SSIM  Style strokes  Standard strokes
Sunset         0.722       0.689           2,294          4,678
Forest         0.473       0.440           2,358          8,700
Landscape      0.634       0.663           1,986         16,056
```

Style is competitive or better on 2/3 images, with far fewer strokes.
The warm shift helps on warm images (sunset, forest), hurts slightly on cool images (landscape).

### Next evolution ideas
- Auto-detect image warmth and adjust shift amount
- Add vertical brush strokes for trees, buildings
- Vary brush width by region (thick for sky, thin for detail)
- Add impasto texture (thick paint) on focal points
