"""Real-time style morphing — pure functions + registries.

See docs/superpowers/specs/2026-04-22-real-time-style-morphing-design.md
for the full design. This module is the single place that knows
(a) what parameter vector each style represents (STYLE_DEFAULTS),
(b) which underpainting function each style dispatches to (STYLE_DISPATCH),
(c) how two styles blend at a given t (blend_params, interleave_strokes),
(d) what "a valid schedule" looks like (validate_schedule).

The pipeline imports from here; it does not duplicate the tables.

Community styles (§8 of the design spec) are loaded at import time from
  <repo>/styles/*/style.yaml
and from any colon-separated directories listed in the STYLES_PATH env var.
Each style.yaml must have format_version=1, a non-empty name, and an extends
field that names a built-in style. Parameter-only styles are safe by default;
code-style plugins (generator.py) are v2 per spec §8.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable
import random

from .styles import (
    engraving_underpainting,
    layered_underpainting,
    pointillism_underpainting,
    tenebrism_underpainting,
    van_gogh_underpainting,
)


# --- Per-style parameter vectors ---------------------------------------
# Values extracted from inspection of scripts/paint_lib/pipeline.py
# lines 135-151 (complementary_shadow style overrides) and from the
# current style_mode branches. Keep these synchronized with the
# pipeline's hard-coded behavior until a follow-up PR replaces the
# scattered literals with lookups here.

STYLE_DEFAULTS: dict[str, dict[str, float]] = {
    "default": {
        "contrast_boost":         0.25,
        "complementary_shadow":   0.12,
        "painterly_details_bias": 0.0,
        "van_gogh_bias":          0.0,
        "tenebrism_bias":         0.0,
        "pointillism_bias":       0.0,
        "engraving_bias":         0.0,
    },
    "van_gogh": {
        "contrast_boost":         0.30,
        "complementary_shadow":   0.18,
        "painterly_details_bias": 0.8,
        "van_gogh_bias":          1.0,
        "tenebrism_bias":         0.0,
        "pointillism_bias":       0.0,
        "engraving_bias":         0.0,
    },
    "tenebrism": {
        "contrast_boost":         0.45,
        "complementary_shadow":   0.0,
        "painterly_details_bias": 0.3,
        "van_gogh_bias":          0.0,
        "tenebrism_bias":         1.0,
        "pointillism_bias":       0.0,
        "engraving_bias":         0.0,
    },
    "pointillism": {
        "contrast_boost":         0.20,
        "complementary_shadow":   0.20,
        "painterly_details_bias": 0.2,
        "van_gogh_bias":          0.0,
        "tenebrism_bias":         0.0,
        "pointillism_bias":       1.0,
        "engraving_bias":         0.0,
    },
    "engraving": {
        "contrast_boost":         0.35,
        "complementary_shadow":   0.0,
        "painterly_details_bias": 0.0,
        "van_gogh_bias":          0.0,
        "tenebrism_bias":         0.0,
        "pointillism_bias":       0.0,
        "engraving_bias":         1.0,
    },
}
"""Per-style parameter vectors — the single source of truth for how each
named style differs from the pipeline's defaults in its effect-channel
values. Consumed by blend_params (Task 2) and by pipeline parameter
merges (Task 6)."""


# --- Per-style underpainting dispatch ----------------------------------
# Every generator here must accept the same positional signature
#   (grid, cell_w, cell_h, **kwargs)
# and return a list of stroke dicts. Callers provide the grid from
# sample_grid(). The signatures in paint_lib/styles.py already conform
# modulo per-style kwargs the pipeline already knows how to pass.

STYLE_DISPATCH: dict[str, Callable[..., list[dict]]] = {
    "default":     layered_underpainting,
    "van_gogh":    van_gogh_underpainting,
    "tenebrism":   tenebrism_underpainting,
    "pointillism": pointillism_underpainting,
    "engraving":   engraving_underpainting,
}
"""Name → underpainting-generator dispatch table. Every generator accepts
(grid, cell_w, cell_h, **kwargs) and returns a list of stroke dicts.
New community styles (follow-up spec) plug in here."""


# --- Community-style loader -------------------------------------------
# Tiny YAML-subset parser: handles flat dicts with int/float/string/bool
# values and a single level of scalar nesting. No multi-document, no
# anchors, no block sequences (the style.yaml schema never uses them).

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
_FLOAT_SCI = re.compile(r"^-?\d+(\.\d+)?[eE][+-]?\d+$")

# Repo root is three levels above this file:
# scripts/paint_lib/morph.py  →  scripts/paint_lib  →  scripts  →  repo
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILTIN_NAMES = frozenset(STYLE_DISPATCH.keys())


def _yaml_coerce(s: str) -> Any:
    s = s.strip()
    if not s or s in ("null", "~", "Null", "NULL"):
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s) or _FLOAT_SCI.match(s):
        return float(s)
    # Strip surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse the subset of YAML used by style.yaml and persona.yaml files.

    Supports:
    - top-level scalar key: value
    - one-level nested block (for `parameters:`, `cares_about:`, etc., indented 2+ spaces)
    - one-level lists (e.g., `skills_tags: [a, b, c]`)
    - multi-line block scalar for `description` / `signature_essay` ('>'/`|`-style, collected as a string)

    Returns a flat dict. Keys with nested values map to nested dicts or lists.
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    collecting_scalar = False  # True when inside a '>' or '|' block scalar
    scalar_mode = ""  # ">" or "|"

    for line in text.splitlines():
        # Skip full-line comments and empty lines (but not inside nested blocks)
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            if collecting_scalar:
                collecting_scalar = False
            current_key = None
            continue

        indent = len(line) - len(line.lstrip())

        # Inside block scalar: accumulate lines
        if collecting_scalar and current_key:
            if indent >= 2 or (scalar_mode == "|" and stripped):
                # Continuation of block scalar
                if result[current_key]:
                    result[current_key] += "\n"
                result[current_key] += stripped
                continue
            else:
                # End of block scalar
                collecting_scalar = False
                scalar_mode = ""

        # Nested line under current_key (indented ≥ 2)
        if indent >= 2 and current_key is not None and not collecting_scalar:
            sub = stripped.strip()
            if ":" not in sub:
                continue
            k, _, v = sub.partition(":")
            k = k.strip()
            v = v.strip()
            if not isinstance(result.get(current_key), dict):
                result[current_key] = {}
            # Parse nested value: handle inline lists
            if v.startswith("[") and v.endswith("]"):
                # Inline list: [a, b, c]
                items_str = v[1:-1]
                items = [_yaml_coerce(x.strip()) for x in items_str.split(",") if x.strip()]
                result[current_key][k] = items
            else:
                result[current_key][k] = _yaml_coerce(v) if v else None
            continue

        # Reset nesting when we return to top level
        if indent == 0:
            collecting_scalar = False
            scalar_mode = ""

        if ":" not in stripped:
            continue

        k, _, v = stripped.partition(":")
        k = k.strip()
        v = v.strip()

        if v in (">", "|"):
            # Block scalar — collect continuation lines as a single string
            result[k] = ""
            current_key = k
            collecting_scalar = True
            scalar_mode = v
        elif not v:
            # Begin a nested mapping
            result[k] = {}
            current_key = k
            collecting_scalar = False
        elif v.startswith("[") and v.endswith("]"):
            # Inline list: [a, b, c]
            items_str = v[1:-1]
            items = [_yaml_coerce(x.strip()) for x in items_str.split(",") if x.strip()]
            result[k] = items
            current_key = None
            collecting_scalar = False
        else:
            result[k] = _yaml_coerce(v)
            current_key = None
            collecting_scalar = False

    return result


_REQUIRED_PARAM_KEYS = frozenset({
    "contrast_boost",
    "complementary_shadow",
    "painterly_details_bias",
    "van_gogh_bias",
    "tenebrism_bias",
    "pointillism_bias",
    "engraving_bias",
})


def _load_one_community_style(yaml_path: Path) -> None:
    """Parse a single style.yaml and register into STYLE_DEFAULTS + STYLE_DISPATCH.

    On any validation or parse failure: print a [morph] warning to stderr and
    return without touching the registries. Never raises.
    """
    try:
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        data = _parse_yaml(text)

        fmt = data.get("format_version")
        if fmt != 1:
            print(
                f"[morph] skipping {yaml_path}: format_version must be 1, got {fmt!r}",
                file=sys.stderr,
            )
            return

        name = data.get("name", "")
        if not isinstance(name, str) or not name.strip():
            print(
                f"[morph] skipping {yaml_path}: 'name' is missing or empty",
                file=sys.stderr,
            )
            return
        name = name.strip()

        extends = data.get("extends", "")
        if not isinstance(extends, str) or not extends.strip():
            print(
                f"[morph] skipping {yaml_path} ({name!r}): 'extends' is missing or empty",
                file=sys.stderr,
            )
            return
        extends = extends.strip()

        if extends not in _BUILTIN_NAMES:
            print(
                f"[morph] skipping {yaml_path} ({name!r}): "
                f"extends={extends!r} is not a known built-in "
                f"(known: {sorted(_BUILTIN_NAMES)})",
                file=sys.stderr,
            )
            return

        raw_params = data.get("parameters", {})
        if not isinstance(raw_params, dict):
            print(
                f"[morph] skipping {yaml_path} ({name!r}): 'parameters' must be a mapping",
                file=sys.stderr,
            )
            return

        params: dict[str, float] = {}
        for pk in _REQUIRED_PARAM_KEYS:
            raw_v = raw_params.get(pk)
            if raw_v is None:
                print(
                    f"[morph] skipping {yaml_path} ({name!r}): "
                    f"missing required parameter key {pk!r}",
                    file=sys.stderr,
                )
                return
            try:
                params[pk] = float(raw_v)
            except (TypeError, ValueError):
                print(
                    f"[morph] skipping {yaml_path} ({name!r}): "
                    f"parameter {pk!r} is not numeric: {raw_v!r}",
                    file=sys.stderr,
                )
                return

        # Guard: do NOT overwrite built-ins
        if name in _BUILTIN_NAMES:
            print(
                f"[morph] skipping {yaml_path}: "
                f"{name!r} shadows a built-in style — community styles cannot override built-ins",
                file=sys.stderr,
            )
            return

        STYLE_DEFAULTS[name] = params
        STYLE_DISPATCH[name] = STYLE_DISPATCH[extends]

    except Exception as exc:  # noqa: BLE001
        print(
            f"[morph] skipping {yaml_path}: unexpected error: {exc}",
            file=sys.stderr,
        )


def _scan_styles_dir(directory: Path) -> None:
    """Scan `directory/*/style.yaml` and register any valid community styles."""
    if not directory.is_dir():
        return
    for yaml_path in sorted(directory.glob("*/style.yaml")):
        _load_one_community_style(yaml_path)


def _load_community_styles() -> None:
    """Populate STYLE_DEFAULTS + STYLE_DISPATCH from the filesystem.

    Called once at module import time. Scans:
    1. <repo_root>/styles/*/style.yaml
    2. Each directory listed in STYLES_PATH (colon-separated)
    """
    _scan_styles_dir(_REPO_ROOT / "styles")

    styles_path_env = os.environ.get("STYLES_PATH", "")
    if styles_path_env:
        for extra in styles_path_env.split(":"):
            extra = extra.strip()
            if extra:
                _scan_styles_dir(Path(extra))


# Run the loader at import time so community styles are available everywhere.
_load_community_styles()


# --- Phase → t mapping -------------------------------------------------
# Ordered dict: the key names are logical phase labels the pipeline
# maps to. Values are linearly spaced 0 → 1 across 8 logical phases
# per the spec §4.4.

PHASE_T: dict[str, float] = {
    "underpaint":   0.00,
    "fog":          round(1 / 7, 4),    # 0.1429
    "edge":         round(2 / 7, 4),    # 0.2857
    "gap_detail":   round(3 / 7, 4),    # 0.4286
    "detail_fine":  round(4 / 7, 4),    # 0.5714
    "contour":      round(5 / 7, 4),    # 0.7143
    "highlight":    round(6 / 7, 4),    # 0.8571
    "finish":       1.00,
}
"""Logical-phase → blend-weight table. Consumed by pipeline.py to compute
t for interleave_strokes (Phase 1) and blend_params (Phases 2–8).
Monotonic 0.0 → 1.0 across exactly 8 phases per spec §4.4."""


# --- Validation --------------------------------------------------------

def validate_schedule(schedule: Any) -> None:
    """Raise ValueError if `schedule` is not a well-formed morph schedule.

    Mutates nothing. Called by auto_paint at the top of a run and by
    the tool-server handler before dispatch. Extra keys pass through
    (forward compatibility for a future `curve` or `phases` field).
    """
    if not isinstance(schedule, dict):
        raise ValueError(f"style_schedule must be a dict, got {type(schedule).__name__}")
    for key in ("start", "end"):
        if key not in schedule:
            raise ValueError(f"style_schedule missing required key: {key!r}")
        value = schedule[key]
        if value not in STYLE_DEFAULTS:
            raise ValueError(
                f"style_schedule[{key!r}]: unknown style {value!r} "
                f"(known: {sorted(STYLE_DEFAULTS)})"
            )


# Import lazily from the src tree so pure-python users don't trigger it
# unless they actually call blend_params. Top of a viewer-less test
# run should not need to import painter.skills.
def _clamp_effect(channel: str, value: float) -> float:
    """Delegate to painter.skills.clamp_effect; safe to call repeatedly."""
    try:
        from painter.skills import clamp_effect
        return clamp_effect(channel, value)
    except Exception:
        return value


def blend_params(start: str, end: str, t: float) -> dict[str, float]:
    """Linear interpolation between two style parameter vectors, clamped.

    Keys present in only one vector default to 0 in the other (so adding
    a new knob to one style doesn't silently zero it during a morph —
    it just fades in linearly as t moves away from the pole that lacks it).

    Returns a new dict; the inputs are not mutated.
    """
    if start not in STYLE_DEFAULTS:
        raise ValueError(f"unknown start style: {start!r}")
    if end not in STYLE_DEFAULTS:
        raise ValueError(f"unknown end style: {end!r}")
    A = STYLE_DEFAULTS[start]
    B = STYLE_DEFAULTS[end]
    keys = set(A) | set(B)
    out: dict[str, float] = {}
    for k in keys:
        v = (1.0 - t) * A.get(k, 0.0) + t * B.get(k, 0.0)
        out[k] = _clamp_effect(k, v)
    return out


def interleave_strokes(
    start_strokes: list[dict],
    end_strokes: list[dict],
    t: float,
    seed: int,
) -> list[dict]:
    """Mix two stroke lists at blend weight t ∈ [0, 1], deterministic by seed.

    Degenerate shortcuts:
      - t <= 0.0 returns a copy of start_strokes in original order
      - t >= 1.0 returns a copy of end_strokes in original order
    These preserve stroke order so the pixel-identity contract holds:
    running through the morph machinery with t=0 must yield the same
    canvas as not running the morph at all. Shuffling would reorder
    alpha layering.

    In the generic case, the total count is the weighted average of
    the two source counts (prevents one high-count style from swamping
    the other). Strokes are sampled without replacement from each
    source and shuffled together so neighbors blend on the canvas.
    """
    if t <= 0.0:
        return list(start_strokes)
    if t >= 1.0:
        return list(end_strokes)
    rng = random.Random(seed)
    total = round((1.0 - t) * len(start_strokes) + t * len(end_strokes))
    n_start = round(total * (1.0 - t))
    n_end = round(total * t)
    # Account for smaller-than-ideal source sizes: clamp and redistribute
    n_start = min(n_start, len(start_strokes))
    n_end = min(n_end, len(end_strokes))
    picked = (
        rng.sample(start_strokes, n_start)
        + rng.sample(end_strokes, n_end)
    )
    rng.shuffle(picked)
    return picked
