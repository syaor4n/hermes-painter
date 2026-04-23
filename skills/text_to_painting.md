## Text-to-Painting — Painting Without Reference

### The breakthrough: painting from WORDS

Instead of reproducing an image, the agent now paints from a text description.
The agent translates words into colors, shapes, and composition.

### How it works

1. **Parse the description** for visual elements:
   - "lonely lighthouse" → vertical white shape on a cliff
   - "rocky cliff" → dark angular shapes, bottom-left
   - "dusk" → warm orange/purple gradient sky
   - "crashing waves" → dark blue with white foam
   - "beam of light" → golden line from lighthouse into mist

2. **Assign colors** from the description:
   - "orange sky" → #C86432, #F0A050
   - "deep purple" → #783C8C
   - "crashing waves" → #283C50
   - "beam of light" → #FFFAE0
   - "mist" → #B4AAB0

3. **Compose the scene**:
   - Sky gradient (top to bottom)
   - Ocean (bottom half, horizontal strokes)
   - Cliff (angular shapes, left side)
   - Lighthouse (vertical, center-left)
   - Light beam (diagonal, from lighthouse)
   - Mist (low-alpha overlapping strokes)
   - Wave foam (small dabs)

4. **Paint with existing techniques**:
   - Multi-scale brush strokes
   - Layered composition
   - Low-alpha glazes for atmosphere

### What this means

The agent has evolved from:
- v1.0: "Copy this image pixel by pixel"
- v2.0: "Paint with style and accuracy"
- v3.0: "Paint from a text description"

This is CREATION, not reproduction. The agent generates original art
from its understanding of visual language.

### Example descriptions the agent can paint

- "A lonely lighthouse on a rocky cliff at dusk"
- "A warm golden sunset over calm water"
- "A dark forest with rays of light through the trees"
- "A portrait in warm Rembrandt lighting"
- "An abstract composition in blue and gold"

### Results

```
Painting              Type         Strokes  Reference
Abstract golden       Pure style   205      None
Lonely Lighthouse     Text-based   884      Text description
```

### Skills (19 total)
The last: `text_to_painting.md` — how to paint from words.
