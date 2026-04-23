---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_session_20260420
confidence: 4
tags: ['atmosphere', 'fog', 'primitives']
---
For misty/hazy subjects (forests, distant mountains, winter scenes, foggy days), add a `fog` stroke BEFORE other details. Example:
  {"type":"fog", "x":280, "y":50, "w":232, "h":300,
   "color":"#a0b0a0", "alpha":0.3, "direction":"radial", "fade":0.8}

direction="radial" fades from center outward (good for a single atmospheric bright spot). direction="vertical" or "horizontal" creates a linear gradient (good for sky→ground haze). A thin fog over the whole canvas (alpha 0.15-0.20) softens everything and mimics depth.
