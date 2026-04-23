# Changelog

All notable changes to the painter. Versions are as-recorded by the painter
itself in `skills/style/signature.md`; dates reflect the style-evolution log
it kept during development.

This file is human-curated; the agent's own journal lives in `journal.jsonl`.

## [Unreleased]

### Removed

- **Paint from description (text-to-paint).** The keyword→shape→paint
  module (`paint_lib.brief`, `scripts/text_paint.py`, `/api/paint-text`,
  `tool_paint_from_brief`, `tool_self_critique_vs_prompt`) and the
  corresponding viewer UI card are removed. The feature claimed more than
  it delivered — a prompt like "a crow with details on the wings" fell
  back to a hardcoded sunset because the keyword dict had no entry, and
  upgrading it would have required a paid image-gen dependency. The
  project's core pitch remains image → painterly stylization.
  `scripts/show_learning.py` is removed with it (it depended on
  `paint_from_brief`; the `gallery/learning/` evidence PNGs are
  unaffected). Design:
  `docs/superpowers/specs/2026-04-22-strip-paint-from-text-design.md`.

### Added

- **Duet workshop in the viewer UI.** A sidebar card below Morph with
  two persona dropdowns (populated dynamically from the tool server's
  `list_personas`, so community personas added via `PERSONAS_PATH`
  appear without code changes), a max-turns slider (2–20, default 6),
  and a "Start duet" button that spawns a full `scripts/duet.py` run as
  a subprocess. Each turn paints live to the viewer canvas via the
  existing tool-server bridge, so the iteration history strip fills
  with turn-by-turn snapshots automatically. Backend: new
  `GET /api/list_personas` proxy + new `POST /api/paint_duet` with
  validation (target loaded, busy lock, different personas, registry
  membership). Design spec:
  `docs/superpowers/specs/2026-04-22-duet-workshop-design.md`.

- **Morph workshop in the viewer UI.** A sidebar card below the Paint
  controls with two dropdowns (Start / End style) and two buttons:
  "Suggest for this target" proxies the `plan_style_schedule` tool so
  the agent's rule-based start/end pair + rationale surface directly in
  the UI, and "Paint morph" kicks off an `auto_paint(style_schedule=…)`
  run against the chosen pair. `POST /api/paint` gained an optional
  `style_schedule` field; a new `POST /api/suggest_morph` endpoint
  proxies to the tool server so the browser stays same-origin. Design
  spec: `docs/superpowers/specs/2026-04-22-morph-workshop-design.md`.

- **Preset bar in the viewer UI.** Six one-click style tiles — Classical,
  Van Gogh, Tenebrism, Pointillist, Engraving, Golden Hour (the
  `lumiere_doree` community style) — appear as a horizontal strip
  above the studio image. Clicking a tile kicks off a paint in that
  style personality without touching the sliders or the `style_mode`
  dropdown (which remain orthogonal controls for pipeline intensity).
  `POST /api/paint` gained an optional `style_personality` field with
  a 6-value whitelist; `scripts/auto_paint.py` reads the new env var
  `PAINTER_STYLE_PERSONALITY` and passes it as the `style_mode` kwarg
  to the pipeline. Design spec:
  `docs/superpowers/specs/2026-04-22-preset-bar-design.md`.

