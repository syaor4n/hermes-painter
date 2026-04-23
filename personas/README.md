# Personas

A *persona* is a painter voice: a named style preference plus a weighted set
of failure modes it "cares about" plus a correction budget. Two personas
alternate turns in `paint_duet` to produce a collaborative canvas.

## Layout

```
personas/
├── van_gogh_voice/
│   └── persona.yaml          ← the only required file
├── tenebrist_voice/
│   └── persona.yaml
└── your_voice_here/
    └── persona.yaml
```

Each persona lives in its own subdirectory. The subdirectory name is
conventional — only `persona.yaml::name` is authoritative.

## `persona.yaml` schema

```yaml
format_version: 1              # required; must equal 1
name: my_voice                 # required; [a-z][a-z0-9_]+, must not collide
                               #   with a built-in persona
style_mode: van_gogh           # required; must resolve to a registered style
                               #   (built-in or community, see styles/README.md)

author: your-github-handle     # optional
description: >                 # optional; one paragraph
  What this voice cares about and what it avoids.

signature_essay: |             # optional; first-person aesthetic statement
  Two or three sentences in this painter's voice. Not parsed — pure
  descriptive text surfaced in list_personas output.

skills_tags: [tag1, tag2]      # optional; filter when reading the skills/
                               #   library during this persona's turn

cares_about:                   # optional; weights on failure-detector modes
  MUDDY_UNDERPAINT: 1.0        # (0.0 — ignore, 2.0 — always attend to)
  TOO_DARK_OUTLINES: 1.0

correction_budget:             # optional; every field has a sensible default
  max_cells_per_turn: 6        # how many cells this persona edits per turn [1, 20]
  stroke_width: 3              # brush width for sculpt_correction_plan
  alpha: 0.55                  # blend strength [0.0, 1.0]
  avoid_cells_painted_by_other: true  # don't overwrite the other persona's cells
```

## Minimum viable persona

```yaml
format_version: 1
name: minimalist_voice
style_mode: default
```

Every other field has a default.

## Valid failure modes (for `cares_about`)

These are the `src/painter/failures.py` detector names. Unknown names cause
the loader to reject the persona (with a `[duet]` warning to stderr).

- `TOO_DARK_OUTLINES`
- `SUBJECT_LOST_IN_BG`
- `MUDDY_UNDERPAINT`
- `OVER_RENDERED_BG`
- `UNDER_COVERED`
- `OVER_RENDERED_FG`
- `HARD_BANDING`
- `DIRECTION_MISMATCH`

## Registering a persona

1. Fork the repo.
2. Create `personas/<your_voice>/persona.yaml` following the schema above.
3. Test it loads:
   ```bash
   .venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); \
     from paint_lib.duet import PERSONAS; \
     assert '<your_voice>' in PERSONAS"
   ```
4. Test it pairs with a built-in:
   ```bash
   .venv/bin/python scripts/duet.py targets/masterworks/great_wave.jpg \
       --personas <your_voice>,tenebrist_voice --max-turns 6
   ```
5. Open a PR. Include a sample `gallery/duet/<slug>/` run if you want us
   to feature your persona in the README.

## Local-only personas

Set `PERSONAS_PATH` to point at extra directories, colon-separated:

```bash
export PERSONAS_PATH=~/my-personas:/opt/shared/personas
```

The loader scans each listed directory for `<name>/persona.yaml` in addition
to the `personas/` directory in this repo.

## What's NOT supported (v1)

- **Python `generator.py` files.** Personas reuse the generator of their
  declared `style_mode`. If you want truly custom strokes, first ship a
  community style (see `styles/README.md`) and reference it as your
  persona's `style_mode`.
- **Shadowing built-ins.** A community persona with the same `name` as a
  shipped one is rejected — fork the repo to edit a built-in.
- **More than 2 personas per duet.** `paint_duet` takes exactly 2 for v1.

## Further reading

- Design spec: `docs/superpowers/specs/2026-04-22-collaborative-painters-design.md`
- Styles guide: `styles/README.md`
- Tool reference: `GET http://localhost:8765/tool/manifest` (run `hermes_tools.py` first)
