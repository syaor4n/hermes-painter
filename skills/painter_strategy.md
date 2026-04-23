## Universal painting strategy — consolidated from 11-image test suite

### The winning strategy: hybrid brush→fill

**Phase 1: Brush base (3-5 iterations)**
- Type: `brush` strokes, horizontal
- Width: 22px, Segments: 52px, Alpha: 0.65, Threshold: 15
- Creates smooth painterly color base across the canvas
- SSIM reaches 0.55-0.62 depending on image complexity

**Phase 2: Fill accuracy (10-60 iterations)**
- Type: `fill_rect`, 8x8 blocks
- Threshold: starts at 12, decreases by 1 every 5 iterations (min 2-3)
- Alpha boost: starts 0.4, increases 0.005/iter (max 0.5), cap 0.92
- Stop after 8 iterations with no improvement > 0.0003
- SSIM climbs incrementally as blocks are corrected

### Why this works
Brush strokes create smooth edges but imprecise colors. fill_rect creates precise colors but pixelated edges. Layering fill_rect over brush base gives both — smooth texture visible underneath, correct colors on top.

### What does NOT work (tested, failed)
- Fine brush (8px width) → creates noise, SSIM drops
- Diagonal brush strokes → doesn't match image structure
- 4x4 fill blocks → too noisy, SSIM drops vs 8x8
- Pure fill (no brush base) → pixelated result
- Pure brush (no fill) → inaccurate colors, SSIM plateaus early
- Aggressive fill from start (no brush) → chaotic mosaic

### Image difficulty prediction
Compute mean color variance in 8x8 blocks BEFORE painting:
- Variance < 30 → Easy (SSIM 0.65-0.95): shapes, snow, sunset
- Variance 30-60 → Medium (SSIM 0.55-0.65): landscape, ocean
- Variance 60-100 → Hard (SSIM 0.40-0.55): portrait, night, forest, city
- Variance > 100 → Very hard (SSIM < 0.40): flower, abstract

### Verified results across 11 images

| Image | SSIM | Category |
|-------|------|----------|
| Test shapes | 0.947 | Trivial |
| Snow | 0.766 | Easy |
| Sunset | 0.689 | Easy |
| Yosemite landscape | 0.663 | Medium |
| Ocean | 0.608 | Medium |
| Portrait | 0.532 | Hard |
| Forest | 0.440 | Hard |
| Night sky | 0.428 | Hard |
| City | 0.427 | Hard |
| Flower | 0.356 | Very hard |
| Abstract | 0.321 | Very hard |

### Strokes used (from canvas/index.html)
- `brush`: {type:"brush", points:[[x,y],...], color:"#hex", width:20, alpha:0.85}
  Ribbon shape following path with rounded caps. Width = stroke thickness.
- `fill_rect`: {type:"fill_rect", x, y, w, h, color:"#hex", alpha:0.9}
  Solid rectangle. Best for accuracy passes.
- `dab`: {type:"dab", x, y, w, h, angle, color:"#hex", alpha:0.9}
  Ellipse at angle. Tested but not better than fill_rect for accuracy.

### Workflow
```bash
# 1. Start viewer
python scripts/viewer.py --port 8080

# 2. Init
python scripts/paint_live.py --init targets/image.jpg

# 3. Paint (automated loop):
#    - Analyze error map from current canvas
#    - Generate brush or fill strokes targeting high-error regions
#    - POST plan to viewer via paint_live.py
#    - Repeat until plateau

# 4. Reflect
python scripts/reflect.py runs/<run_dir>
```
