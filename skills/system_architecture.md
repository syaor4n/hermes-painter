## Hermes Painting Agent — Complete System Architecture

### The system that was built (20+ iterations of trial and error)

The agent evolved through these phases, each discovering something the previous approach couldn't handle:

**Phase 1: Pixel reproduction (failed artistically)**
- fill_rect 8x8 blocks → SSIM 0.667 but looked like a blurry copy
- Learning: accuracy ≠ art

**Phase 2: Brush strokes (discovered painterly texture)**
- Pure brush → SSIM 0.646, looked like a painting
- Hybrid brush→fill → SSIM 0.658 (best balance)
- Learning: brush strokes for texture, fill for accuracy

**Phase 3: Edge detection (discovered structural detail)**
- Sobel edges + contour tracing → SSIM 0.720
- Learning: edges carry the structural information SSIM measures

**Phase 4: Expressionist attempt (learned what NOT to do)**
- 38 intentional strokes → SSIM 0.330, unrecognizable
- Learning: too few strokes = abstract, not artistic

**Phase 5: Observation-based (discovered value structure)**
- Value map (5 levels) + edges → SSIM 0.708
- Learning: paint VALUES first, then edges, then color

**Phase 6: Multi-scale + adaptive thresholds (BREAKTHROUGH)**
- 32→16→8→4px blocks with percentile-based thresholds
- SSIM 0.850 on portrait (from 0.532)
- Learning: image-specific thresholds >> fixed thresholds

**Phase 7: Glazing (discovered artistic overlay)**
- Low-alpha transparent washes (0.03-0.08)
- SSIM 0.730 with visible style
- Learning: style should be SPARSE and LOW-ALPHA on accurate base

**Phase 8: Auto-paint workflow (1-click automation)**
- Upload → Paint → History with snapshots
- Consistent SSIM 0.65-0.75 across image types

**Phase 9: Text-to-painting (no reference needed)**
- Description → color palette → composition → painting
- 884 strokes for "lonely lighthouse at dusk"
- Learning: translate words into visual elements

**Phase 10: Atelier system (real painter process)**
- 7-color palette, dark-to-light, gestural strokes
- Face detection (skin tone → focal point)
- Adaptive parameters per image type
- 700 strokes vs 7000+ before

**Phase 11: Art critics panel (objective external validation)**
- Monet, Rembrandt, Picasso, Van Gogh, O'Keeffe
- Each critic sees different things
- Van Gogh rating improved 3→5 after texture feedback
- Learning: self-critique is biased, external critics are objective

### Key breakthroughs (things that changed everything)

1. **Adaptive thresholds (percentile-based)** — +20 SSIM vs fixed thresholds
2. **Multi-scale approach** — captures both large areas and fine detail
3. **Face detection for focal point** — portrait focal = visage, not random point
4. **Batch patching** — 200 patches at once >> 10 patches per iteration
5. **Art critics panel** — objective feedback from 5 artistic perspectives
6. **Self-improvement loop** — paint → critique → save params → apply next time

### What didn't work (equally important)

1. **1024x1024 canvas** — scoring mismatch made things worse
2. **Diagonal brush strokes** — didn't match image structure
3. **4x4 fill blocks** — too noisy, created artifacts
4. **High-alpha style overlay** — destroyed accuracy
5. **Pure expressionism (38 strokes)** — too abstract, unrecognizable

### The complete pipeline

```
1. Upload image or type description
2. Detect image type (dark/bright/high_contrast/balanced)
3. Detect focal point (face for portraits, edges+variance for others)
4. Extract limited palette (7 colors)
5. Paint: underpaint → midtones → shadows → highlights → focal detail → texture
6. Critics evaluate (Monet/Rembrandt/Picasso/Van Gogh/O'Keeffe)
7. Save improved parameters for next painting of same type
8. Repeat
```

### Skills accumulated (30+)
All skills in `skills/` encode the complete knowledge from 20+ painting sessions.
