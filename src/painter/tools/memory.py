"""Memory/learning tools: skills, journal, style signature, reflections.

Handlers here wrap the ``painter.skills`` / ``painter.journal`` /
``painter.style`` modules and manage the ``reflections/`` markdown store
under the repo root.
"""
from __future__ import annotations

from pathlib import Path

from painter import journal as journal_mod
from painter import skills as skills_mod
from painter import style as style_mod

from ._common import _REFLECTIONS_DIR


def tool_list_skills(args: dict) -> dict:
    image_type = args.get("image_type")
    tags = args.get("tags")
    include_legacy = bool(args.get("include_legacy", False))
    skill_objs = skills_mod.iter_skills()
    out = []
    for s in skill_objs:
        if not include_legacy and skills_mod._looks_like_run_critique(s):
            continue
        if s.applies_to(image_type, tags=tags):
            out.append({
                "name": s.name,
                "scope_types": s.scope_types,
                "tags": s.tags,
                "confidence": s.confidence,
                "body": s.body.strip(),
            })
    # Frontmatter skills first, then by confidence desc, then name
    out.sort(key=lambda d: (0 if d["tags"] or d["scope_types"] else 1, -d["confidence"], d["name"]))
    return {"skills": out}


def tool_save_skill(args: dict) -> dict:
    path = skills_mod.write_skill(
        args["name"],
        args["body"],
        scope_types=args.get("scope_types"),
        exclude_types=args.get("exclude_types"),
        tags=args.get("tags"),
        provenance=args.get("provenance"),
        confidence=int(args.get("confidence", 1)),
    )
    return {"path": str(path)}


def tool_list_journal(args: dict) -> dict:
    n = int(args.get("n", 20))
    return {"entries": journal_mod.tail(n)}


def tool_save_journal_entry(args: dict) -> dict:
    """Append a run summary to journal.jsonl.

    Expected fields (all optional — include whatever is meaningful):
      run, target, image_type, iters, final_ssim, blank_ssim,
      delta_vs_start, skills_loaded, candidates_per_iter, note
    The `ts` field is auto-added with the current UTC timestamp.
    """
    entry = dict(args)
    journal_mod.record(entry)
    return {"ok": True, "entry": entry}


def tool_read_style(_args: dict) -> dict:
    return {"body": style_mod.read()}


def tool_update_style(args: dict) -> dict:
    body = args.get("body")
    note = args.get("evolution_note")
    if body:
        style_mod.update(body, append_evolution=note)
    elif note:
        style_mod.append_evolution_line(note)
    return {"ok": True, "body": style_mod.read()}


def tool_record_reflection(args: dict) -> dict:
    """Save a structured post-run reflection.

    args: {
      run_id: str,
      target: str,
      what_worked: str,
      what_failed: str,
      try_next_time: str,
      confidence: int (1..5),
      surprised_by: str?,             # optional
      failure_modes: list[str]?,      # optional mode names from the taxonomy
    }

    Writes `reflections/<run_id>.md` as markdown with YAML frontmatter so
    Hermes session_search / grep can retrieve by target, mode, etc.
    """
    import datetime as _dt
    _REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = args.get("run_id") or _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    meta = {
        "run_id": run_id,
        "target": args.get("target", ""),
        "confidence": int(args.get("confidence", 3)),
        "failure_modes": args.get("failure_modes") or [],
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
    }
    body = (
        f"**what_worked**: {args.get('what_worked', '').strip()}\n\n"
        f"**what_failed**: {args.get('what_failed', '').strip()}\n\n"
        f"**try_next_time**: {args.get('try_next_time', '').strip()}\n"
    )
    if args.get("surprised_by"):
        body += f"\n**surprised_by**: {args['surprised_by'].strip()}\n"
    fm_yaml = "\n".join(f"  - {m}" for m in meta["failure_modes"]) or "  []"
    frontmatter = (
        "---\n"
        f"run_id: {meta['run_id']}\n"
        f"target: {meta['target']}\n"
        f"confidence: {meta['confidence']}\n"
        f"timestamp: {meta['timestamp']}\n"
        f"failure_modes:\n{fm_yaml}\n"
        "---\n\n"
    )
    path = _REFLECTIONS_DIR / f"{run_id}.md"
    path.write_text(frontmatter + body, encoding="utf-8")
    return {"ok": True, "path": str(path)}


