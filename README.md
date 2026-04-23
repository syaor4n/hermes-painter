# painter

[![CI](https://github.com/syaor4n/hermes-painter/actions/workflows/ci.yml/badge.svg)](https://github.com/syaor4n/hermes-painter/actions/workflows/ci.yml)

<p align="center">
  <img src="./gallery/learning/hero_arc.gif" width="320" alt="Animated learning arc: Hokusai's Great Wave painted in van_gogh style, cycling through target, cold paint, and primed paint after 5 priming runs."/>
  <br/>
  <sub><i>Hokusai's <i>The Great Wave off Kanagawa</i>, painted in van_gogh style, seed 7. The animation cycles through the target (reference), a <b>cold</b> paint (no priming, zero applied skills), and a <b>primed</b> paint after 5 priming runs on feature-nearest neighbors. Same seed, same style — only the skills state differs between cold and primed.</i></sub>
</p>

<p align="center">
  <b>This agent doesn't just paint. Its memory changes how it paints.</b>
</p>

**For developers and researchers exploring creative agents with persistent,
inspectable memory.** This is a testbed where every skill learned, every
reflection written, every parameter shift is committed to disk,
human-readable, and reproducible in one command.

**Concrete use case — art education.** A teacher loads a masterwork
from `targets/masterworks/`, clicks Paint, and the class watches the
agent build the image stroke by stroke on the browser canvas. Each
phase (underpaint, edges, fill, contours, highlights) is narrated by
the agent's own journal; students can open `skills/` to see which
techniques the agent has accumulated over prior sessions and read the
first-person `style/signature.md` to understand how its voice evolves.
Unlike a black-box image generator, every choice is inspectable — and
every student critique can target a specific skill file, a specific
phase, or a specific stroke.

An agent paints on a 512×512 HTML canvas stroke by stroke. After each
run it writes a reflection; a `skill_promote` pass distills recurring
patterns into skills with numeric parameter deltas; on the next run those
deltas sum and shift the pipeline's actual emission. You can watch the
arc happen and verify the mechanism at every step.

**The agent that paints is the CLI itself** — Claude Code, Hermes, or any
LLM driving the conversation. There is no second LLM inside this repo and
no API key required. Python only provides the canvas infrastructure, the
critic, and a tool server the CLI drives.

Submitted to the **Hermes Agent Creative Hackathon** (Kimi / NousResearch,
Apr 2026) — Creative Software track.

## Reproduce the memory arc in one command

```bash
make install-pil              # ~30 s, no browser needed for this path
python scripts/demo_memory_arc.py
```

The memory arc renders via PIL (the demo spawns its isolated viewer
with `--renderer pil`), so you can skip the ~200 MB Chromium download.
If you also want the live browser viewer later (for `make demo` or
`make judge-demo`), run `make install` instead — same flow, with
Playwright + Chromium added on top.

> **Always run judged commands through `.venv` or `make`.** The repo's
> declared dependencies (`scikit-image`, `pillow`, `playwright`) are
> installed into the venv, not your system Python. Running bare
> `python`/`pytest` outside `.venv` will hit `ModuleNotFoundError`.

That command spins up an **isolated sandbox** (no mutation of your real
`skills/` library), runs one cold paint with `apply_feedback=False` on
`targets/masterworks/great_wave.jpg`, then 5 priming paints on
feature-nearest same-image-type neighbors, runs `skill_promote` to
distill the reflections into skills, and finally re-paints the same
target with the promoted skills applied. The three canvases + a
side-by-side composite + a machine-readable summary all land in
`gallery/learning/<timestamp>/`:

- `run_cold.png` · `run_primed.png` · `side_by_side.png`
- `summary.json` — SSIMs, applied skills per run, effective parameter deltas, timings

Run takes **~5–7 min** on the default target (`great_wave.jpg`), much
less on simpler targets like `rothko_purple_white_red.jpg`.
`python scripts/demo_memory_arc.py --help` for
`--target / --style-mode / --seed / --priming` overrides.

### Under the hood — the dimensional-effects feedback loop

The side-by-side below is a real, unedited `scripts/demo_memory_arc.py`
output — the same command anyone cloning the repo can reproduce:

![learning arc](./gallery/learning/side_by_side.png)

| run | priming runs | applied skills | contrast_boost | **SSIM** | strokes |
|---|---:|---:|---:|:---:|---:|
| **cold** | 0 | 0 | 0.25 (default) | **0.2974** | 2 326 |
| **primed** | 5 | 1 | 0.28 (+0.03) | **0.2993** | 2 326 |

**What the mechanism actually did** (from `gallery/learning/summary.json`):

- **5 reflections written** into the sandbox during priming (one per
  target: warhol_marilyn, rothko_purple_white_red, the_bedroom,
  okeeffe_blue_green_music, american_gothic — the feature-nearest
  neighbors of great_wave in the `balanced` image_type bucket).
- **3 skills promoted** by `skill_promote`:
  `promoted_style_mode_van_gogh`, `promoted_image_type_balanced`,
  `promoted_saliency_mask`.
- **1 skill applied** to the primed paint:
  `promoted_image_type_balanced` (the only one whose scope matches
  great_wave's detected image_type). Its `dimensional_effects` added
  `contrast_boost: +0.03` to the pipeline's baseline.
- **Pipeline parameters observably shifted.** Cold's `effective_params`
  was `{}` (skill-feedback path skipped with `apply_feedback=False`);
  primed's `effective_params` carried `contrast_boost=0.28`,
  `complementary_shadow=0.12`, `style_mode=van_gogh`, plus the
  provenance `deltas: {contrast_boost: +0.03}` — traceable all the way
  back to the applied skill file in `sandbox/skills/`.
- **SSIM delta +0.0019**, small but consistently positive at this seed.
  The canvases are byte-level different (different contrast bias yields
  different color sampling) even where phase-level stroke counts match.

Not a dramatic cherry-picked leap: the memory arc is **gradual by
design**, and what this run proves is that the whole mechanism ran
end-to-end without the caller asking for anything beyond the target.
All artifacts are committed to disk in the sandbox and reproducible via
`python scripts/demo_memory_arc.py --seed 7`.

## Gallery — single paints, varied styles

<p align="center">
  <img src="./gallery/viewer_ui.png" width="720" alt="Live viewer in its atelier layout: the current canvas sits on an easel, the target hangs on the studio wall, a palette and brushes frame the scene. Controls below: test images, upload, style presets, paint/morph/duet, and dimensional-effects sliders."/>
  <br/>
  <sub><i>The atelier-styled live viewer. Canvas on the easel fills in stroke by stroke against the target on the wall. Sidebar: test images, style presets, paint/morph/duet controls, and the dimensional-effects sliders that skills bias. Right rail: iteration history, replay, and compare.</i></sub>
</p>

Produced by `scripts/gallery_build.py` against the `targets/masterworks/`
set on 2026-04-22 (Apple M-series, headless Chromium, seed=42).

| Target | Painted | Style | SSIM · strokes · time |
|---|---|---|---|
| ![](./gallery/great_wave_default_target.jpg) | ![](./gallery/great_wave_default.png) | default | 0.281 · 2 743 · 6.3 s |
| ![](./gallery/the_bedroom_van_gogh_target.jpg) | ![](./gallery/the_bedroom_van_gogh.png) | van_gogh | 0.238 · 2 543 · 3.2 s |
| ![](./gallery/caravaggio_tenebrism_target.jpg) | ![](./gallery/caravaggio_tenebrism.png) | tenebrism | 0.269 · 4 525 · 6.6 s |
| ![](./gallery/seurat_pointillism_target.jpg) | ![](./gallery/seurat_pointillism.png) | pointillism | 0.296 · 12 288 · 2.0 s |

Raw metrics in `gallery/summary.json`. SSIM numbers are the compass, not the
goal — the scores above are representative of the 8-phase pipeline at its
current baseline.

## Architecture

```
 ┌──────────────────┐                         ┌─────────────────┐
 │ CLI agent        │    JSON tool calls      │  hermes_tools   │
 │ (Claude Code /   │────────────────────────▶│  :8765          │
 │  Hermes /        │                         │                 │
 │  you by hand)    │                         └────────┬────────┘
 └──────────────────┘                                  │
                                                       ▼
                                                ┌──────────────┐
                                                │ viewer :8080 │──▶ canvas
                                                │              │◀── screenshot
                                                └──────────────┘
                                                       │
                                                       ▼
                                  skills/ • journal.jsonl • style/
```

- `scripts/viewer.py` → the canvas (Playwright + HTML) with a human UI and HTTP API on `:8080`
- `scripts/hermes_tools.py` → 49 JSON tools for an external agent on `:8765` (`curl localhost:8765/tool/manifest`)
- `scripts/paint_lib/` → the reusable multi-phase `auto_paint` pipeline (phases split under `phases_pkg/`); also exposes `paint_duet` and the morph scheduler
- All of `src/painter/*.py` → shared infrastructure (renderer, critic, skills, journal, style)
- `tests/test_renderer_parity.py` → pixel-MAE check across 12 stroke fixtures between `local_renderer.py` and `canvas/index.html`

> **Single-session architecture.** The viewer is a `ThreadingHTTPServer`
> with a single global `STATE` dict, guarded by a `threading.Lock` for
> paint-job entry and canvas mutations. That is sufficient for one local
> session at a time — the intended model. Running two concurrent paint
> sessions against the same viewer is not supported; use the memory-arc
> demo's alt-port pattern (`--viewer-port`, `--tools-port`) if you need
> an isolated second stack on the same machine.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium

make demo   # starts viewer :8080 + tool server :8765 + opens the UI
```

No `make`? Same thing by hand:

```bash
PYTHONPATH=src .venv/bin/python scripts/viewer.py &        # canvas :8080
PYTHONPATH=src .venv/bin/python scripts/hermes_tools.py &  # tools  :8765
open http://127.0.0.1:8080
```

Both servers bind to `127.0.0.1` by default — the tool layer reads
arbitrary files via `load_target`, so don't expose them publicly.

## Demo: run it with `hermes` in 30 seconds

This repo ships with an [`AGENTS.md`](./AGENTS.md) that Hermes (the
Nous Research CLI agent) reads automatically on session start. Pick
any of these one-liners and watch the agent work:

```bash
hermes "Paint targets/masterworks/the_bedroom.jpg in van_gogh style. \
        Dump the final canvas and describe what you painted."
```

```bash
hermes "Load targets/masterworks/caravaggio_resurrection.jpg. Call \
        plan_style_schedule and tell me the rationale. Then auto_paint \
        the target with that schedule and report the final SSIM."
```

```bash
hermes "Run a paint_duet on targets/masterworks/mona_lisa.jpg with \
        personas van_gogh_voice and tenebrist_voice, max_turns=4. \
        Summarize each turn's SSIM delta."
```

```bash
hermes "Paint targets/masterworks/great_wave.jpg with auto_paint. Then \
        read skills/ and journal.jsonl. Paint it a second time. Tell \
        me which skills fired and what changed between the two canvases."
```

```bash
hermes "Load targets/masterworks/seurat_grande_jatte.jpg. Plan and \
        draw 4 iterations of strokes stroke-by-stroke (no auto_paint) \
        via the score_plan / draw_strokes imagination loop. Save a \
        reflection at the end."
```

The human opens `http://127.0.0.1:8080` to watch strokes land in real
time. Click the easel canvas in the viewer to zoom in at native 512×512
resolution. See [`AGENTS.md`](./AGENTS.md) for the agent runbook and
[`HERMES.md`](./HERMES.md) for the full agent playbook.

---

## Also explored (experimental, built on the same substrate)

Two experimental directions that build on the memory-arc pipeline. They
are **supporting evidence**, not the flagship — the main story above is
what this project is about.

### Style morph (experimental)

The Hermes agent can plan a *morph* between two styles for a run, via the
`plan_style_schedule` tool. The canvas starts in one style and drifts
into another across the 8-phase pipeline — Phase 1 interleaves strokes
from both generators, Phases 2-8 interpolate style parameters
continuously.

<p align="center">
  <img src="./gallery/morph/morph_live.gif" width="384" alt="Live morph paint: The Great Wave painted van_gogh → pointillism across 5 iterations."/>
  <br/>
  <sub><i>Live iteration replay: <code>great_wave.jpg</code> painted <code>van_gogh → pointillism</code>.</i></sub>
</p>

Three demo rows, each shown next to a uniform-end control:

| Target | Morph output | Uniform-end control | Schedule |
|---|---|---|---|
| `caravaggio_resurrection` | ![](./gallery/morph/caravaggio_van_gogh_to_tenebrism.png) | ![](./gallery/morph/caravaggio_van_gogh_to_tenebrism_uniform.png) | `van_gogh → tenebrism` |
| `mona_lisa` | ![](./gallery/morph/mona_lisa_van_gogh_to_tenebrism.png) | ![](./gallery/morph/mona_lisa_van_gogh_to_tenebrism_uniform.png) | `van_gogh → tenebrism` |
| `great_wave` | ![](./gallery/morph/great_wave_van_gogh_to_pointillism.png) | ![](./gallery/morph/great_wave_van_gogh_to_pointillism_uniform.png) | `van_gogh → pointillism` |

Full rationales in [`gallery/morph/rationales.md`](./gallery/morph/rationales.md).

### Collaborative duet (experimental)

Two named *painter personas* alternate critique-and-correct turns on one
canvas. Each persona has a `style_mode`, a weighted list of failure
detectors, and a taste filter that picks which worst-cells it has
"legitimate claim" to correct. Turns are rejected on SSIM regression, so
the dialogue is committed to the journal honestly.

<p align="center">
  <img src="./gallery/duet/mona_lisa_vangogh_vs_tenebrist/turn_strip.png" width="720" alt="Three turns of a duet on Mona Lisa."/>
  <br/>
  <sub><i>Three turns of a duet on Mona Lisa: <code>van_gogh_voice</code> × <code>tenebrist_voice</code>. Panel 1 is the van_gogh opening; panels 2–3 alternate corrections.</i></sub>
</p>

Three demo duets, each shown next to its solo-opening control:

| Target | Duet | Solo control | Personas | Journal |
|---|---|---|---|---|
| `mona_lisa` | ![](./gallery/duet/mona_lisa_vangogh_vs_tenebrist/canvas.png) | ![](./gallery/duet/mona_lisa_vangogh_vs_tenebrist/control.png) | `van_gogh_voice × tenebrist_voice` | [📝](./gallery/duet/mona_lisa_vangogh_vs_tenebrist/duet_journal.md) |
| `great_wave` | ![](./gallery/duet/great_wave_vangogh_vs_pointillist/canvas.png) | ![](./gallery/duet/great_wave_vangogh_vs_pointillist/control.png) | `van_gogh_voice × pointillist_voice` | [📝](./gallery/duet/great_wave_vangogh_vs_pointillist/duet_journal.md) |
| `caravaggio` | ![](./gallery/duet/caravaggio_tenebrist_vs_vangogh/canvas.png) | ![](./gallery/duet/caravaggio_tenebrist_vs_vangogh/control.png) | `tenebrist_voice × van_gogh_voice` | [📝](./gallery/duet/caravaggio_tenebrist_vs_vangogh/duet_journal.md) |

New tools in the manifest: `paint_duet`, `list_personas`.
Persona library: [`personas/README.md`](./personas/README.md).

---

## Deep dive

The details below stay compact. Each link points at the source of truth
for anyone who wants to inspect a specific subsystem — the README is
not the place to duplicate what's already live in a tool manifest, a
module docstring, or a test file.

### The agent's loop

`load_target → analyze_target → list_skills → (get_regions → score_plan
→ snapshot → draw_strokes → dump_canvas + Read → restore_if_bad) ×
iterate → save_skill + save_journal_entry`. Full annotated sequence,
including the 8-phase `auto_paint` pipeline (underpainting → fog →
edges → gap-fill → mid/fine detail → contours → highlights →
critique-correct), lives in [`HERMES.md`](./HERMES.md).

### Tool manifest (49 tools)

The tool server ships a live, machine-readable manifest — always
authoritative, never drifts from code:

```bash
curl localhost:8765/tool/manifest
```

Categories: canvas I/O (`draw_strokes`, `score_plan`, `snapshot`,
`restore`), visual inspection (`dump_canvas`, `dump_heatmap`,
`get_regions`, `sample_target`), target analysis (`analyze_target`,
`saliency_mask`, `segment_regions`), stroke planners
(`edge_stroke_plan`, `detail_stroke_plan`, `contour_stroke_plan`,
`highlight_stroke_plan`), agent memory (`list_skills`, `save_skill`,
`list_journal`, `record_reflection`, `skill_promote`, `read_style`,
`update_style`). Duet + morph: `paint_duet`, `list_personas`,
`plan_style_schedule`.

### Stroke vocabulary

11 types — `fill_rect`, `fill_circle`, `fill_poly`, `line`, `polyline`,
`bezier`, `brush` (smooth or bristle), `dab`, `splat`, `fog`, `glow` —
mirrored byte-for-byte between `canvas/index.html` (browser) and
`src/painter/local_renderer.py` (PIL). Parity enforced by
[`tests/test_renderer_parity.py`](./tests/test_renderer_parity.py).
All strokes: 512×512 canvas, `#RRGGBB` colors, optional `alpha` (0–1).

### Skills (YAML frontmatter)

Each skill is a markdown file with frontmatter: `scope.image_types`,
`tags`, `confidence`, `provenance`, and optional `dimensional_effects`
that sum numeric deltas into the pipeline (`contrast_boost`,
`critique_rounds`, `painterly_details_bias`, per-style biases).
`src/painter/skills.py` is the loader; it scope-filters at load time
and caps the full library at 6 KB of prompt context. Examples:
[`skills/*.md`](./skills).

### Viewer HTTP API (port 8080)

15 endpoints covering state, paint orchestration, plan scoring,
snapshot/restore, target upload, heatmap, and the iteration replay.
Full contract lives in the module docstring at the top of
[`scripts/viewer.py`](./scripts/viewer.py). The tool server on :8765
proxies most of these for agent callers; the viewer is directly
usable if you prefer a thinner bridge.

## Project docs

| File | What's in it |
|---|---|
| [`HERMES.md`](./HERMES.md) | Full agent playbook — loop, 8-phase pipeline, anti-patterns, design philosophy, style-signature semantics |
| [`AGENTS.md`](./AGENTS.md) | One-page runbook for Hermes / Claude Code, with paste-ready prompts |
| [`CHANGELOG.md`](./CHANGELOG.md) | Distilled version history |
| [`skills/style/signature.md`](./skills/style/signature.md) | The painter's first-person style essay — it rewrites this itself |
| [`skills/*.md`](./skills) | YAML-frontmatter skill library, scope-filtered at load time |
