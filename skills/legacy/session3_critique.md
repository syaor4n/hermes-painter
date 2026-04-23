## Session 3 — Atelier v3 with Face Detection + Adaptive Parameters

### Improvements from session 2

| Feature | Before | After |
|---------|--------|-------|
| Portrait focal point | (160,48) wrong | (226,169) = FACE |
| Image type detection | None | dark/bright/high_contrast/balanced |
| Shadow threshold | Fixed 40th % | Adaptive 20th-60th % |
| Highlight threshold | Fixed 80th % | Adaptive 60th-80th % |
| Underpaint alpha | Fixed 0.65 | Adaptive 0.55-0.7 |
| Critique loading | None | Loads previous critiques |

### Results (4 paintings)

```
#  Subject              Strokes  Focal       Type          Notes
1  Portrait (image)       791    (226,169)   high_contrast Face detected!
2  Sunset (image)         729    (282,143)   balanced      Sun area
3  Forest (image)         738    (417,205)   balanced      
4  Sunset+boat (text)     757    (255,299)   balanced      Horizon
```

### Face detection works
The skin tone detection (R>G>B, R>100, G>60, B>40) correctly identifies
the face in portraits as the focal point. This means focal detail is
concentrated on the face, with the rest of the painting staying loose.

### Adaptive parameters work
- High-contrast images (portraits): more shadows (200), fewer highlights (120)
- Balanced images (landscapes): balanced shadows (200) and highlights (100)
- Dark images (night): more shadows (250), fewer highlights (50)
- Bright images (snow): fewer shadows (100), more highlights (150)

### What to improve next
1. The self-critique is still generic — needs to be specific
2. No learning between sessions (critiques don't affect stroke parameters)
3. Every painting uses the same 6 steps — could vary based on image type
4. The generated scene for text descriptions is too simple
5. No color mixing on the canvas (always uses palette colors directly)
