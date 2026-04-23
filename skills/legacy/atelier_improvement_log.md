## Atelier Self-Improvement Log

### Version 1 (initial)
- 5-step pipeline: underpaint → midtone → shadows → highlights → focal detail
- Basic palette extraction, no edge enhancement
- SSIM-only evaluation (evaluated target, not painting)
- Average score: ~5.4/10

### Version 2 (hierarchy + saturation)
- Added focal-distance-based stroke sizing (near=fine, far=bold)
- Background: 60px strokes, midground: 30px, focal: 10px
- Saturation boost: 1.25x
- Reduced palette to 6 colors
- Added warm accent layer
- Average score: ~6.2/10 (evaluated target image)

### Version 3 (edge enhancement + canvas evaluation) — CURRENT
- Added Sobel edge enhancement step (1600+ edge dabs)
- Fixed: evaluation now uses PAINTED CANVAS, not target image
- Fixed: apply_plan working directory was wrong (was ../.., now ..)
- Saturation boost: 1.35x
- Average score: ~6.9/10

### Scores by image (v3, canvas-evaluated)
| Image      | Comp | Color | Form | Texture | Overall |
|------------|------|-------|------|---------|---------|
| forest     | 6.5  | 7.0   | 6.5  | 7.5     | 6.9     |
| portrait   | 7.5  | 7.0   | 6.5  | 7.5     | 7.1     |
| ocean      | 6.5  | 7.0   | 6.5  | 7.5     | 6.9     |
| city       | 7.0  | 7.0   | 6.5  | 7.5     | 7.0     |
| flower     | 7.0  | 7.0   | 6.5  | 7.5     | 7.0     |
| sunset     | 7.5  | 6.0   | 5.0  | 7.5     | 6.5     |
| snow       | 7.5  | 7.0   | 6.5  | 7.5     | 7.1     |
| night      | 7.5  | 6.0   | 6.5  | 7.0     | 6.8     |
| abstract   | 7.0  | 7.0   | 6.5  | 7.5     | 7.0     |
| landscape  | 7.0  | 7.0   | 6.5  | 7.5     | 7.0     |

### Consistent critiques
1. "Palette is mostly cool — add warm accents" (warm accents exist but too subtle)
2. "Colors could be more saturated" (at 1.35x, need 1.5x+)
3. Form varies by image type (sunset/night harder)

### Roadmap to 8+/10
- [ ] Warmer, more visible warm accents (alpha 0.15→0.25)
- [ ] Higher saturation boost (1.35x → 1.5x)
- [ ] Image-type-specific adjustments (boost warm for sunsets, contrast for night)
- [ ] Palette warm/cool balance (force at least 2 warm colors)
