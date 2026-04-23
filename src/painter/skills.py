"""Skills v2 — markdown + YAML frontmatter + scope filter + confidence.

Legacy plain-markdown skills (no frontmatter) are still supported; they are
loaded as "universal" (apply to every image type).

Frontmatter example:

    ---
    scope:
      image_types: [portrait, landscape]
      exclude: [night]
    provenance:
      run: 20260420_162504_photo
      delta_ssim: 0.15
    confidence: 3
    tags: [underpainting, rembrandt]
    ---
    Body of the skill...
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILLS_DIR = Path(
    os.environ.get("PAINTER_SKILLS_DIR")
    or Path(__file__).resolve().parents[2] / "skills"
)

# Simple YAML subset parser (no deps). Supports:
#   key: value
#   key: [a, b, c]
#   key:
#     nested_key: value
#     nested_key: [a, b]
# Values are strings unless they look like ints, floats or bools.
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def _coerce(s: str) -> Any:
    s = s.strip()
    if not s:
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() in ("null", "none", "~"):
        return None
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _parse_list(s: str) -> list[Any]:
    inner = s.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1].strip()
    if not inner:
        return []
    return [_coerce(x) for x in inner.split(",")]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (metadata, body). If no frontmatter, metadata is {}."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")

    meta: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # Nested (2+ spaces indent, under current_key)
        if line.startswith("  ") and current_key:
            sub = line.strip()
            if ":" not in sub:
                continue
            k, _, v = sub.partition(":")
            k = k.strip()
            v = v.strip()
            if not isinstance(meta.get(current_key), dict):
                meta[current_key] = {}
            if v.startswith("["):
                meta[current_key][k] = _parse_list(v)
            else:
                meta[current_key][k] = _coerce(v) if v else {}
        else:
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            current_key = k
            if not v:
                meta[k] = {}
            elif v.startswith("["):
                meta[k] = _parse_list(v)
            else:
                meta[k] = _coerce(v)
                current_key = None
    return meta, body


@dataclass
class Skill:
    path: Path
    metadata: dict[str, Any]
    body: str

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def confidence(self) -> int:
        return int(self.metadata.get("confidence", 1) or 1)

    @property
    def scope_types(self) -> list[str]:
        return list((self.metadata.get("scope") or {}).get("image_types") or [])

    @property
    def exclude_types(self) -> list[str]:
        return list((self.metadata.get("scope") or {}).get("exclude") or [])

    @property
    def tags(self) -> list[str]:
        return list(self.metadata.get("tags") or [])

    @property
    def effects(self) -> dict[str, float]:
        """P0.1 — real feedback channel. A skill can declare `dimensional_effects`
        in its frontmatter. The values are summed across all applicable skills
        and applied as parameter deltas in auto_paint.
        """
        raw = self.metadata.get("dimensional_effects") or {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    def applies_to(self, image_type: str | None, *, tags: list[str] | None = None) -> bool:
        if image_type and self.exclude_types and image_type in self.exclude_types:
            return False
        if self.scope_types:
            if image_type is None or image_type not in self.scope_types:
                return False
        if tags:
            if not set(tags).intersection(self.tags or []):
                return False
        return True

    def as_prompt_fragment(self) -> str:
        tags_str = f" (tags: {', '.join(self.tags)})" if self.tags else ""
        return f"### {self.name}{tags_str}\n{self.body.strip()}"


def iter_skills(
    directory: Path | None = None,
    *,
    include_excluded_dirs: tuple[str, ...] = ("style", "legacy"),
) -> list[Skill]:
    directory = directory or SKILLS_DIR
    if not directory.exists():
        return []
    skills: list[Skill] = []
    for md in sorted(directory.rglob("*.md")):
        if md.name == "INDEX.md":
            continue
        # style/ and legacy/ are archive dirs; never surfaced to the agent
        if any(p in include_excluded_dirs for p in md.relative_to(directory).parts[:-1]):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        meta, body = _parse_frontmatter(text)
        skills.append(Skill(path=md, metadata=meta, body=body))
    return skills


# Legacy filenames that are per-run critiques, not reusable techniques.
# They are skipped when loading skills for a planner prompt.
_LEGACY_CRITIQUE_MARKERS = (
    "critique",
    "critic_results",
    "auto_paint_results",
    "final_results",
    "session",
    "latest_",
    "honest_",
    "self_critique",
    "expressionist_critique",
    "observation_style",
)


def _looks_like_run_critique(skill: Skill) -> bool:
    if skill.metadata:  # has frontmatter → intentionally written as a skill
        return False
    name = skill.name.lower()
    return any(m in name for m in _LEGACY_CRITIQUE_MARKERS)


def load_skills(
    image_type: str | None = None,
    *,
    tags: list[str] | None = None,
    min_confidence: int = 1,
    max_skills: int = 8,
    max_chars: int = 6000,
    per_skill_chars: int = 800,
) -> str:
    """Concatenate relevant skills into a single prompt-friendly block.

    Hard budget: `max_chars` total across all loaded skills, `per_skill_chars`
    per skill body. Legacy per-run critique files are filtered out.
    """
    all_skills = [s for s in iter_skills() if not _looks_like_run_critique(s)]
    matching = [
        s for s in all_skills
        if s.applies_to(image_type, tags=tags) and s.confidence >= min_confidence
    ]
    # Skills with frontmatter sort higher; break ties by confidence then name
    matching.sort(
        key=lambda s: (0 if s.metadata else 1, -s.confidence, s.name)
    )
    if max_skills:
        matching = matching[:max_skills]
    if not matching:
        return ""
    fragments: list[str] = []
    total = 0
    for s in matching:
        body = s.body.strip()
        if len(body) > per_skill_chars:
            body = body[:per_skill_chars].rstrip() + " …"
        tags_str = f" (tags: {', '.join(s.tags)})" if s.tags else ""
        frag = f"### {s.name}{tags_str}\n{body}"
        if total + len(frag) > max_chars:
            break
        fragments.append(frag)
        total += len(frag) + 2
    return "\n\n".join(fragments)


def load_style(signature_path: Path | None = None) -> str:
    """Return the painter's style signature, or '' if not written yet."""
    p = signature_path or (SKILLS_DIR / "style" / "signature.md")
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    _, body = _parse_frontmatter(text)
    return body.strip()


