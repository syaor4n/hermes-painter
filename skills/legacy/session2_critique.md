## Session 2 — 3 Paintings with Improved Atelier

### What improved from session 1

```
Change                    Before    After      Impact
Focal detection           variance  variance+edges+center  Better placement
Shadow threshold          <20th %   <40th %    More shadows visible
Focal zone radius         160px     60px       Concentrated detail
Background strokes        36px      44px       Bolder, looser
Focal strokes             20px      14px       Tighter detail
Signature alpha           0.1       0.15       More visible brushwork
```

### Results

```
#  Subject              Strokes  Focal       Palette
1  Portrait (image)       771    (160,48)    dark browns/reds
2  Sunset (image)         729    (304,32)    gold/orange/dark
3  Building sunset (text) 771    (320,352)   purple/orange/gray
```

### What's working better
- Focal point now detects the sun in sunset (304, 32) and the building (320, 352)
- More shadows visible (200 strokes vs 0-150 before)
- Background strokes are bolder (44px vs 36px)
- Focal detail is more concentrated (60px zone vs 160px)

### What still needs work
1. The focal point for portrait is still not on the face
2. Every painting uses the same 6-step process
3. No adaptation to image type (sunset ≠ portrait ≠ forest)
4. The self-critique is still generic
5. No learning between paintings (skills don't affect next painting yet)

### Next improvements
1. For portraits: detect face (skin tone) as focal point
2. Adapt step sizes based on image complexity
3. Load previous critiques before painting
4. Write specific critiques, not generic ones
5. Vary the approach: some images need more underpainting, some need less
