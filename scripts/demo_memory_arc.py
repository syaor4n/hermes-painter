"""F1 flagship: reproduce the memory arc on demand.

Spawns an isolated viewer + tool server in /tmp/memory_arc_<ts>/ with env
vars pointing at a sandbox. Paints one target cold, primes 5 same-image-type
neighbors, promotes recurring reflections, then paints the same target with
the promoted skills applied. Emits side_by_side.png + summary.json.

Usage:
  python scripts/demo_memory_arc.py
  python scripts/demo_memory_arc.py --target targets/masterworks/great_wave.jpg
  python scripts/demo_memory_arc.py --style-mode tenebrism --seed 7
  python scripts/demo_memory_arc.py --priming path/a.jpg,path/b.jpg

The user's real skills/, reflections/, and journal.jsonl are never touched.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# src/ is on sys.path so `painter.image_type` resolves when this script is
# invoked directly (python scripts/demo_memory_arc.py).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from painter.image_type import classify  # noqa: E402


_FEATURE_KEYS = ("mean", "std", "saturation", "warmth")


def _feature_vector(feats: dict[str, Any]) -> list[float]:
    return [float(feats[k]) for k in _FEATURE_KEYS]


def _classify_png(path: Path) -> dict[str, Any]:
    return classify(path.read_bytes())


def _euclid(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _minmax_normalize(vectors: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    """Return (normalized_vectors, mins, ranges). ranges use max(1e-9, hi-lo)
    to avoid divide-by-zero when a feature is constant across candidates."""
    if not vectors:
        return [], [0.0] * len(_FEATURE_KEYS), [1.0] * len(_FEATURE_KEYS)
    n_features = len(vectors[0])
    mins = [min(v[i] for v in vectors) for i in range(n_features)]
    maxs = [max(v[i] for v in vectors) for i in range(n_features)]
    ranges = [max(1e-9, maxs[i] - mins[i]) for i in range(n_features)]
    normed = [[(v[i] - mins[i]) / ranges[i] for i in range(n_features)] for v in vectors]
    return normed, mins, ranges


def _normalize_point(vec: list[float], mins: list[float], ranges: list[float]) -> list[float]:
    return [(vec[i] - mins[i]) / ranges[i] for i in range(len(vec))]


def pick_priming_targets(
    final_target: Path,
    *,
    style_mode: str,
    k: int = 5,
    candidate_dirs: list[Path] | None = None,
    diversity_threshold: float = 0.15,
) -> list[Path]:
    """Select up to k priming targets that share the final target's image_type
    and are feature-nearest, with a greedy diversity filter.

    All files from `candidate_dirs` matching *.jpg/*.jpeg/*.png are considered.
    Returns a list (possibly shorter than k). The final target is excluded by
    resolved path. Deterministic: `sorted(glob())` + stable distance ordering.

    `style_mode` is accepted for signature symmetry with the caller but does
    not influence selection — style is enforced at paint time.
    """
    if candidate_dirs is None:
        candidate_dirs = [
            _ROOT / "targets",
            _ROOT / "targets" / "unsplash",
            _ROOT / "targets" / "masterworks",
        ]

    final_resolved = final_target.resolve()
    final_feats = _classify_png(final_target)
    final_type = final_feats["type"]

    # Gather same-type candidates
    candidates: list[tuple[Path, dict[str, Any]]] = []
    seen: set[Path] = set()
    for d in candidate_dirs:
        d = Path(d)
        if not d.exists():
            continue
        for pattern in ("*.jpg", "*.jpeg", "*.png"):
            for p in sorted(d.glob(pattern)):
                pr = p.resolve()
                if pr == final_resolved or pr in seen:
                    continue
                seen.add(pr)
                feats = _classify_png(p)
                if feats["type"] != final_type:
                    continue
                candidates.append((p, feats))

    if not candidates:
        return []

    # Normalize all candidate feature vectors together, then normalize the
    # final target's vector against the SAME ranges so distances are comparable.
    cand_vectors = [_feature_vector(f) for _, f in candidates]
    normed, mins, ranges = _minmax_normalize(cand_vectors)
    final_norm = _normalize_point(_feature_vector(final_feats), mins, ranges)

    scored = sorted(
        (
            (_euclid(normed[i], final_norm), candidates[i][0], normed[i])
            for i in range(len(candidates))
        ),
        key=lambda t: (t[0], t[1].name),
    )

    picked: list[tuple[Path, list[float]]] = []
    for _dist, p, nvec in scored:
        if len(picked) >= k:
            break
        too_close = any(
            _euclid(nvec, pvec) < diversity_threshold for _, pvec in picked
        )
        if too_close:
            continue
        picked.append((p, nvec))

    return [p for p, _ in picked]


def make_sandbox(root: Path) -> dict[str, Path]:
    """Create the sandbox layout under `root`. Returns a dict of paths.

    Layout:
        root/
          skills/
            style/signature.md   (copied from real library if it exists)
          reflections/
          runs/
          logs/
          journal.jsonl           (empty)

    Idempotent: calling twice on the same root is fine.
    """
    root = Path(root)
    skills_dir = root / "skills"
    reflections_dir = root / "reflections"
    runs_dir = root / "runs"
    logs_dir = root / "logs"
    journal_path = root / "journal.jsonl"

    for d in (skills_dir, skills_dir / "style", reflections_dir, runs_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    if not journal_path.exists():
        journal_path.write_text("")

    # Copy style signature so the painter's voice persists into the sandbox.
    # The style/ subdir is excluded by iter_skills(), so this doesn't pollute
    # the "zero promoted skills" invariant for the cold run.
    sig_src = _ROOT / "skills" / "style" / "signature.md"
    sig_dst = skills_dir / "style" / "signature.md"
    if sig_src.exists() and not sig_dst.exists():
        shutil.copy2(sig_src, sig_dst)

    return {
        "root": root,
        "skills_dir": skills_dir,
        "reflections_dir": reflections_dir,
        "runs_dir": runs_dir,
        "logs_dir": logs_dir,
        "journal_path": journal_path,
    }


def build_side_by_side(
    target_png: Path,
    cold_png: Path,
    primed_png: Path,
    out_path: Path,
    *,
    header: str = "",
    panel_size: int = 512,
    gap: int = 16,
    label_band: int = 32,
) -> None:
    """Compose target | cold | primed panels horizontally with labels.

    All three images are resized to panel_size x panel_size. A header strip
    (if given) runs across the top. A label band runs across the bottom with
    "target / cold / primed (after 5 priming runs)".
    """
    from PIL import Image, ImageDraw, ImageFont  # imported lazily so tests that
                                                  # don't need PIL still load fast

    def _load_square(p: Path) -> Image.Image:
        im = Image.open(p).convert("RGB")
        return im.resize((panel_size, panel_size), Image.LANCZOS)

    imgs = [_load_square(target_png), _load_square(cold_png), _load_square(primed_png)]
    labels = ["target", "cold", "primed (after 5 priming runs)"]

    header_h = label_band if header else 0
    total_w = 3 * panel_size + 2 * gap
    total_h = panel_size + label_band + header_h

    canvas = Image.new("RGB", (total_w, total_h), (240, 240, 240))

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except OSError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(canvas)

    # Header
    if header:
        draw.text((gap, 8), header, fill=(40, 40, 40), font=font)

    # Panels + labels
    for i, (im, label) in enumerate(zip(imgs, labels)):
        x = i * (panel_size + gap)
        y = header_h
        canvas.paste(im, (x, y))
        text_w = draw.textlength(label, font=font)
        draw.text(
            (x + (panel_size - text_w) / 2, y + panel_size + 8),
            label,
            fill=(40, 40, 40),
            font=font,
        )

    canvas.save(out_path)


def write_summary(summary: dict[str, Any], out_path: Path) -> None:
    """Write the demo summary as pretty-printed JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))


def _wait_http_200(url: str, *, timeout_s: float = 10.0, interval_s: float = 0.5) -> bool:
    """Poll `url` and return True as soon as it responds 200, else False on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, OSError):
            pass
        time.sleep(interval_s)
    return False


def _kill_proc(proc: subprocess.Popen, *, label: str) -> None:
    """SIGTERM → 2s wait → SIGKILL fallback. Silent on already-dead."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass
        proc.kill()
        proc.wait(timeout=2)
    except Exception as e:
        print(f"[demo] warn: failed to kill {label}: {e}", file=sys.stderr)


def spawn_stack(
    sandbox: dict[str, Path],
    *,
    viewer_port: int = 18080,
    tools_port: int = 18765,
    renderer: str = "pil",
    python: str = sys.executable,
) -> tuple[subprocess.Popen, subprocess.Popen]:
    """Launch the isolated viewer + tool server with sandbox env vars.

    Blocks until both answer 200 on their health endpoints, up to 10s each.
    On failure, kills whatever came up and raises RuntimeError.
    """
    existing_pypath = os.environ.get("PYTHONPATH", "")
    env = {
        **os.environ,
        "PAINTER_SKILLS_DIR": str(sandbox["skills_dir"]),
        "PAINTER_REFLECTIONS_DIR": str(sandbox["reflections_dir"]),
        "PAINTER_JOURNAL_PATH": str(sandbox["journal_path"]),
        "PAINTER_TOOL_URL": f"http://127.0.0.1:{tools_port}",
        "PAINTER_VIEWER_URL": f"http://127.0.0.1:{viewer_port}",
        "PYTHONPATH": f"{_ROOT / 'src'}{os.pathsep}{existing_pypath}" if existing_pypath else str(_ROOT / "src"),
    }

    viewer_log = (sandbox["logs_dir"] / "viewer.log").open("a")
    tools_log = (sandbox["logs_dir"] / "tools.log").open("a")

    viewer_proc = subprocess.Popen(
        [python, str(_ROOT / "scripts" / "viewer.py"),
         "--port", str(viewer_port),
         "--renderer", renderer,
         "--tool-url", f"http://127.0.0.1:{tools_port}"],
        env=env,
        stdout=viewer_log, stderr=viewer_log,
        cwd=str(_ROOT),
    )

    tools_proc = subprocess.Popen(
        [python, str(_ROOT / "scripts" / "hermes_tools.py"),
         "--port", str(tools_port),
         "--viewer", f"http://127.0.0.1:{viewer_port}"],
        env=env,
        stdout=tools_log, stderr=tools_log,
        cwd=str(_ROOT),
    )

    viewer_up = _wait_http_200(f"http://127.0.0.1:{viewer_port}/api/state")
    tools_up = _wait_http_200(f"http://127.0.0.1:{tools_port}/tool/manifest")

    if not (viewer_up and tools_up):
        _kill_proc(viewer_proc, label="viewer")
        _kill_proc(tools_proc, label="tools")
        raise RuntimeError(
            f"isolated stack failed to come up. "
            f"viewer={'ok' if viewer_up else 'DOWN'} tools={'ok' if tools_up else 'DOWN'}. "
            f"See {sandbox['logs_dir']}/viewer.log and tools.log"
        )

    return viewer_proc, tools_proc


def _fetch_state(viewer_url: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{viewer_url}/api/state", timeout=5) as r:
        return json.loads(r.read())


def _load_target(tool_url: str, target: Path) -> None:
    body = json.dumps({"path": str(target)}).encode()
    req = urllib.request.Request(
        f"{tool_url}/tool/load_target",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"load_target failed: {r.status}")


def _read_canvas_png(viewer_url: str) -> bytes:
    """Pull the canvas PNG bytes from /api/state."""
    st = _fetch_state(viewer_url)
    b64 = st.get("canvas_png")
    if not b64:
        raise RuntimeError("viewer /api/state did not include canvas_png")
    return base64.b64decode(b64)


def paint_once(
    target: Path,
    *,
    apply_feedback: bool,
    auto_reflect: bool,
    style_mode: str | None,
    seed: int,
    viewer_url: str,
    tool_url: str,
) -> dict[str, Any]:
    """Run one auto_paint against the isolated stack. Returns metrics + canvas.

    Assumes:
      - spawn_stack has been called (viewer+tools are up with sandbox env)
      - PAINTER_VIEWER_URL / PAINTER_TOOL_URL env vars are set in this process
        (so paint_lib.core resolves them correctly)

    Calls paint_lib.auto_paint() in-process, pattern matching
    scripts/learn_from_targets.py:122 (which also imports and calls it directly).
    """
    # Defer import: paint_lib pulls in painter.skills/etc., which must be
    # imported AFTER the caller set the PAINTER_* env vars.
    if str(_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(_ROOT / "scripts"))
    from paint_lib import auto_paint

    _load_target(tool_url, target)

    t0 = time.time()
    result = auto_paint(
        str(target),
        seed=seed,
        verbose=False,
        style_mode=style_mode,
        apply_feedback=apply_feedback,
        auto_reflect=auto_reflect,
    )
    elapsed_s = round(time.time() - t0, 2)

    final = _fetch_state(viewer_url)
    score = final.get("score") or {}
    canvas_png = _read_canvas_png(viewer_url)

    return {
        "ssim": float(score.get("ssim") or 0.0),
        "n_strokes": int(final.get("strokes_applied", 0)),
        "applied_skills": list(result.get("applied_skills") or []),
        "effective_params": dict(result.get("effective_params") or {}),
        "canvas_png": canvas_png,
        "elapsed_s": elapsed_s,
    }


def _post_skill_promote(tool_url: str) -> dict[str, Any]:
    body = json.dumps({"n": 10, "min_repeat": 2, "max_promote": 8}).encode()
    req = urllib.request.Request(
        f"{tool_url}/tool/skill_promote",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _format_header(target: Path, style_mode: str | None, seed: int) -> str:
    style = style_mode or "default"
    return f"{target.name} — style={style}, seed={seed}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--target", type=Path,
                     default=_ROOT / "targets" / "masterworks" / "great_wave.jpg")
    ap.add_argument("--style-mode", default="van_gogh")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", type=Path, default=None,
                     help="Default: gallery/learning/<YYYYMMDD_HHMMSS>/")
    ap.add_argument("--priming", default="",
                     help="Comma-separated priming paths (overrides auto-selection)")
    ap.add_argument("--viewer-port", type=int, default=18080)
    ap.add_argument("--tools-port", type=int, default=18765)
    ap.add_argument("--keep-sandbox", action="store_true", default=True)
    ap.add_argument("--clean-sandbox", dest="keep_sandbox", action="store_false")
    args = ap.parse_args(argv)

    if not args.target.exists():
        print(f"[demo] target not found: {args.target}", file=sys.stderr)
        return 1

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    sandbox_root = Path(tempfile.gettempdir()) / f"memory_arc_{ts}"
    out_dir = args.out_dir or (_ROOT / "gallery" / "learning" / ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[demo] sandbox:  {sandbox_root}")
    print(f"[demo] out-dir:  {out_dir}")
    print(f"[demo] target:   {args.target.relative_to(_ROOT) if args.target.is_absolute() else args.target}")
    print(f"[demo] style:    {args.style_mode}  seed: {args.seed}")

    sandbox = make_sandbox(sandbox_root)

    viewer_url = f"http://127.0.0.1:{args.viewer_port}"
    tool_url = f"http://127.0.0.1:{args.tools_port}"
    # paint_lib.core reads these env vars to know which stack to talk to (R5).
    os.environ["PAINTER_VIEWER_URL"] = viewer_url
    os.environ["PAINTER_TOOL_URL"] = tool_url
    os.environ["PAINTER_SKILLS_DIR"] = str(sandbox["skills_dir"])
    os.environ["PAINTER_REFLECTIONS_DIR"] = str(sandbox["reflections_dir"])
    os.environ["PAINTER_JOURNAL_PATH"] = str(sandbox["journal_path"])

    viewer_proc = tools_proc = None
    exit_code = 0
    try:
        print("[demo] spawning isolated stack...")
        viewer_proc, tools_proc = spawn_stack(
            sandbox,
            viewer_port=args.viewer_port,
            tools_port=args.tools_port,
        )
        print(f"[demo]   viewer :{args.viewer_port}  tools :{args.tools_port}  ok")

        # COLD
        print("\n[demo] COLD run (apply_feedback=False, zero promoted skills)...")
        cold = paint_once(
            args.target,
            apply_feedback=False, auto_reflect=False,
            style_mode=args.style_mode, seed=args.seed,
            viewer_url=viewer_url, tool_url=tool_url,
        )
        assert not cold["applied_skills"], (
            "invariant violated: cold paint saw promoted skills "
            f"(sandbox leaked): {cold['applied_skills']}"
        )
        (out_dir / "run_cold.png").write_bytes(cold["canvas_png"])
        print(f"[demo]   ssim={cold['ssim']:.4f}  strokes={cold['n_strokes']}  elapsed={cold['elapsed_s']}s")

        # PRIMING
        if args.priming.strip():
            priming = [Path(p.strip()) for p in args.priming.split(",") if p.strip()]
            priming_note = f"explicit override, {len(priming)} paths"
        else:
            priming = pick_priming_targets(
                args.target, style_mode=args.style_mode, k=5,
            )
            priming_note = (
                f"auto-selected {len(priming)} same-type neighbors"
                if len(priming) == 5
                else f"only {len(priming)} same-type candidates available"
            )
        print(f"\n[demo] PRIMING x{len(priming)}  ({priming_note})")
        for i, p in enumerate(priming, 1):
            r = paint_once(
                p,
                apply_feedback=True, auto_reflect=True,
                style_mode=args.style_mode, seed=args.seed + i,
                viewer_url=viewer_url, tool_url=tool_url,
            )
            rel = p.relative_to(_ROOT) if p.is_absolute() and str(p).startswith(str(_ROOT)) else p
            print(f"[demo]   [{i}/{len(priming)}] {rel}  ssim={r['ssim']:.4f}  strokes={r['n_strokes']}")

        # PROMOTE
        print("\n[demo] skill_promote scanning sandbox reflections...")
        promote = _post_skill_promote(tool_url)
        promoted_list = promote.get("promoted") or []
        print(f"[demo]   scanned={promote.get('scanned', 0)}  promoted={len(promoted_list)}")
        for p in promoted_list:
            print(f"[demo]     + {p.get('name')}  effects={p.get('effects')}")

        # PRIMED
        print("\n[demo] PRIMED run (apply_feedback=True, same target/seed/style as cold)...")
        primed = paint_once(
            args.target,
            apply_feedback=True, auto_reflect=False,
            style_mode=args.style_mode, seed=args.seed,
            viewer_url=viewer_url, tool_url=tool_url,
        )
        (out_dir / "run_primed.png").write_bytes(primed["canvas_png"])
        print(f"[demo]   ssim={primed['ssim']:.4f}  strokes={primed['n_strokes']}  "
              f"applied_skills={len(primed['applied_skills'])}  elapsed={primed['elapsed_s']}s")

        # ARTIFACTS
        print("\n[demo] writing artifacts...")
        build_side_by_side(
            args.target, out_dir / "run_cold.png", out_dir / "run_primed.png",
            out_dir / "side_by_side.png",
            header=_format_header(args.target, args.style_mode, args.seed),
        )

        final_feats = _classify_png(args.target)
        summary = {
            "ts": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "target": str(args.target.relative_to(_ROOT) if args.target.is_absolute() and str(args.target).startswith(str(_ROOT)) else args.target),
            "image_type": final_feats["type"],
            "style_mode": args.style_mode,
            "seed": args.seed,
            "sandbox_path": str(sandbox_root),
            "priming": {
                "k_requested": 5,
                "k_used": len(priming),
                "targets": [str(p.relative_to(_ROOT) if p.is_absolute() and str(p).startswith(str(_ROOT)) else p) for p in priming],
                "note": priming_note,
            },
            "cold": {
                "ssim": cold["ssim"],
                "n_strokes": cold["n_strokes"],
                "applied_skills": cold["applied_skills"],
                "effective_params": cold["effective_params"],
                "elapsed_s": cold["elapsed_s"],
            },
            "primed": {
                "ssim": primed["ssim"],
                "n_strokes": primed["n_strokes"],
                "applied_skills": primed["applied_skills"],
                "effective_params": primed["effective_params"],
                "elapsed_s": primed["elapsed_s"],
            },
            "delta": {
                "ssim": round(primed["ssim"] - cold["ssim"], 4),
                "applied_skills_count": len(primed["applied_skills"]),
                "effective_params": {
                    k: round(float(primed["effective_params"].get(k, 0) or 0) - float(cold["effective_params"].get(k, 0) or 0), 4)
                    for k in ("contrast_boost", "complementary_shadow", "critique_rounds", "painterly_details")
                    if k in primed["effective_params"] or k in cold["effective_params"]
                },
            },
            "promoted": promoted_list,
        }
        write_summary(summary, out_dir / "summary.json")

        print(f"\n[demo] ✓ done.")
        print(f"[demo]   side-by-side: {out_dir / 'side_by_side.png'}")
        print(f"[demo]   summary:      {out_dir / 'summary.json'}")
        if len(priming) < 5:
            exit_code = 1  # soft-fail signal: fewer primings than requested

    except RuntimeError as e:
        print(f"\n[demo] ✗ {e}", file=sys.stderr)
        exit_code = 2
    except Exception as e:
        print(f"\n[demo] ✗ paint failed: {type(e).__name__}: {e}", file=sys.stderr)
        exit_code = 3
    finally:
        if viewer_proc is not None:
            _kill_proc(viewer_proc, label="viewer")
        if tools_proc is not None:
            _kill_proc(tools_proc, label="tools")
        if not args.keep_sandbox:
            shutil.rmtree(sandbox_root, ignore_errors=True)

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