def _to_yaml(meta: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    for k, v in meta.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(_to_yaml(v, indent + 1))
        elif isinstance(v, list):
            if v:
                rendered = ", ".join(repr(x) if isinstance(x, str) else str(x) for x in v)
                lines.append(f"{pad}{k}: [{rendered}]")
            else:
                lines.append(f"{pad}{k}: []")
        elif isinstance(v, bool):
            lines.append(f"{pad}{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{pad}{k}: null")
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)


def write_skill(
    name: str,
    body: str,
    *,
    scope_types: list[str] | None = None,
    exclude_types: list[str] | None = None,
    tags: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
    confidence: int = 1,
    dimensional_effects: dict[str, float] | None = None,
) -> Path:
    """Write a new skill file with full frontmatter.

    dimensional_effects: P0.1 feedback channel. A dict like
      {contrast_boost: 0.05, van_gogh_bias: 0.4}. Values are summed across all
      applicable skills and applied as parameter deltas in auto_paint.
    """
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "scope": {
            "image_types": scope_types or [],
            "exclude": exclude_types or [],
        },
        "provenance": {
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            **(provenance or {}),
        },
        "confidence": confidence,
        "tags": tags or [],
    }
    if dimensional_effects:
        meta["dimensional_effects"] = {k: float(v) for k, v in dimensional_effects.items()}
    # Sanitize filename
    safe = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_") or "skill"
    path = SKILLS_DIR / f"{safe}.md"
    content = f"---\n{_to_yaml(meta)}\n---\n{body.strip()}\n"
    path.write_text(content, encoding="utf-8")
    return path


# --- P0.1 feedback loop: effects vector -------------------------------------

# Hard bounds per channel. Deltas are clamped at application time so a runaway
# auto-promoter can't produce wild swings.
EFFECT_LIMITS = {
    "contrast_boost":          (0.0, 0.5),
    "complementary_shadow":    (0.0, 0.3),
    "critique_rounds":         (0.0, 4.0),
    "painterly_details_bias":  (0.0, 1.0),
    "van_gogh_bias":           (0.0, 1.0),
    "tenebrism_bias":          (0.0, 1.0),
    "pointillism_bias":        (0.0, 1.0),
    "engraving_bias":          (0.0, 1.0),
}


def effects_vector(skills: list[Skill]) -> dict[str, float]:
    """Sum `dimensional_effects` across skills. Unknown channels pass through
    so new dimensions are forward-compatible (callers filter what they use)."""
    out: dict[str, float] = {}
    for s in skills:
        for k, v in s.effects.items():
            out[k] = out.get(k, 0.0) + v
    return out


def clamp_effect(channel: str, value: float) -> float:
    lo, hi = EFFECT_LIMITS.get(channel, (float("-inf"), float("inf")))
    return max(lo, min(hi, value))


def applicable_skills_for(image_type: str) -> list[Skill]:
    """Skills whose scope is universal (empty) or explicitly includes image_type.
    Legacy per-run critiques are filtered out."""
    return [
        s for s in iter_skills()
        if not _looks_like_run_critique(s)
        and s.applies_to(image_type)
    ]


def bump_confidence(skill: Skill, delta: int = 1) -> None:
    """Increase/decrease a skill's confidence and rewrite the file."""
    meta = dict(skill.metadata)
    new_conf = max(0, int(meta.get("confidence", 1) or 1) + delta)
    meta["confidence"] = new_conf
    content = f"---\n{_to_yaml(meta)}\n---\n{skill.body.strip()}\n"
    skill.path.write_text(content, encoding="utf-8")
    skill.metadata = meta


def decay_confidence(days: int = 30, dry_run: bool = False) -> list[dict]:
    """#18: skills untouched for `days` lose 1 confidence point.

    Uses file mtime as the "last touched" signal. A skill with confidence=3
    that hasn't been modified in 60 days → still just -1 (single tick per run).
    Skills at 0 are left alone (can't go negative and keeps bottom-tier alive).

    Returns a list of {path, name, old_confidence, new_confidence, days_old}
    describing what changed. Pass dry_run=True to preview without writing.
    """
    import time
    cutoff = time.time() - days * 86400
    changes = []
    for skill in iter_skills():
        mtime = skill.path.stat().st_mtime
        if mtime >= cutoff:
            continue
        old = skill.confidence
        if old <= 0:
            continue
        days_old = int((time.time() - mtime) / 86400)
        changes.append({
            "path": str(skill.path),
            "name": skill.name,
            "old_confidence": old,
            "new_confidence": max(0, old - 1),
            "days_old": days_old,
        })
        if not dry_run:
            bump_confidence(skill, -1)
    return changes
