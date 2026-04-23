"""Cross-run causal trace. One JSON object per run, appended to journal.jsonl."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOURNAL_PATH = Path(
    os.environ.get("PAINTER_JOURNAL_PATH")
    or Path(__file__).resolve().parents[2] / "journal.jsonl"
)


def record(entry: dict[str, Any], *, path: Path | None = None) -> None:
    """Append a run summary to the journal."""
    path = path or JOURNAL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def tail(n: int = 20, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the N most recent journal entries."""
    path = path or JOURNAL_PATH
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-n:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize(entries: list[dict[str, Any]]) -> str:
    """Compact textual summary for injection into a planner prompt."""
    if not entries:
        return ""
    lines = ["## Recent runs (most recent last)"]
    for e in entries:
        ts = e.get("ts", "?")[:10]
        img = e.get("image_type", "?")
        tgt = e.get("target", "?")
        ssim = e.get("final_ssim")
        delta = e.get("delta_vs_start")
        note = e.get("note", "")
        ssim_s = f"{ssim:.3f}" if isinstance(ssim, (int, float)) else "?"
        delta_s = f"{delta:+.3f}" if isinstance(delta, (int, float)) else "?"
        lines.append(f"- {ts} [{img}] {Path(str(tgt)).name}: ssim={ssim_s}, Δ={delta_s} — {note}")
    return "\n".join(lines)
