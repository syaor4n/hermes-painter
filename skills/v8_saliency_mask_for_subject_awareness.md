---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: training_v8_20260421
confidence: 9
tags: ['technique', 'saliency', 'subject', 'infrastructure']
---
A Laplacian-variance saliency mask (`saliency_mask` tool) cheaply isolates in-focus subjects from blurred backgrounds. With `blur_sigma=8.0`, percentile-based normalization (5th–95th), a 0.5 gamma boost, and a small center bias (0.15), it consistently segments faces, animals, and foreground objects in Unsplash-style DOF photos.

**Gating rule:** only apply the mask if `separability > 0.18` AND `0.05 < fg_fraction < 0.8`. Below 0.18 the mask is noise; outside the fg_fraction band it's useless (too empty or too full). 20/22 targets passed the gate in v8.

**How the mask flows downstream:**
- `detail_stroke_plan(mask_path=...)` — skip strokes whose midpoint is in low-saliency; keeps soft backgrounds soft.
- `contour_stroke_plan(mask_path=..., mask_boost=2.5)` — components mostly inside the mask get weighted 2.5×; components mostly outside get weighted 0.4×. Subject contours win limited budgets.
- `highlight_stroke_plan(mask_path=...)` — only keep catchlights inside the subject.

**Why it works even without ML:** for DOF-heavy photos the Laplacian distinguishes sharp edges (in focus) from soft gradients (out of focus). For flat/wide photos (landscapes, abstracts) separability stays below threshold and we fall back to v7 behavior — no quality loss.