- **Collaborative duet** (`paint_duet` tool, manifest #50, plus
  `list_personas` tool #51). Two named painter personas alternate
  critique-and-correct turns on one canvas. Personas live in
  `personas/<name>/persona.yaml` (same loader pattern as community
  styles). Ships with three personas: `van_gogh_voice`, `tenebrist_voice`,
  `pointillist_voice` — deliberately opposed aesthetics. Each persona
  has weighted failure detectors it "cares about" and a taste filter
  that picks which worst-cells it has legitimate claim to correct.
  Turns are rejected on SSIM regression via snapshot/restore.
  Three demos under `gallery/duet/` with per-turn snapshots, journals,
  solo-opening controls, and turn strips. Design spec:
  `docs/superpowers/specs/2026-04-22-collaborative-painters-design.md`.
  Contributing guide: `personas/README.md`.
- **Dimensional-effects slider panel in the viewer UI.** A new DIMENSIONAL
  EFFECTS panel in the right sidebar exposes five `dimensional_effects`
  channels — `contrast_boost`, `complementary_shadow`, `van_gogh_bias`,
  `tenebrism_bias`, `pointillism_bias` — as draggable range sliders with live
  numeric readouts. Slider ranges are taken from `EFFECT_LIMITS`; initial
  values are the `STYLE_DEFAULTS["default"]` vector. A "Preview" button POSTs
  the current slider state to the new `/api/morph_preview` endpoint, which
  re-paints the current target with those effect overrides and shows a result
  line (`painted in Xs · ssim=Y · style_mode=Z`). A "Reset" button restores
  defaults without triggering a paint. The panel handles "no target loaded"
  gracefully in both the server (400) and the UI status area.

- **`POST /api/morph_preview` endpoint** on the viewer HTTP server. Accepts
  `{contrast_boost, complementary_shadow, van_gogh_bias, tenebrism_bias,
  pointillism_bias}` and re-paints the current target using `auto_paint` with
  those overrides. `style_mode` is derived from the highest bias value (kicks
  in at ≥ 0.2). Returns `{ok, ssim, duration_s, style_mode}` on success, or
  400 `{error:"no target loaded"}` if no target is set.

- **Community-opened styles (parameter-only).** `styles/<name>/style.yaml`
  scanner populates STYLE_DEFAULTS + STYLE_DISPATCH at import time; set
  STYLES_PATH env var for extra directories. New `list_styles` tool.
  First shipped community style: `styles/lumiere_doree/` (warm golden-hour
  palette). Code-style plugins (`generator.py`) remain v2 per spec §8.
- **Real-time style morphing** (spec: `docs/superpowers/specs/2026-04-22-real-time-style-morphing-design.md`).
  A run can now morph between two styles across the 8-phase pipeline via
  a new `style_schedule={start,end,rationale}` kwarg on `auto_paint` /
  `paint_from_brief`. New `plan_style_schedule` tool in the manifest
  recommends a schedule based on target analysis. Backwards compatible:
  `style_mode=X` behavior is unchanged, and a degenerate schedule
  `{start:X, end:X}` is pixel-identical to `style_mode=X` (locked in
  by `test_morph_degenerate_matches_style_mode`).
- Three demo pairings under `gallery/morph/` with side-by-side uniform-end
  controls and `rationales.md`.
- `scripts/timelapse.py --phase-strip` for 8-panel labeled strip output.
- `tests/test_tools_manifest.py` — TOOLS ↔ MANIFEST sync invariant.
- CI soft-guard against `STYLE_DISPATCH[` scatter outside `paint_lib/morph.py`.

### Security

- Both HTTP servers now default to binding `127.0.0.1` and print a warning
  when `--host` is set to a non-loopback address.
- `tool/load_target` and `mask_path`-accepting tools now resolve paths
  through a `_safe_path` allowlist (targets/, runs/, reflections/, skills/, /tmp).
  Requests outside the allowlist return `{"error": ...}` instead of reading
  the file. Images are also validated with `Image.verify()` before upload.

### Removed

- Dead `_impasto_strokes` function (`paint_lib/pipeline.py`) — had been
  disabled by default since v7.5 with no callers. `impasto_n = 0` is
  preserved in the result dict for shape compatibility.

### Changed

- **pipeline.py phase refactor (CODE_REVIEW P2.11).** The ~940-line
  `auto_paint` is now a ~490-line orchestrator over a shared
  `PipelineContext` dataclass plus 14 focused phase modules under
  `scripts/paint_lib/phases_pkg/`. Behavior is byte-identical; locked
  in by a determinism baseline (`tests/fixtures/pipeline_baseline_great_wave_seed42.json`)
  and the full integration suite. No user-visible change. Design spec:
  `docs/superpowers/specs/2026-04-22-pipeline-phase-split-design.md`.
  Phase modules: analyze, skill_feedback, underpaint, fog, edge,
  gap_fill, detail, contour, highlight, face_detail, sculpt,
  critique_correct, score, reflect.

- **Contour rendering revamped to painterly multi-stroke.** Each traced
  edge component now emits 3–8 overlapping short brush strokes (bristle
  texture, tapered width, per-stroke alpha 0.30–0.55, 1–3 px perpendicular
  position jitter, color sampled from the *current canvas* rather than
  the target). Result: contours integrate with the underpainting instead
  of reading as uniform pen lines. Old behavior preserved via
  `painterly=False` kwarg on `contour_stroke_plan` — opt-in for the
  engraving style and the tenebrism fine-feature pass where a drawn
  look is desired. Design spec:
  `docs/superpowers/specs/2026-04-22-painterly-contours-design.md`.

- Silent `except Exception: pass` sites in `pipeline.py`, `brief.py`, and
  `failures.py` now emit single-line stderr warnings (`[pipeline] X failed: ...`).
  Failures still degrade gracefully; they no longer vanish.

### Docs

- Added `CODE_REVIEW.md` — a staged P0/P1/P2/P3 walkthrough.
- Added this `CHANGELOG.md`.
- Added hackathon framing + gallery section in `README.md`.

---

## [v15] — 2026-04-21 · hi-res canvas and face detection

- `viewer.py` now accepts `--size 1024` for hi-res work.
- `detect_faces` tool (OpenCV Haar frontal + profile).
- `face_detail_plan`: dense dab clusters gated on face detections —
  previously disabled because it misfired on landscapes; now only fires
  where the detector actually found a face.

## [v14] — 2026-04-21 · sculpt multi-res

- `sculpt_correction_plan` tool: dense per-cell error correction on the
  saliency region, parameterized per image_type (dark/muted use higher
  error threshold + lower alpha to avoid regressing on noisy near-black
  regions).

## [v13] — 2026-04-21 · tenebrism + banding fix

- Tenebrism faithful-reproduction mode (high-contrast Caravaggio-style
  dark field with selective light).
- Stroke-overlap hard-banding fix: underpainting strokes now extend
  1.4× cell size so grid frequency doesn't beat through the final image.

## [v12] — 2026-04-21 · style modes + feedback loop

- Style modes: `van_gogh`, `tenebrism`, `pointillism`, `engraving`.
- **Dimensional-effects feedback loop**: skills can declare
  `dimensional_effects` in their YAML frontmatter (`contrast_boost`,
  `van_gogh_bias`, etc.). Values are summed across all applicable skills
  and applied as pipeline parameter deltas — the first learning channel
  that actually changes stroke emission, not just prompt-level memory.
- `skill_promote` tool: scans recent high-confidence reflections;
  recurring `what_worked` phrases become new skills or bump existing.

## [v10] — 2026-04-21 · tonal finishing + web UI polish

- Finishing and underpainting now live in the same tonal universe — no
  more `#101010` pure-black outlines. A red lip gets a carmine outline,
  not a cartoon outline.
- 40 % of contour components dropped (lost-and-found edges); radial
  alpha falloff around the saliency center keeps the focal point sharp.
- Infra: paint-lock, gzipped stroke log, `safe_phase` wrappers, pipeline
  pytest, auto-regression alert, pixel-parity test, LAB palette.
- Web UI: Compare A/B, style-mode dropdown, Download PNG, phase labels,
  letterbox aspect.
- 35 tools total.

## [v9] — 2026-04-21 · infrastructure maturation

- `test_renderer_parity.py` — pixel-MAE parity between PIL and canvas
  renderers across all 12 stroke types. Catches drift.
- `critique_correct` + best-of-N refine final output at acceptable cost.
- Segmentation mode (SLIC) for posterized alternative style.
- `sample_grid` batch tool — replaces O(N²) `sample_target` calls.
  Paint time 9 s → 3 s per canvas.
- 8-phase pipeline, 33 tools.

## [v8] — 2026-04-21 · saliency + local direction + highlights

Four coordinated additions turn the painter from descriptive to interpretive:

- Laplacian saliency mask gates detail/contour effort — backgrounds stay soft.
- Per-cell structure-tensor angles drive local stroke direction — fur,
  hair, fabric align correctly.
- Tanh contrast S-curve in underpainting pushes darks + lights apart —
  no more muddy greys.
- Bright warm dabs at local maxima (eyes, lips, metal, water now read alive).

Pipeline order is load-bearing: highlights MUST be last.

## [v7] — 2026-04-21 · contour tracing

- Phase 6: Canny edge detection + skeletonize + connected-component
  tracing emits bezier curves that follow real object boundaries
  (glasses frames, eye outlines, beaks, lip shapes).
- Random-walk detail produces scribbles; ordered-path contour tracing
  produces drawing. Critical for faces + animals.

## [v6] — 2026-04-21 · two-tier detail finishing

- Mid-detail (percentile 94, α 0.55, contrast color) for soft shading.
- Fine-detail (percentile 98.5, α 0.95, pure dark) for crisp accents.
- Polyline marks read as drawing over paint.
- Switched from synthetic gradients to real Unsplash photos for training.
  Synthetic targets were giving false 99 % coverage that hid weak detail.
- Canvas now 2200–2300 strokes across 5 layers.

## [v4] — 2026-04-20 · feature-aware sun painting

- `find_features` tool called first — 60 px positional error on sun avoided.
- 6-stop radial-gradient `glow` stroke for buttery sun (vs bullseye rings).
- Composition rule: dock now aligns with sun's vertical axis.

### Early painter lessons (≤ v4)

- Don't optimize SSIM directly — produces flat bands.
- Always `dump_canvas` + Read after every batch — can't judge painterly
  quality from scores alone.
- The default brush was a highlighter ribbon, not a real brush. Canvas
  and local renderer now produce bristle textures with color variation.
  A "painting" is 400–800 strokes, not 80.
