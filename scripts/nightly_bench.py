"""Autonomous nightly painter loop.

Designed to be triggered by `hermes cron`. Flow:

  1. Ensure viewer + tool server are up (start if down)
  2. Run `scripts/run_bench.py --baseline v10` to paint the 5 canonical targets
  3. For each target: critique_canvas, record_reflection
  4. Write a morning report to `runs/nightly/<date>.md`
  5. If any target regressed > 0.02 SSIM, include ⚠ flag in report title

This script is what Hermes executes when it wakes up.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "runs" / "nightly"


def services_up():
    for url in ("http://localhost:8080/api/state",
                "http://localhost:8765/tool/manifest"):
        try:
            urllib.request.urlopen(url, timeout=2).read()
        except Exception:
            return False
    return True


def start_services():
    env = dict(os.environ)
    env.setdefault("VIRTUAL_ENV", str(ROOT / ".venv"))
    py = str(ROOT / ".venv" / "bin" / "python")
    if not services_up():
        print("[nightly] services down; starting…")
        subprocess.Popen([py, "scripts/viewer.py", "--port", "8080"],
                         cwd=str(ROOT), env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen([py, "scripts/hermes_tools.py", "--port", "8765"],
                         cwd=str(ROOT), env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            time.sleep(1)
            if services_up():
                break
        else:
            print("[nightly] services failed to start", file=sys.stderr)
            sys.exit(2)


def post(tool, payload=None):
    req = urllib.request.Request(
        f"http://localhost:8765/tool/{tool}",
        data=json.dumps(payload or {}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def critique_and_reflect(target_name: str, target_path: str, score: dict):
    """After a target has been painted, run critique + reflection."""
    crit = post("critique_canvas", {})
    modes = [f["mode"] for f in crit.get("findings", [])]
    # Build a structured reflection
    worked = "coverage high" if score and score.get("coverage", 0) > 0.95 else "coverage low"
    failed = "; ".join(f"{f['mode']} (sev {f['severity']})"
                        for f in crit.get("findings", [])) or "no heuristic failures"
    next_try = crit.get("suggested_fixes", ["continue current pipeline"])[0] if crit.get("suggested_fixes") else "continue"
    run_id = f"nightly_{target_name}_{time.strftime('%Y%m%d')}"
    post("record_reflection", {
        "run_id": run_id,
        "target": target_path,
        "what_worked": worked,
        "what_failed": failed,
        "try_next_time": next_try,
        "confidence": 3,
        "failure_modes": modes,
    })
    return {"run_id": run_id, "verdict": crit.get("verdict"), "modes": modes}


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y-%m-%d")
    report_path = REPORT_DIR / f"{date_str}.md"

    start_services()

    # Run bench
    py = str(ROOT / ".venv" / "bin" / "python")
    result = subprocess.run(
        [py, "scripts/run_bench.py", "--baseline", "v10"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600,
    )
    bench_stdout = result.stdout
    bench_rc = result.returncode
    regressions_flag = "⚠ REGRESSIONS DETECTED" if bench_rc == 1 else "✓ all targets OK"

    # Load current & baseline to produce the report
    current = json.loads((ROOT / "benches" / "current.json").read_text())
    baseline = json.loads((ROOT / "benches" / "v10_baseline.json").read_text())
    by_name = {r["name"]: r for r in baseline["results"]}

    # Critique + reflect for each target (canvas is whatever the last paint left)
    reflections = []
    for row in current["results"]:
        sys.path.insert(0, str(ROOT / "scripts"))
        from paint_lib import auto_paint
        # Re-paint this target so canvas is current for critique
        auto_paint(row["target"], seed=42, verbose=False)
        reflections.append(critique_and_reflect(row["name"], row["target"], row))

    # Write report
    lines = [
        f"# Nightly painter bench — {date_str}",
        f"## {regressions_flag}",
        "",
        "## Results per target",
        "| target | ssim | Δ vs v10 | coverage | strokes | critique |",
        "|---|---|---|---|---|---|",
    ]
    for row, refl in zip(current["results"], reflections):
        base = by_name.get(row["name"], {})
        delta = (row["final_ssim"] or 0) - (base.get("final_ssim") or 0)
        lines.append(
            f"| {row['name']} | {row['final_ssim']:.4f} | {delta:+.4f} | "
            f"{row['coverage']:.1%} | {row['total_strokes']} | "
            f"{refl['verdict']} ({', '.join(refl['modes']) or 'clean'}) |"
        )
    lines.append("")
    lines.append("## Phase deltas (mean across targets)")
    lines.append("| phase | mean Δ SSIM |")
    lines.append("|---|---|")
    phase_names = ["edges", "gap_fill", "mid_detail", "fine_detail",
                    "contours", "highlights"]
    for p in phase_names:
        deltas = [r["phase_deltas"].get(p, {}).get("ssim")
                   for r in current["results"]
                   if p in r.get("phase_deltas", {})]
        if deltas:
            mean = sum(d for d in deltas if d is not None) / len(deltas)
            lines.append(f"| {p} | {mean:+.4f} |")
    lines.append("")
    lines.append("## Bench tool stdout")
    lines.append("```")
    lines.append(bench_stdout[-2000:] if bench_stdout else "(no output)")
    lines.append("```")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[nightly] report: {report_path}")
    print(regressions_flag)
    return bench_rc


if __name__ == "__main__":
    sys.exit(main())
