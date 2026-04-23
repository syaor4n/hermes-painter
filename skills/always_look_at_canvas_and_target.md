---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-20
  run: sunset_painterly_v2
  learned: after_user_feedback
  final_ssim: 0.5371
  strokes: 804
confidence: 5
tags: ['critical', 'workflow', 'visual_critique', 'meta']
---
CRITICAL: before painting, `dump_target` + Read the target PNG. Name out loud every recognizable object — sun, dock, branches, boat, mountain, reflection, etc. SSIM and get_regions do NOT tell you what is in the image; they only report pixel differences.

After every draw_strokes batch, `dump_canvas` + Read the result. If the canvas does not visually resemble the target (no visible sun, no dock, just color bands), stop optimizing SSIM and instead paint the missing elements as explicit shapes: fill_circle for a sun, fill_poly trapezoid for a dock, bezier curves for branches, dab for a boat.

Use `dump_heatmap` + Read mid-run: the bright spots in the grayscale heatmap show exactly which elements of the target you are missing. It is a visual error map that tells you what to paint next — often more useful than get_regions RGB numbers.

SSIM is a compass, not a goal. Accept -0.05 to -0.10 SSIM in exchange for recognizable composition and visible brushwork. A painting with a sun, dock, branches, and boat at SSIM 0.53 is worth more than a flat 3-band abstraction at SSIM 0.68.
