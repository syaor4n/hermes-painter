## Constructive Evaluation — The Key to Self-Improvement

### The problem with opinionated critics
Famous painter personas (Monet, Rembrandt, Picasso, Van Gogh, O'Keeffe)
rated paintings based on their ARTISTIC PREFERENCES, not quality.

- Picasso wanted minimalism → gave 3/10 to any painting with many strokes
- Rembrandt wanted drama → penalized low-contrast images
- Their demands were CONTRADICTORY (minimalism vs expression)
- Average rating: 4.0/10 — not useful for improvement

### The solution: constructive teachers
Replace critics with teachers focused on WHAT'S GOOD and HOW TO IMPROVE.

```
Old: "Picasso: 3/10 — too many strokes" (punitive)
New: "Composition: 5.0 — focal point needs more contrast" (constructive)
```

### The 4 teachers

| Teacher | Evaluates | Typical score |
|---------|-----------|---------------|
| Composition | Focal point, hierarchy, depth, balance | 5.0-7.0 |
| Color | Palette size, value range, warmth, saturation | 6.0-8.0 |
| Form | Regional distinction, edge clarity | 6.0-8.0 |
| Texture | Brush texture %, surface variety, stroke direction | 7.0-7.5 |

### Results comparison

```
System              Avg rating   Useful suggestions per painting
Opinionated critics    4.0       0-1 (mostly punitive)
Constructive teachers  6.7       2-4 (specific, actionable)
```

### Why teachers work better
1. They praise what's GOOD (motivating)
2. They give SPECIFIC suggestions (actionable)
3. They don't contradict each other (coherent)
4. They adapt to the image type (contextual)

### Implementation
- `art_teachers.py` — the 4 teacher classes with evaluate() methods
- Integrated into `atelier.py` after each painting
- Suggestions saved to critique file for next painting to apply
- `params_{image_type}.json` stores improved parameters per image type

### Key suggestion patterns
- "Focal point needs more contrast" → add highlights at focal
- "Background too detailed" → use wider strokes (50-80px) in background
- "Colors could be more saturated" → boost palette saturation by 1.2x
- "Palette mostly cool" → add warm accent dabs
