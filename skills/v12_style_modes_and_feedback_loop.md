---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: v12_masterworks_20260421
confidence: 5
tags: [pipeline, style-modes, feedback-loop, engraving, van-gogh]
---
v12 adds three style dimensions and two feedback tools. Together they close the loop the agent was missing.

**v12.1 complementary_shadow** — Monet broken-color principle: when a cell's L < 0.45, mix 12% of its complementary hue. Default ON at strength 0.12 across all recipes. Universal improvement — shadows feel alive instead of muddy. Zero measurable SSIM cost, clear aesthetic gain on comparison.

**v12.2 style_mode='engraving'** — a fully alternative underpainting: diagonal hachures at ±45° with density proportional to darkness. Forces grayscale, uses polyline contours. Validated on Timothy Cole's Mona Lisa mezzotint: produces a recognizable line-art rendering where v10's bristle grid produced mud. Accept `UNDER_COVERED` verdict in this mode — the paper showing between hachures is the point.

**v12.3 style_mode='van_gogh'** — replaces default underpainting with `van_gogh_underpainting`: 1.8× longer bristles, 3 passes, complementary shadow auto-boosted to 0.18. Skips mid_detail and fine_detail (VG has no ink marks). Contour pass becomes polyline width=4, saturated dark, 25% short dropped — emulating his cloisonnist outlines. Validated on The Bedroom: all elements (bed, chairs, floor, walls) now clearly visible where v11 produced a colored blob.

**v12.4 skill_effectiveness_report** — aggregates reflections by recipe, shows per-recipe run count + mean failure count + which modes fired. First time the agent can SEE that `portrait_dof sharp` ran twice with zero failures vs `engraving` ran twice with 2.5 avg failures (where most are expected/acceptable in the engraving case). Closes the feedback loop: skills are no longer self-declared confidence, they're backed by observed outcomes.

**v12.5 reflection_clusters** — groups recent reflections by failure mode. Surfaces "HARD_BANDING appeared in 8/25 runs, touching cat/bird/bedroom/mona_lisa/water_lilies — targets with large smooth areas." Enables weekly review without reading each reflection individually.

**How to use the feedback loop in session**:
1. At session start, `load_painter_brief` (includes top failures)
2. Before big changes, `reflection_clusters` to know what to avoid
3. Before declaring a recipe good, `skill_effectiveness_report` to verify
4. After new runs, `record_reflection` feeds back in for future sessions

With this, the agent has observable metrics to justify its choices, not just intuition. A recipe that consistently triggers > 1.5 avg failures should be revised or retired; one with 0 failures across 3+ runs can be promoted to confidence 4+.
