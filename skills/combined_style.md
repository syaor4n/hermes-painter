## Combined Style — Multi-Scale + Lumière Dorée

### The formula: ACCURACY + STYLE

1. **Multi-scale base** (32→16→8px blocks, adaptive thresholds) → SSIM 0.850 base
2. **Subtle golden tone** (0.12 intensity) on every color → warmth without destroying accuracy
3. **Edge contours** (Sobel, true colors) → structural detail
4. **Golden accents** (impasto highlights, brush texture) → artistic personality
5. **Fine fill** (4px, alpha 0.5) → corrects remaining errors

### Results

```
Image          Combined     Multi-scale  Lumière Dorée  Standard
Portrait       0.786        0.850        0.707          0.532
```

The combined approach sits between pure accuracy and pure style.
The golden overlay (0.12 intensity) is subtle enough to preserve accuracy
while adding visible warmth and personality.

### Style characteristics visible in the painting
- Warm golden undertone in every color (subtle, not overpowering)
- Visible brush texture marks (200 scattered at alpha 0.15)
- Warm impasto highlights on bright areas
- Smooth color transitions (multi-scale base)
- Defined edges (Sobel contours)

### What to push further
- Stronger golden tone on shadows (currently uniform 0.12)
- More dramatic light-shadow contrast
- Visible underpainting in shadow areas
- Brush stroke direction following image contours
