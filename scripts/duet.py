#!/usr/bin/env python3
"""CLI entry for the paint_duet orchestrator.

Usage:
  python scripts/duet.py targets/masterworks/mona_lisa.jpg \\
      --personas van_gogh_voice,tenebrist_voice --max-turns 6 --seed 42

Requires viewer + tool server running on :8080 / :8765.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", help="Path to the target image (inside repo)")
    ap.add_argument("--personas", default="van_gogh_voice,tenebrist_voice",
                    help="Comma-separated list of exactly 2 persona names")
    ap.add_argument("--max-turns", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # Probe services using env var URLs with defaults
    viewer_url = os.environ.get("PAINTER_VIEWER_URL", "http://127.0.0.1:8080")
    tool_url = os.environ.get("PAINTER_TOOL_URL", "http://127.0.0.1:8765")
    import urllib.request
    for url, label in [
        (f"{viewer_url}/api/state", "viewer"),
        (f"{tool_url}/tool/manifest", "tool-server"),
    ]:
        try:
            urllib.request.urlopen(url, timeout=3)
        except Exception as e:
            print(f"[duet] {label} not reachable at {url}: {e}", file=sys.stderr)
            return 1

    persona_names = [p.strip() for p in args.personas.split(",") if p.strip()]

    from paint_lib.duet import paint_duet, PERSONAS
    for p in persona_names:
        if p not in PERSONAS:
            print(f"[duet] unknown persona: {p!r}. Available: {sorted(PERSONAS)}",
                  file=sys.stderr)
            return 2

    try:
        result = paint_duet(
            args.target,
            personas=persona_names,
            max_turns=args.max_turns,
            seed=args.seed,
            out_dir=args.out_dir,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"[duet] failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    print(json.dumps({
        "canvas_path": result["canvas_path"],
        "journal_path": result["journal_path"],
        "final_ssim": result["final_ssim"],
        "reason": result["reason"],
        "early_stopped": result["early_stopped"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
