---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v6_20260421
confidence: 4
tags: ['methodology', 'evaluation', 'training']
---
When extending the tool to unknown subjects, test against **real photographs** (Unsplash, etc.), not procedurally-generated PNGs. Synthetic gradients and grid patterns hide the failure modes that matter: blurred depth-of-field backgrounds, specular highlights, overlapping objects, texture variation.

Unsplash photo URLs of the form `https://images.unsplash.com/<photo-id>?w=512&h=512&fit=crop&auto=format&q=80` are stable and cc0-friendly. Download 8–12 diverse subjects (portrait, architecture, flower, food, animal, still-life, landscape, night scene) into `targets/unsplash/` before training a new pipeline iteration.

**Why:** v5 trained on synthetic test patterns and showed 99% coverage everywhere, giving false confidence. Running the same pipeline on real photos in v6 revealed that the detail pass was visible only when stroke color was sharply darker than the underpainting — a finding that never surfaces on flat synthetic gradients.