def tool_load_painter_brief(_args: dict) -> dict:
    """Compressed recap of painter state for session start.

    Returns a <2KB markdown brief combining:
      - current style signature (from skills/style/signature.md)
      - last 5 journal entries (most recent trajectory)
      - failure mode stats from last 10 reflections
      - top-3 skills by confidence
    """
    lines: list[str] = []
    lines.append("# Painter brief\n")

    # Style signature (truncate)
    try:
        sig = style_mod.read()
        if sig:
            head = sig[:400].rstrip()
            lines.append("## style (truncated)")
            lines.append(head)
            if len(sig) > 400:
                lines.append("… (call read_style for full signature)")
            lines.append("")
    except Exception:
        pass

    # Recent journal
    try:
        entries = journal_mod.tail(n=5)
        if entries:
            lines.append("## last 5 runs")
            for e in entries:
                run = e.get("run", "?")
                ssim = e.get("final_ssim")
                note = (e.get("note") or "")[:140]
                ssim_s = f"{ssim:.3f}" if isinstance(ssim, (int, float)) else "—"
                lines.append(f"- **{run}** (ssim={ssim_s}) {note}")
            lines.append("")
    except Exception:
        pass

    # Failure mode stats
    try:
        fm_counts: dict[str, int] = {}
        refl_files = sorted(_REFLECTIONS_DIR.glob("*.md"), reverse=True)[:10]
        for rf in refl_files:
            text = rf.read_text(encoding="utf-8", errors="ignore")
            if "failure_modes:" in text:
                # parse lines between `failure_modes:` and next top-level key
                in_block = False
                for line in text.splitlines():
                    if line.startswith("failure_modes:"):
                        in_block = True
                        continue
                    if in_block:
                        if line.startswith("  - "):
                            fm_counts[line[4:].strip()] = fm_counts.get(line[4:].strip(), 0) + 1
                        elif not line.startswith(" "):
                            break
        if fm_counts:
            lines.append("## failure modes in last 10 reflections")
            for mode, n in sorted(fm_counts.items(), key=lambda x: -x[1])[:6]:
                lines.append(f"- {mode}: {n}")
            lines.append("")
    except Exception:
        pass

    # Top skills by confidence
    try:
        skills_list = list(skills_mod.iter_skills())
        skills_list.sort(key=lambda s: -s.confidence)
        if skills_list:
            lines.append("## top skills by confidence")
            for s in skills_list[:3]:
                desc = (s.metadata.get("description")
                         if isinstance(s.metadata, dict) else None) or ""
                desc = desc[:100]
                lines.append(f"- **{s.name}** (c={s.confidence}) {desc}")
            lines.append("")
    except Exception:
        pass

    lines.append("## discipline reminder")
    lines.append("- dump_target + Read at start")
    lines.append("- score_plan 2 candidates before draw_strokes")
    lines.append("- dump_canvas + Read after each batch")
    lines.append("- critique_canvas + record_reflection at end")

    text = "\n".join(lines)
    # Soft cap at ~2 KB
    if len(text) > 2200:
        text = text[:2100] + "\n…(truncated)"
    return {"brief": text, "size_bytes": len(text)}


