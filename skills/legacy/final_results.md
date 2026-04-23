## Complete Final Results — All Styles Tested

### Style comparison across 4 images

```
Image          Multi-scale  Glazed     Lumière    Elegant    Standard
               (pure)       (overlay)  Dorée      (sparse)
Portrait       0.850        0.730      0.707      0.677      0.532
Landscape      0.796        0.676      —          —          0.663
Forest         0.648        0.513      —          —          0.440
City           0.627        —          —          —          0.427
```

### The trade-off: accuracy vs style

Every style overlay REDUCES SSIM:
- Multi-scale base: SSIM 0.850 (no style)
- + Warm glaze (0.06 alpha): SSIM drops ~0.05
- + Cool glaze (0.05 alpha): SSIM drops ~0.03
- + Impasto highlights (0.45 alpha): SSIM drops ~0.04
- + Signature marks (0.12 alpha): SSIM drops ~0.02

Total style cost: ~0.12 SSIM for visible artistic character.

### Best approach per image type

**Simple images** (shapes, snow): Multi-scale alone (SSIM 0.85-0.95)
**Medium images** (landscape, sunset): Multi-scale + light glazes (SSIM 0.70-0.75)
**Complex images** (forest, city): Multi-scale alone (SSIM 0.60-0.65, glazes hurt)

### Style techniques that work

| Technique | Alpha | Impact | Best for |
|-----------|-------|--------|----------|
| Warm shadow glaze | 0.05-0.08 | Subtle warmth | Portraits, landscapes |
| Cool highlight glaze | 0.04-0.06 | Subtle cool | Skies, highlights |
| Golden midtone glaze | 0.05 | Warm glow | Skin tones |
| Impasto highlights | 0.4-0.5 | Visible thick paint | Bright spots |
| Deep shadow accents | 0.5 | Warm dark marks | Darkest areas |
| Signature marks | 0.08-0.12 | Brush texture | Everywhere |

### Style techniques that DON'T work

| Technique | Why it fails |
|-----------|-------------|
| High-alpha overlay (>0.3 everywhere) | Destroys accuracy |
| Warm shift on all colors | Too aggressive |
| Dense brush texture (>500 marks) | Adds noise |
| Style on dense-texture images (forest) | Every overlay hurts |

### The golden rule
Style should be SPARSE and LOW-ALPHA on top of an ACCURATE base.
Like seasoning on food — too much ruins the dish.
