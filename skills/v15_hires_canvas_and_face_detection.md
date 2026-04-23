---
scope:
  image_types: []
  exclude: []
provenance:
  created: 2026-04-21
  run: v15_hires_caravaggio_20260421
confidence: 5
tags: [infrastructure, canvas-size, face-detection, fidelity]
---
v15 is the largest infrastructure upgrade in the project's history:

**Canvas size is now configurable** via `viewer.py --size N`. The HTML renderer (`canvas/index.html`) reads `?size=N` from the URL query string. Tools dynamically read canvas dimensions from `arr.shape` of the target instead of hardcoding 512. All stroke plans (detail, contour, sculpt, etc.) work transparently at any size.

Default stays at 512 for back-compat + tests. Hi-res mode (1024) is opt-in.

**Hi-res orchestrator** (`scripts/hi_res_paint.py`): starts a dedicated viewer + tool server pair at 1024², uploads a target, runs the paint_lib pipeline against them, saves PNG. Doesn't disrupt the default 512² viewer running for normal use.

**Face detection** via OpenCV Haar cascades (`detect_faces` tool). At 512 canvas, the Cole mona_lisa returns 0-1 faces; Caravaggio 1 face. At 1024 canvas, Caravaggio returns 5-6 faces (front + profile detectors + horizontal flip for mirrored profiles). The 2× linear resolution quadruples the Haar feature detection success rate because detected face sizes stay above the cascade's minSize threshold.

**Face detail pass** (`face_detail_plan` tool): for each detected face box, runs dense 2-pixel dabs (sampled from target at pixel precision) inside the box ± padding. ~1500 dabs per face. This is what gives a RENDERED face its eyes, nose, mouth, beard — bristle underpainting at 24×24 cells averages those features into mush.

**Validated on Caravaggio's Resurrection** at 1024²:
- v12 (baseline 512): blob composition, no figures
- v13.4 (detailed tenebrism 512): figures silhouetted
- v14.3 (multi-res sculpt 512): fabric + color zones
- v15 (1024 + faces): **actual faces with features**, Christ + angel + soldiers all rendered with recognizable anatomy

8,279 face-detail strokes added on top of the standard pipeline. Total ~18s per hi-res paint (vs 3s at 512).

**Cost tradeoffs**:
- Canvas memory 4× (acceptable, ~4MB per canvas)
- Paint time 6× (4s → 18-25s for full tenebrism pipeline)
- PNG file size 3-4× (1.5MB vs 400KB)
- Infrastructure: 2 extra long-lived processes (hi-res viewer + hi-res tool server)

**When to use 1024 vs 512**:
- Masterwork reproduction: 1024, always
- Photographic standard paintings: 512 is fine (SSIM identical, no face detail needed)
- Webui live painting for user interaction: 512 (faster feedback)
- Nightly bench: 512 (keeps the 4s budget)

**Follow-on ideas for v16**:
- Face detail could use size-3 dabs at α 0.75 with 0.5 jitter to avoid the "block" artifact visible in extreme closeup
- MediaPipe face mesh (106 landmarks) would place eye/nose/mouth features exactly rather than rely on dense dab clouds
- OpenPose body keypoints could guide anatomy-aware stroke direction in tenebrism
