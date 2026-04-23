## Hermes Detail Style — v2.0 FINAL

### The breakthrough: edge contours
Adding Sobel edge detection + contour tracing transforms blurry copies into actual paintings.
Edges carry the structural information that SSIM measures.

### Results with detail style vs previous approaches

```
Image          Detail v2.0  Style v1.0  Standard   Improvement
Portrait       0.635        0.532       0.532      +19% vs standard
Sunset         0.720        0.722       0.689      +5% vs standard  
Landscape      (pending)    0.634       0.663      
Forest         (pending)    0.473       0.440      
```

### 4-Layer process (refined)

**Layer 1: Base** — 20-24px brush, 44-52px segments, alpha 0.6-0.65
**Layer 2: Contrast** — 10-12px brush, 32px segments
  - Low variance (std < 25): average color, alpha 0.45
  - High variance (std >= 25): edge color, alpha 0.6
**Layer 3: Edge contours** — 3-4px brush, alpha 0.85
  - Sobel threshold: 18-20
  - Connected tracing: 5 points per stroke
  - TRUE edge colors (not darkened)
**Layer 4: Fine fill** — 8x8 fill_rect, adaptive alpha 0.35-0.85

### Key insight
The contour strokes (Layer 3) are the secret. They add the structural detail
that was missing from all previous approaches. Even just 200-400 thin edge
strokes dramatically improve SSIM on images with clear edges (portrait, city).

### Edge detection that works
- Sobel gradient magnitude (not Canny — simpler, faster)
- Threshold 18-20 for strong edges
- Connected component tracing (follow strongest neighbor)
- Max 5-6 points per contour stroke
- Paint with TRUE edge color (don't darken — the contrast comes from adjacent regions)
