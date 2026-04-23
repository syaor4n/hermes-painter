---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: sunset_v4
  target: targets/sunset.jpg
confidence: 4
tags: ['technique', 'primitives', 'light']
---
For suns, moons, lamps, halos — use the `glow` stroke, NOT stacked fill_circle. A radial gradient produces a smooth continuous color transition, while stacked circles produce visible concentric rings that look like a target or bullseye.

Example sun (smooth warm gradient):
  {"type":"glow", "x":254, "y":221, "r":80,
   "stops":[[0,"#ffffff"],[0.1,"#fff0a0"],[0.25,"#ffc860"],[0.45,"#f08838"],
            [0.7,"#b84422"],[1,"rgba(140,40,20,0)"]],
   "alpha":0.95}

Tip: use at least 5 color stops to get a buttery transition. End with an rgba(...,0) stop for a soft fade-out. The last color (transparent) determines how the glow blends into the surrounding sky.

For a bright core inside the halo, layer a second smaller `glow` on top.
