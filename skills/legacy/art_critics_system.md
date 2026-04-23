## Art Critics Panel — External Validation System

### Why self-critique is biased
The agent can't see its own weaknesses. It always says "could be bolder" but
doesn't know HOW to be bolder. External critics from different artistic
perspectives provide OBJECTIVE feedback.

### The 5 Critics

| Critic | Philosophy | Metric | What they catch |
|--------|-----------|--------|-----------------|
| Monet | Color + light | Palette range, atmospheric depth | Muddy colors, flat lighting |
| Rembrandt | Value + drama | Shadow %, highlight %, value range | No depth, flat values |
| Picasso | Simplification | Stroke count, palette size, block complexity | Too many strokes, too detailed |
| Van Gogh | Expression | Color variation in 16x16 blocks | No brush texture, mechanical look |
| O'Keeffe | Composition | Focal centrality, L/R balance, edge clarity | Unbalanced, focal too far from center |

### The improvement loop
1. Paint → 2. 5 critics evaluate → 3. Synthesize → 4. Save improved params
5. Next painting loads params → 6. Apply improvements → 7. Critics evaluate again

### Example improvement
Van Gogh rated 3/10: "No visible brush texture"
→ Saved extra_texture=True
→ Next painting added 80 texture strokes + more visible signature marks
→ Van Gogh rated 5/10: "Good brush texture (58% blocks have variation)"

### Key metric fix
Van Gogh's original metric (edge density) didn't capture brush texture.
Changed to color variation in 16x16 blocks (standard deviation > 15 = visible texture).
This correctly identifies visible brushwork vs smooth areas.

### Integration with atelier
After each painting:
1. Run all 5 critics on the final image
2. Each rates 1-10 with specific observations
3. Synthesize into action plan
4. Save improved params to skills/params_{image_type}.json
5. Next painting of same type loads these params
