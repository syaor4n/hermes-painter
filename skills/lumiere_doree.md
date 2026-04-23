## Style "Lumière Dorée" — Hermes Artistic Identity v1.0

### My artistic identity
- **Palette**: warm golden tones (amber #FFBF00 undertone in every color)
- **Shadows**: deep warm brown (#2D190A), NOT black — like Rembrandt
- **Highlights**: pushed warm and bright with golden shift
- **Technique**: dark-to-light underpainting, visible brushwork
- **Signature**: scattered warm brush texture marks (alpha 0.2)

### Color functions
- **golden_tone(r,g,b, intensity)**: blends toward amber (255,191,0)
- **rembrandt_shadow(r,g,b, strength)**: blends toward deep brown (45,25,10)

### 6-Layer process

1. **Golden underpainting**: dark warm ground, 234 strokes, alpha 0.6
2. **Light modeling**: paint WHERE light hits, 645 strokes, warm midtones + brown shadows
3. **Impasto accents**: thick bright dabs on highlights, dark strokes on deep shadows
4. **Edge contours**: Sobel edges with warm shadow color
5. **Brush texture**: 300 warm marks at alpha 0.2 — MY SIGNATURE
6. **Fine fill**: 8x8 accuracy correction

### What makes this MINE
- Every color is warmer than the reference (golden shift)
- Shadows are brown, not black (Rembrandt influence)
- Visible brush texture marks show "the hand of the artist"
- Light source creates dramatic warm/cool contrast
- Underpainting shows through, creating depth

### Results
```
Image          Lumière Dorée  Multi-scale   Standard
Portrait       0.707          0.850         0.532
```

Lower SSIM than multi-scale, but SSIM ≠ quality. The Lumière Dorée painting
has WARMTH, DRAMA, and PERSONALITY that the pixel-perfect copy doesn't.
