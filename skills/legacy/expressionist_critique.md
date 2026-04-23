## Expressionist Critique — Lessons Learned

### What went wrong with 38 strokes

The 38-stroke portrait was "too simple, on ne reconnait rien." The agent was trying to be
"expressive" by using fewer strokes, but ended up with abstract symbols instead of a portrait.

The mistake: confusing ABSTRACTION with EXPRESSION.
- Abstraction = removing detail until nothing recognizable remains
- Expression = using visible brushwork to convey feeling while keeping the subject clear

### The right approach to expressionism

Expressionism doesn't mean FEWER strokes — it means MORE VISIBLE strokes.
Every stroke should be intentional and contribute to the image.

**Van Gogh's Starry Night**: ~thousands of visible strokes, not 38.
**Monet's Water Lilies**: thick layered brushwork, not sparse marks.

### Stroke count by element

| Element | Minimum | Good | Maximum |
|---------|---------|------|---------|
| Background | 20 | 100 | 300 |
| Face planes | 10 | 50 | 150 |
| Eyes | 4 | 10 | 20 |
| Nose | 2 | 5 | 10 |
| Lips | 2 | 5 | 10 |
| Hair | 5 | 30 | 80 |
| Total portrait | 50 | 200 | 600 |

For landscapes:
| Element | Minimum | Good | Maximum |
|---------|---------|------|---------|
| Sky | 10 | 50 | 200 |
| Mountains | 10 | 50 | 200 |
| Forest | 20 | 100 | 500 |
| Ground | 10 | 50 | 200 |
| Total landscape | 50 | 300 | 1000 |

### Value structure is more important than stroke count

The 38-stroke painting lacked VALUE CONTRAST. Without proper light/shadow structure,
even 1000 strokes won't look 3D.

Always check: Are my shadows at least 2x darker than my highlights?
If not, push values harder before adding more strokes.

### The user's feedback that changed everything

"Copies floues" → led to multi-scale approach (SSIM 0.850)
"Trop simple" → led to proper stroke count per element
"Manque de détails" → led to edge contours + fine fill
"Ton propre style" → led to Lumière Dorée + glazed style
"Peindre sans référence" → led to text-to-painting
