## Complete Workflow — Viewer + Auto-Paint v2

### Viewer features

**Upload**: Choose any image (jpg, png, etc.). Center-crop to square, resize to 512x512.
**Gallery**: 12 clickable test images (Landscape, Sunset, Forest, City, Portrait, Ocean, Night, Snow, Flower, Mountain, Abstract, Desert).
**Paint button**: One click launches auto_paint.py on the uploaded target.
**Snapshots**: Every iteration's canvas is saved. Click any row in history to view it.
**Navigation**: Arrow keys (left/right) navigate between snapshots. Escape closes.

### Auto-paint strategy (best results)

1. **Multi-scale base** (32→16→8px, adaptive thresholds, capped)
2. **4px fine fill** (capped at 3000)
3. **Edge contours** (Sobel, threshold 15)
4. **Light glazes** (alpha 0.025-0.04, warm shadows + cool highlights)
5. **Impasto highlights** (40 spots, alpha 0.45)
6. **Signature marks** (40-80, alpha 0.05-0.12)

### Image resize

Center-crop to square first, then resize to 512x512. This prevents distortion
on non-square images. The subject center is preserved, edges are cropped.

### Results (auto-paint)

```
Image          SSIM    Strokes   Time
Sunset         0.749   13,393    ~3 min
Landscape      0.673    7,240    ~2 min
Portrait       0.661    7,000    ~2 min
Forest         0.511    8,481    ~3 min
```

### Endpoints

- GET / — Web UI
- GET /api/state — Current state + history
- GET /api/iteration/{N} — Snapshot at iteration N
- GET /api/snapshots — List available snapshots
- POST /api/target — Upload image (multipart)
- POST /api/paint — Start auto-painting
- POST /api/clear — Reset canvas
- POST /api/plan — Apply a stroke plan
