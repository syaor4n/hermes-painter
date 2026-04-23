"""End-of-run reflection: write a signed skill from a run directory.

This is a deterministic heuristic — the rich reflection happens in the CLI
agent's own mind (Claude Code / Hermes). When the agent wants a nuanced
skill body, it calls `save_skill` directly via the tool server; this module
is the safety net that always produces *something* from a finished run.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from . import skills


def _load_trace(run_dir: Path) -> list[dict[str, Any]]:
    trace = run_dir / "trace.jsonl"
    if not trace.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _load_scores(run_dir: Path) -> list[dict[str, float]]:
    p = run_dir / "scores.csv"
    if not p.exists():
        return []
    rows: list[dict[str, float]] = []
    with p.open() as f:
        for row in csv.DictReader(f):
            iter_val = row.get("iter", row.get("iteration", "0"))
            rows.append({
                "iter": int(iter_val),
                "ssim": float(row.get("ssim", 0)),
                "mse": float(row.get("mse", 0)),
                "composite": float(row.get("composite", 0)),
            })
    return rows


def best_batch(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Identify the batch with the biggest SSIM jump."""
    best: dict[str, Any] | None = None
    prev_ssim = 0.0
    for entry in trace:
        s = entry.get("score", {})
        cur_ssim = s.get("ssim") if isinstance(s, dict) else None
        if cur_ssim is None:
            continue
        delta = cur_ssim - prev_ssim
        if best is None or delta > best.get("_delta", -1):
            best = {**entry, "_delta": delta}
        prev_ssim = cur_ssim
    return best


def _heuristic_body(
    scores: list[dict[str, float]],
    best: dict[str, Any] | None,
    image_type: str,
) -> str:
    final = scores[-1] if scores else {}
    if best:
        best_note = (
            f"Biggest jump at iter {best.get('iter', '?')} (Δ SSIM {best.get('_delta', 0):+.3f}): "
            f"{best.get('reasoning', '(no reasoning given)').strip() or 'no reasoning noted'}"
        )
    else:
        best_note = "No clear winning batch — small improvements across iterations."
    return (
        f"For {image_type or 'any'} images, this run reached SSIM {final.get('ssim', 0):.3f} "
        f"(MSE {final.get('mse', 0):.4f}). {best_note}"
    )


def reflect(
    run_dir: Path,
    *,
    image_type: str | None = None,
    target_path: Path | None = None,
    tags: list[str] | None = None,
) -> Path | None:
    """Generate and save a skill from a finished run. Returns the path or None.

    Writes nothing if the run did not improve SSIM by at least 0.02 — it would
    just pollute the skills library with uninformative noise.
    """
    run_dir = Path(run_dir)
    trace = _load_trace(run_dir)
    if not trace:
        return None
    scores = _load_scores(run_dir)
    best = best_batch(trace)

    body = _heuristic_body(scores, best, image_type or "any")

    final_ssim = scores[-1]["ssim"] if scores else 0.0
    initial_ssim = scores[0]["ssim"] if scores else 0.0
    delta = final_ssim - initial_ssim
    if delta < 0.02:
        return None

    name = f"learned_{run_dir.name}"
    provenance = {
        "run": run_dir.name,
        "delta_ssim": round(delta, 4),
        "final_ssim": round(final_ssim, 4),
    }
    if target_path:
        provenance["target"] = str(target_path)
    return skills.write_skill(
        name,
        body,
        scope_types=[image_type] if image_type else None,
        tags=tags,
        provenance=provenance,
        confidence=1,
    )
