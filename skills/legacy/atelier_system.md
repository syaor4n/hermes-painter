## Atelier System — The AI Painter's Studio (v3)

### Philosophy
- **Limited palette**: 6-8 colors per painting (extracted from reference or generated for mood)
- **Gestural strokes**: 14-44px wide (adaptive), not 8px pixel blocks
- **Dark to light**: Rembrandt underpainting → midtones → highlights
- **Visual hierarchy**: Focal point gets detail (14px), background stays loose (44px)
- **Self-critique**: After each painting, analyze what worked and what didn't
- **Skills accumulate**: Each critique improves the next painting
- **Image-type adaptation**: Different parameters for dark/bright/high_contrast/balanced images

### 6-Step process (with adaptive parameters)

**Step 1: Dark underpainting** (40-80px strokes)
- Alpha: 0.55 (dark images) to 0.7 (bright images)
- Cover canvas with dark versions of palette colors
- Varied stroke directions (horizontal / diagonal up / diagonal down)

**Step 2: Midtone blocking** (adaptive stroke sizes)
- Near focal point (<80px): 14px strokes, alpha 0.65
- Mid distance (80-160px): 24px strokes, alpha 0.55
- Background (>160px): 44px strokes, alpha 0.45
- Uses closest palette color for each block

**Step 3: Shadow accents** (10px strokes, alpha 0.65)
- Threshold: 20th-60th percentile (adaptive by image type)
- Count: 100-250 (adaptive)

**Step 4: Highlight accents** (dabs, alpha 0.5)
- Threshold: 60th-80th percentile (adaptive)
- Count: 50-150 (adaptive)

**Step 5: Focal point detail** (6px strokes, alpha 0.35-0.75)
- 60px radius around focal point (not 160px)
- Density decreases with distance from center
- 150 strokes max

**Step 6: Signature marks** (7px strokes, alpha 0.15)
- 40 scattered brush marks from the palette
- Visible brushwork (the "hand of the artist")

### Focal point detection (3 methods)

1. **Portrait detection**: Skin tone clustering (R>G>B, R>100, G>60, B>40)
   - If >500 skin pixels found → use center of mass as focal point
   - This correctly identifies faces

2. **Edge + variance detection**: For landscapes/objects
   - Score = block_variance * 0.5 + edge_density * 50
   - Center bias: slight preference for center-ish positions

3. **Default**: Center of canvas (256, 256)

### Image type detection and adaptation

```
Type           Criteria                Shadows  Highlights  Underpaint
dark           mean < 80              250      50          0.55
bright         mean > 180             100      150         0.70
high_contrast  std > 60               200      120         0.65
balanced       else                   200      100         0.65
```

### Palette extraction
- Quantize pixels (divide by 40, multiply by 40+20)
- Count combinations, get top N colors
- Filter out colors too similar (<40 distance)
- Result: 6-8 distinct palette colors

### Self-improvement methodology

The agent follows a cycle:
1. **Paint** — using current best techniques
2. **Self-critique** — specific observations (shadow coverage, palette range, focal position)
3. **Art critics panel** — 5 famous painters provide OBJECTIVE external feedback
4. **Synthesize** — combine all feedback into an action plan
5. **Save** — write critique + parameters to skills/latest_critique.md
6. **Load** — next painting reads previous critique and applies learned parameters
7. **Repeat** — each cycle improves the agent

### Art Critics Panel (external validation)

Self-critique is biased. The agent can't see its own weaknesses.
External critics provide OBJECTIVE feedback from different artistic perspectives:

| Critic | Philosophy | What they see |
|--------|-----------|---------------|
| Monet | Color and light | Color harmony, atmospheric depth, light source |
| Rembrandt | Value and drama | Shadow depth, highlight contrast, value range |
| Picasso | Simplification | Stroke count, palette size, form complexity |
| Van Gogh | Expression | Brush texture, color saturation, emotional temperature |
| O'Keeffe | Composition | Focal point position, balance, edge clarity |

Each critic rates 1-10 and gives specific observations.
The synthesis combines all feedback into an action plan.

Example on a portrait:
```
Monet: 6/10 — Good color harmony
Rembrandt: 6/10 — Good dramatic lighting
Picasso: 3/10 — Too many colors, too much detail
Van Gogh: 3/10 — No visible brush texture, colors too muted
O'Keeffe: 4/10 — Composition unbalanced

Average: 4.4/10
Action plan: more texture, more saturation, balance composition
```

The critics are NOT biased — they each see different things.
Picasso wants simplification, Van Gogh wants expression, O'Keeffe wants composition.

### Results across 16+ paintings

```
Session 1 (initial): 6 paintings, 586-705 strokes, no adaptation
Session 2 (improved focal): 3 paintings, 729-771 strokes, better focal
Session 3 (adaptive): 4 paintings, 729-791 strokes, face detection works
Session 4 (art critics): 3 paintings, 729-791 strokes, objective feedback
```

### Complete self-improvement architecture

```
┌─────────────────────────────────────────────────┐
│                 ATELIER SYSTEM                   │
├─────────────────────────────────────────────────┤
│                                                  │
│  Input: Image or Text Description               │
│     ↓                                            │
│  Analysis: Image type, palette, focal point     │
│     ↓                                            │
│  Painting: 6 steps, adaptive parameters         │
│     ↓                                            │
│  Critique Panel:                                │
│    ┌──────────┬───────────┬──────────┐          │
│    │ Monet    │ Rembrandt │ Picasso  │          │
│    │ color    │ drama     │ simplify │          │
│    └──────────┴───────────┴──────────┘          │
│    ┌──────────┬───────────┐                     │
│    │ Van Gogh │ O'Keeffe  │                     │
│    │ express  │ compose   │                     │
│    └──────────┴───────────┘                     │
│     ↓                                            │
│  Synthesis: Action plan + parameters            │
│     ↓                                            │
│  Save: skills/latest_critique.md                │
│     ↓                                            │
│  Next painting loads and applies                │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Key insight
The agent doesn't need to reproduce pixels. It needs to PAINT WITH INTENTION:
- Limited palette for harmony
- Large gestural strokes for expression
- Focal point for visual hierarchy
- Dark-to-light for depth
- Visible brushwork for authenticity
- **External critics for objective improvement** (not just self-critique)