def tool_skill_effectiveness_report(args: dict) -> dict:
    """v12.4: aggregate which recipes/skills have been active in reflections
    and what outcomes resulted.

    args: {n: int = 30}    # how many recent reflections to scan
    Returns: {recipes: [{name, runs, mean_severity_score, failure_mode_histogram}], n_reflections}

    A "recipe" in this report is any token in `what_worked` field that matches
    the pattern "Recipe: <name>" OR a skill name found in skills dir. If
    nothing matches, the report aggregates by target type instead (basename).
    """
    import datetime as _dt
    n = int(args.get("n", 30))
    if not _REFLECTIONS_DIR.exists():
        return {"recipes": [], "n_reflections": 0, "note": "no reflections/ directory"}
    files = sorted(_REFLECTIONS_DIR.glob("*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    by_recipe: dict[str, dict] = {}
    total_by_mode: dict[str, int] = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Parse frontmatter modes
        modes: list[str] = []
        in_fm = False
        in_modes = False
        for line in text.splitlines():
            if line.strip() == "---":
                in_fm = not in_fm
                continue
            if in_fm and line.startswith("failure_modes:"):
                in_modes = True
                continue
            if in_fm and in_modes:
                if line.startswith("  - "):
                    modes.append(line[4:].strip())
                elif not line.startswith(" "):
                    in_modes = False
        # Find a "Recipe: X" marker in body
        recipe = None
        for line in text.splitlines():
            if "Recipe:" in line:
                recipe = line.split("Recipe:", 1)[1].strip().split(".")[0].strip()
                break
        if recipe is None:
            # Fall back to target basename
            for line in text.splitlines():
                if line.startswith("target:"):
                    t = line.split(":", 1)[1].strip()
                    recipe = Path(t).stem
                    break
            recipe = recipe or "(unknown)"
        entry = by_recipe.setdefault(recipe, {"runs": 0, "severity_sum": 0,
                                                "mode_counts": {}})
        entry["runs"] += 1
        # Severity sum: each mode contributes 1 (can be refined with severity)
        entry["severity_sum"] += len(modes)
        for m in modes:
            entry["mode_counts"][m] = entry["mode_counts"].get(m, 0) + 1
            total_by_mode[m] = total_by_mode.get(m, 0) + 1
    # Build output rows
    rows = []
    for name, e in by_recipe.items():
        avg_sev = e["severity_sum"] / max(1, e["runs"])
        rows.append({
            "name": name,
            "runs": e["runs"],
            "mean_failure_count": round(avg_sev, 2),
            "modes": dict(sorted(e["mode_counts"].items(), key=lambda x: -x[1])),
        })
    rows.sort(key=lambda r: -r["runs"])
    return {
        "recipes": rows,
        "n_reflections": len(files),
        "failure_mode_total": dict(sorted(total_by_mode.items(), key=lambda x: -x[1])),
    }


def tool_reflection_clusters(args: dict) -> dict:
    """v12.5: cluster recent reflections by dominant failure mode.

    Returns summary that highlights persistent problems and what recently
    improved. Read this before writing new skills — the signal emerges
    from clusters, not individual reflections.

    args: {n: int = 20}
    """
    n = int(args.get("n", 20))
    if not _REFLECTIONS_DIR.exists():
        return {"clusters": [], "n_reflections": 0}
    files = sorted(_REFLECTIONS_DIR.glob("*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    mode_to_runs: dict[str, list[dict]] = {}
    clean_runs: list[dict] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        target = ""
        run_id = ""
        modes: list[str] = []
        in_fm = False
        in_modes = False
        for line in text.splitlines():
            if line.strip() == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                if line.startswith("target:"):
                    target = line.split(":", 1)[1].strip()
                elif line.startswith("run_id:"):
                    run_id = line.split(":", 1)[1].strip()
                elif line.startswith("failure_modes:"):
                    in_modes = True
                    continue
                if in_modes:
                    if line.startswith("  - "):
                        modes.append(line[4:].strip())
                    elif not line.startswith(" ") and line.strip():
                        in_modes = False
        run = {"run_id": run_id, "target": target}
        if not modes:
            clean_runs.append(run)
        else:
            for m in modes:
                mode_to_runs.setdefault(m, []).append(run)
    # Build clusters
    clusters = []
    for mode, runs in sorted(mode_to_runs.items(), key=lambda x: -len(x[1])):
        clusters.append({
            "mode": mode,
            "count": len(runs),
            "sample_runs": [r["run_id"] for r in runs[:3]],
            "targets": list({Path(r["target"]).stem for r in runs if r["target"]})[:5],
        })
    return {
        "clusters": clusters,
        "clean_runs": len(clean_runs),
        "n_reflections": len(files),
        "summary": (
            f"{len(clean_runs)}/{len(files)} runs clean. "
            f"Top issues: "
            + ", ".join(f"{c['mode']} ({c['count']})" for c in clusters[:3])
            if clusters else f"{len(clean_runs)}/{len(files)} runs clean — no recurring issues."
        ),
    }


def tool_decay_skills(args: dict) -> dict:
    """#18: Decrement confidence by 1 on skills untouched for N days.

    args: {days: int = 30, dry_run: bool = false}
    Returns: {n_changed, changes: [{name, old_confidence, new_confidence, days_old}, ...]}
    """
    days = int(args.get("days", 30))
    dry_run = bool(args.get("dry_run", False))
    changes = skills_mod.decay_confidence(days=days, dry_run=dry_run)
    return {"n_changed": len(changes), "changes": changes, "dry_run": dry_run}


_IMAGE_TYPE_KEYS = ("balanced", "dark", "bright", "high_contrast", "muted")


def _infer_dimensional_effects(snippet: str) -> dict[str, float]:
    """Map a normalized what_worked snippet to a dimensional_effects dict.

    P0.1 feedback loop: promoted skills don't just exist as text — they
    literally change pipeline parameters via apply_skill_effects in
    paint_lib/core.py. Keep deltas small; they compound across multiple
    promoted skills.
    """
    s = snippet.lower()
    out: dict[str, float] = {}
    # Every promoted skill nudges contrast; successful runs tended to have a bit
    # more tonal punch than default. Small delta so many skills can stack.
    out["contrast_boost"] = 0.03

    if "style_mode=van_gogh" in s:
        out["van_gogh_bias"] = 0.35
    if "style_mode=tenebrism" in s:
        out["tenebrism_bias"] = 0.40
        out["contrast_boost"] = out.get("contrast_boost", 0) + 0.02
    if "style_mode=pointillism" in s:
        out["pointillism_bias"] = 0.35
    if "style_mode=engraving" in s:
        out["engraving_bias"] = 0.35

    if "palette_match strong" in s:
        out["complementary_shadow"] = 0.02
    if "painterly" in s:
        out["painterly_details_bias"] = 0.50
    if "critique" in s or "correction" in s:
        out["critique_rounds"] = out.get("critique_rounds", 0) + 1.0

    # Image_type-specific tuning
    if "image_type=dark" in s:
        out["tenebrism_bias"] = max(out.get("tenebrism_bias", 0.0), 0.30)
    if "image_type=high_contrast" in s:
        out["contrast_boost"] = out.get("contrast_boost", 0) + 0.02
    return out


def _infer_scope(snippet: str) -> list[str]:
    """Derive the target image_type(s) this promoted skill should apply to.
    If the reflection mentioned image_type=X, return [X]. Otherwise return
    ['brief'] for paintings done from prompts (back-compat with the original
    auto_promoted flow). Empty list = universal.
    """
    s = snippet.lower()
    for t in _IMAGE_TYPE_KEYS:
        if f"image_type={t}" in s:
            return [t]
    # Fallback: brief-mode runs don't mention an image_type; scope them to brief
    return ["brief"]


def tool_skill_promote(args: dict) -> dict:
    """Scan recent reflections and promote repeating "what_worked" patterns
    to skills (or bump confidence if a matching skill already exists).

    args: {
      n: int = 30             # scan last N reflections
      min_repeat: int = 3     # pattern must occur at least this many times
      max_promote: int = 3    # cap new skills written per call
      dry_run: bool = false
    }

    Returns: {promoted: [...], bumped: [...], scanned: int}
    A "pattern" is a sub-phrase appearing in `what_worked` across multiple
    reflections whose confidence >= 3. Each promoted skill receives
    `dimensional_effects` inferred from the pattern — this is what makes the
    learning loop visible in subsequent paintings.
    """
    import datetime as _dt
    import re as _re
    from collections import Counter

    n = int(args.get("n", 30))
    min_repeat = int(args.get("min_repeat", 3))
    max_promote = int(args.get("max_promote", 3))
    dry_run = bool(args.get("dry_run", False))

    if not _REFLECTIONS_DIR.exists():
        return {"promoted": [], "bumped": [], "scanned": 0,
                "note": "no reflections/ directory"}

    files = sorted(_REFLECTIONS_DIR.glob("*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:n]

    # Extract `what_worked` hints from each reflection, split on `; `
    snippets: list[tuple[str, Path]] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # Find the "confidence: N" line in frontmatter
        conf = 3
        m = _re.search(r"^confidence:\s*(\d+)", text, _re.M)
        if m:
            conf = int(m.group(1))
        if conf < 3:
            continue  # skip low-confidence runs
        mw = _re.search(r"\*\*what_worked\*\*:\s*(.+?)\n", text)
        if not mw:
            continue
        hint = mw.group(1).strip()
        for piece in _re.split(r";\s*", hint):
            piece = piece.strip()
            if len(piece) < 8 or len(piece) > 120:
                continue
            snippets.append((piece, f))

    # Normalize: strip stroke counts / numeric noise so near-identical snippets
    # ("style_mode=van_gogh" + "underpainting=769 strokes") cluster correctly
    def _normalize(s: str) -> str:
        # Drop numeric literals so "underpainting=769 strokes" → "underpainting=N strokes"
        s = _re.sub(r"\b\d+(\.\d+)?\b", "N", s)
        return s.lower().strip()

    counts = Counter(_normalize(s) for s, _ in snippets)
    recurring = [(snippet, c) for snippet, c in counts.items() if c >= min_repeat]
    recurring.sort(key=lambda x: -x[1])

    existing_names = {s.name for s in skills_mod.iter_skills()}
    promoted: list[dict] = []
    bumped: list[dict] = []

    for snippet, count in recurring[:max_promote]:
        safe = _re.sub(r"[^a-z0-9_]+", "_", snippet)[:50].strip("_") or "pattern"
        skill_name = f"promoted_{safe}"
        # Does a similar skill already exist?
        matched = None
        for s in skills_mod.iter_skills():
            if safe in s.name or snippet in s.body.lower():
                matched = s
                break
        if matched:
            if not dry_run:
                skills_mod.bump_confidence(matched, +1)
            bumped.append({
                "name": matched.name,
                "new_confidence": matched.confidence + (1 if not dry_run else 0),
                "based_on": count,
            })
            continue
        effects = _infer_dimensional_effects(snippet)
        scope = _infer_scope(snippet)
        eff_str = ", ".join(f"{k}={v:+.2f}" for k, v in sorted(effects.items()))
        body = (
            f"Pattern auto-promoted after appearing in {count} successful "
            f"reflections (confidence ≥ 3):\n\n    {snippet}\n\n"
            f"Dimensional effects applied when this skill is active:\n\n"
            f"    {eff_str}\n\n"
            f"Scope: image_types={scope}. These effects are summed across all "
            f"applicable skills and applied as parameter deltas in "
            f"auto_paint (contrast_boost, "
            f"complementary_shadow, critique_rounds, style_mode bias, etc.). "
            f"Review: if the pattern turned out to be accidental, delete this file."
        )
        provenance = {
            "auto_promoted": True,
            "reflections_scanned": len(files),
            "recurrence_count": count,
            "promoted_at": _dt.datetime.utcnow().strftime("%Y-%m-%d"),
        }
        if dry_run:
            promoted.append({"name": skill_name, "body_preview": body[:80],
                             "count": count, "effects": effects, "scope": scope,
                             "dry_run": True})
            continue
        path = skills_mod.write_skill(
            skill_name, body,
            scope_types=scope, tags=["auto_promoted"],
            provenance=provenance, confidence=3,
            dimensional_effects=effects,
        )
        promoted.append({"name": skill_name, "path": str(path),
                         "count": count, "effects": effects, "scope": scope})

    return {
        "promoted": promoted,
        "bumped": bumped,
        "scanned": len(files),
        "min_repeat": min_repeat,
        "dry_run": dry_run,
    }
