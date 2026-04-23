# Community Styles

This directory holds community-contributed parameter-only styles for Hermes Painter.
Each style lives in its own subdirectory and is loaded automatically at import time
alongside the 5 built-in styles.

---

## Directory layout

```
styles/
  lumiere_doree/
    style.yaml        # required — metadata + parameter vector
  your_style_name/
    style.yaml
```

One directory per style. The directory name does not have to match `name` in
`style.yaml`, but keeping them identical avoids confusion.

---

## `style.yaml` schema

```yaml
format_version: 1             # integer, must be 1
name: your_style_name         # string, non-empty; must not shadow a built-in
author: your-handle           # string
license: CC0-1.0              # SPDX identifier
description: >
  One or two sentences describing the look and best use cases.
extends: default              # built-in generator to inherit (see below)
parameters:
  contrast_boost:         0.25   # float, see valid ranges below
  complementary_shadow:   0.12
  painterly_details_bias: 0.0
  van_gogh_bias:          0.0
  tenebrism_bias:         0.0
  pointillism_bias:       0.0
  engraving_bias:         0.0
```

All seven `parameters` keys are **required**. A missing key causes the style to be
skipped with a `[morph]` warning printed to stderr.

---

## Parameter valid ranges

Ranges come from `EFFECT_LIMITS` in `src/painter/skills.py`.

| Parameter | Min | Max | Effect |
|---|---|---|---|
| `contrast_boost` | 0.0 | 0.5 | S-curve contrast push in the underpainting |
| `complementary_shadow` | 0.0 | 0.3 | Complementary-hue tint in shadow regions |
| `painterly_details_bias` | 0.0 | 1.0 | Expressive detail brushwork intensity |
| `van_gogh_bias` | 0.0 | 1.0 | Swirling directional stroke character |
| `tenebrism_bias` | 0.0 | 1.0 | Rembrandt-style dark-field dramatic contrast |
| `pointillism_bias` | 0.0 | 1.0 | Dot / dab texture substituting brush strokes |
| `engraving_bias` | 0.0 | 1.0 | Cross-hatch engraving line character |

Values are linearly blended during a morph run — keep them within their ranges
or they will be clamped by `painter.skills.clamp_effect` at blend time.

---

## The `extends` field

`extends` names the built-in style whose **underpainting generator** is inherited.
A parameter-only community style has no code of its own; it borrows the generator
of an existing built-in and runs it with a different parameter vector.

Valid values for `extends`:

| Name | Generator | Character |
|---|---|---|
| `default` | `layered_underpainting` | Neutral multi-layer base |
| `van_gogh` | `van_gogh_underpainting` | Swirling expressive strokes |
| `tenebrism` | `tenebrism_underpainting` | Dark-field selective light |
| `pointillism` | `pointillism_underpainting` | Dense dot / dab patterns |
| `engraving` | `engraving_underpainting` | Parallel hatch lines |

If you want a warm-palette style that still lays down a solid neutral base,
use `extends: default` (as `lumiere_doree` does). If you want the swirling
stroke character of van Gogh with a different colour temperature, use
`extends: van_gogh`.

---

## v1 limitation: no Python generator files

**Python `generator.py` files are NOT supported in v1** (trust-model reasons —
see spec §8.3). Dropping a `generator.py` next to `style.yaml` has no effect;
only the `style.yaml` parameters are read. Full code-style plugins are planned
for v2.

---

## Contributing a new style (PR workflow)

1. Fork the repository.
2. Create `styles/<your_style_name>/style.yaml` following the schema above.
3. Verify locally:
   ```bash
   .venv/bin/python -c "
   from paint_lib import morph
   print('your_style_name' in morph.STYLE_DEFAULTS)
   "
   ```
4. Run the test suite:
   ```bash
   .venv/bin/pytest tests/test_community_styles.py tests/test_morph.py -v
   ```
5. Open a PR with the title `feat(styles): add <your_style_name>`.

The `STYLES_PATH` environment variable (colon-separated directory list) lets you
test local additions without forking:

```bash
STYLES_PATH=/path/to/my/local/styles .venv/bin/python -c \
  "from paint_lib import morph; print(sorted(morph.STYLE_DEFAULTS))"
```
