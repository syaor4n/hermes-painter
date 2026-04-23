# AGENTS.md — Hermes Painter

**You (the CLI agent) are the painter.** Python provides the canvas
infrastructure and a 49-tool HTTP server; every stroke plan comes from you.

---

## 90-second setup

```bash
make demo           # starts viewer :8080 + tool server :8765
```

If you don't have `make`, do it yourself:

```bash
PYTHONPATH=src .venv/bin/python scripts/viewer.py &       # canvas on :8080
PYTHONPATH=src .venv/bin/python scripts/hermes_tools.py & # tools  on :8765
```

The human opens `http://127.0.0.1:8080` to watch. You drive via POSTs to
`http://127.0.0.1:8765/tool/<name>` (use your `terminal` tool or any HTTP
helper). `GET /tool/manifest` returns all 49 tool schemas.

---

## Demo prompts (copy-paste one of these as a starting point)

Pick one. Each exercises a different headline feature.

### 1. Baseline stylize — "paint this in Van Gogh"

> Paint `targets/masterworks/the_bedroom.jpg` in van_gogh style using
> `auto_paint`. When done, dump the canvas and describe what you see.

### 2. Agent-planned morph — "the planner picks two styles for me"

> Load `targets/masterworks/caravaggio_resurrection.jpg`. Call
> `plan_style_schedule` and tell me the planner's rationale. Then
> `auto_paint` the target with that schedule and report the final SSIM.

### 3. Collaborative duet — "two personas alternate"

> Run a duet on `targets/masterworks/mona_lisa.jpg` with personas
> `van_gogh_voice` and `tenebrist_voice`, max_turns=4. Summarize each
> turn's delta and the final SSIM.

### 4. Learning arc — "memory actually changes behavior"

> Paint `targets/masterworks/great_wave.jpg` once with `auto_paint`.
> Read `skills/` and `journal.jsonl`. Paint the same target again and
> tell me which skills fired and what changed between the two canvases.

### 5. Fully agent-driven (no auto_paint) — "plan strokes yourself"

> Load `targets/masterworks/seurat_grande_jatte.jpg`. Analyze it. Plan
> and draw 4 iterations of strokes stroke-by-stroke — NOT via
> `auto_paint` — using the `score_plan` / `draw_strokes` loop. Save a
> reflection at the end.

---

## Orientation (before your first stroke)

Before picking up any brush, read these in order:

1. **`HERMES.md`** — the full agent playbook: every tool grouped by
   purpose, the imagination-first loop, stroke vocabulary, style/skill
   conventions.
2. **`skills/style/signature.md`** — your persistent style (read it,
   update it when you change your approach).
3. **Last ~5 entries of `journal.jsonl`** — what recent runs learned.

## Shipped features you should know about

- **8-phase `auto_paint` pipeline** (the baseline). Style personality
  chooses the look: `default / van_gogh / tenebrism / pointillism /
  engraving / lumiere_doree`.
- **Style morph** (`plan_style_schedule` + `style_schedule` kwarg) —
  the painter starts in one style and blends to another across phases.
- **Collaborative duet** (`paint_duet` + `list_personas`) — two named
  painter personas alternate critique-and-correct turns on one canvas.
- **Dimensional-effects feedback loop** — promoted skills under
  `skills/promoted_*.md` carry numeric parameter deltas that shift the
  next paint's default behavior. The more you paint, the more the
  pipeline drifts toward what worked.
- **Community styles + personas** — drop a `styles/<name>/style.yaml` or
  `personas/<name>/persona.yaml` (PERSONAS_PATH) and they're picked up
  automatically.
- **Viewer UI with canvas zoom** — humans click the easel canvas to
  watch strokes appear at full 512×512 detail while you paint.

## What NOT to do

- Don't call `curl` in scripts — your `terminal` tool runs shell commands
  directly. The only HTTP pattern you need is a POST with a JSON body to
  `http://127.0.0.1:8765/tool/<name>`.
- Don't `draw_strokes` without a `score_plan` first (except inside
  `auto_paint`, which already does this). Imagination is free; applied
  strokes commit the canvas.
- Don't skip `dump_canvas → Read`. SSIM can't tell you if the painting
  is recognizable as its subject. Your eyes can.

## Troubleshooting

- **`ViewerUnavailable` on any tool call** — viewer isn't up. Run
  `make demo` or start `scripts/viewer.py` manually.
- **`tool server not reachable`** — tool server isn't up. Start
  `scripts/hermes_tools.py`.
- **Paint completes but canvas looks empty** — probably no target
  loaded. Call `load_target({"path": "targets/..."})` first.

## One more thing

`HERMES.md` is the long-form briefing. This file is the speed-dial. If
you've never painted on this canvas before, read `HERMES.md` once. If
you have, come straight here and pick a demo prompt.
