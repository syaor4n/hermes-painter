"""v15 hi-res paint orchestrator.

Usage:
  python scripts/hi_res_paint.py TARGET OUTPUT_PNG [--size 1024] [options...]

Starts (if needed) a dedicated high-resolution viewer + tool server pair on
alternate ports, uploads the target, runs paint_lib.auto_paint with optional
face-detection + face-detail passes, then saves the resulting canvas.

Hi-res canvas (1024²) gives 4× more pixels of room for detail vs the default
512². Useful for masterwork reproduction where small features (faces, hands,
fabric folds) need more than 4-6 canvas pixels each to register.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def probe(url: str, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout).read()
        return True
    except Exception:
        return False


def ensure_hires_services(size: int, viewer_port: int, tools_port: int):
    """Make sure a viewer + tool_server pair runs at hi-res."""
    py = str(ROOT / ".venv" / "bin" / "python")
    if not probe(f"http://localhost:{viewer_port}/api/state"):
        print(f"[hi_res] starting viewer on :{viewer_port} at size {size}")
        subprocess.Popen(
            [py, "scripts/viewer.py", "--port", str(viewer_port),
             "--size", str(size)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            time.sleep(1)
            if probe(f"http://localhost:{viewer_port}/api/state", timeout=1):
                break
        else:
            raise SystemExit("viewer failed to start")

    if not probe(f"http://localhost:{tools_port}/tool/manifest"):
        print(f"[hi_res] starting tool_server on :{tools_port} → viewer :{viewer_port}")
        subprocess.Popen(
            [py, "scripts/hermes_tools.py", "--port", str(tools_port),
             "--viewer", f"http://localhost:{viewer_port}"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(20):
            time.sleep(1)
            if probe(f"http://localhost:{tools_port}/tool/manifest", timeout=1):
                break
        else:
            raise SystemExit("tool server failed to start")
    print(f"[hi_res] services ready: viewer :{viewer_port} / tools :{tools_port}")


def post(tool: str, payload: dict, port: int) -> dict:
    req = urllib.request.Request(
        f"http://localhost:{port}/tool/{tool}",
        data=json.dumps(payload or {}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def viewer_get(path: str, port: int) -> bytes:
    with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=30) as r:
        return r.read()


def viewer_post_target(path: Path, port: int, fit: str = "crop"):
    data = path.read_bytes()
    req = urllib.request.Request(
        f"http://localhost:{port}/api/target?fit={fit}",
        data=data,
        method="POST",
        headers={"Content-Type": "image/png"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("output")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--viewer-port", type=int, default=8180)
    ap.add_argument("--tools-port", type=int, default=8765)  # reuse default
    ap.add_argument("--style-mode", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--contrast-boost", type=float, default=0.25)
    ap.add_argument("--use-faces", action="store_true",
                    help="detect + paint faces with dedicated detail pass")
    ap.add_argument("--fit", default="crop", choices=["crop", "letterbox", "auto"])
    args = ap.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        raise SystemExit(f"target not found: {target_path}")

    # Use separate viewer at size 1024 on port 8180 so default 512 viewer stays intact
    ensure_hires_services(args.size, args.viewer_port, args.tools_port)
    tools_port = args.tools_port

    # Route tool server to the hi-res viewer. We need a dedicated tool server
    # pointing at that viewer OR we can just run all painting through the new
    # viewer's API + a fresh tool_server that points at it.
    #
    # For simplicity: always spin up a dedicated tools_server on port 8775 when
    # tools_port defaults to 8765 (which is usually the 512 server).
    if tools_port == 8765:
        tools_port = args.tools_port + 10  # 8775
        if not probe(f"http://localhost:{tools_port}/tool/manifest"):
            py = str(ROOT / ".venv" / "bin" / "python")
            subprocess.Popen(
                [py, "scripts/hermes_tools.py", "--port", str(tools_port),
                 "--viewer", f"http://localhost:{args.viewer_port}"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for _ in range(20):
                time.sleep(1)
                if probe(f"http://localhost:{tools_port}/tool/manifest", timeout=1):
                    break
            else:
                raise SystemExit("dedicated hi-res tools server failed")
            print(f"[hi_res] dedicated tools_server started on :{tools_port}")

    # Upload target
    viewer_post_target(target_path, args.viewer_port, fit=args.fit)
    print(f"[hi_res] target uploaded to viewer :{args.viewer_port}")

    # Clear canvas first (target upload doesn't auto-clear in all flows)
    post("clear", {}, tools_port)

    # Set env so paint_lib uses the hi-res canvas size in any fallback
    os.environ["PAINTER_CANVAS_SIZE"] = str(args.size)

    # Run paint via paint_lib — but override the `post()` port in paint_lib
    # to hit our hi-res tools server. Simplest: import paint_lib, monkey-patch.
    import paint_lib
    orig_post = paint_lib.post
    def hr_post(tool, p=None, port=None):
        try:
            return orig_post(tool, p, port=tools_port)
        except Exception as e:
            print(f"[hi_res] ERROR tool={tool} payload_keys={list((p or {}).keys())} err={e}")
            raise
    paint_lib.post = hr_post

    kwargs = dict(
        seed=args.seed,
        contrast_boost=args.contrast_boost,
        verbose=True,
    )
    if args.style_mode:
        kwargs["style_mode"] = args.style_mode

    t0 = time.time()
    result = paint_lib.auto_paint(str(target_path), **kwargs)
    print(f"[hi_res] base paint: ssim={result.get('final_score', {}).get('ssim'):.3f} in {time.time()-t0:.1f}s")

    # Face detection + detail pass (optional)
    if args.use_faces:
        faces = hr_post("detect_faces", {"min_size": 30})
        print(f"[hi_res] detected {faces.get('n', 0)} faces")
        if faces.get("faces"):
            fd = hr_post("face_detail_plan", {
                "faces": faces["faces"],
                "padding": 0.30,
                "cell_size": 2,
                "error_threshold": 10,
                "max_strokes_per_face": 1500,
                "alpha": 0.90,
            })
            if fd.get("strokes"):
                hr_post("draw_strokes", {
                    "strokes": fd["strokes"],
                    "reasoning": f"Phase 9 · face detail ({faces['n']} faces)",
                })
                print(f"[hi_res] +{fd['n']} face detail strokes")

    # Save final canvas PNG
    state = json.loads(viewer_get("/api/state", args.viewer_port))
    png = base64.b64decode(state["canvas_png"])
    out = Path(args.output).resolve()
    out.write_bytes(png)
    print(f"[hi_res] saved: {out} ({len(png)} bytes, {args.size}×{args.size})")


if __name__ == "__main__":
    main()
