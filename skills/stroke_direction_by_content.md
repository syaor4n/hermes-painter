---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: training_session_20260420
confidence: 5
tags: ['workflow', 'direction', 'technique']
---
Match stroke direction to the content structure:
- horizontal: skies, water, oceans, snow-covered ground, sunsets
- vertical: forests (trunks), cityscapes (buildings), portraits (optional), grass
- random: abstracts, night scenes (stars), smoke/fog, textures

Wrong direction = striped-looking painting that does not read as the subject. Use layered_underpainting(..., direction=X) to set this.
