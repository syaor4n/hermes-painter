"""Bridge script: apply a plan JSON to the live viewer.

Usage:
  python scripts/paint_live.py plan.json
  python scripts/paint_live.py --clear
  python scripts/paint_live.py --target targets/landscape_photo.jpg
  python scripts/paint_live.py --status
  python scripts/paint_live.py --init targets/landscape_photo.jpg
"""
from __future__ import annotations

import base64
import csv
import io
import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

VIEWER = "http://localhost:8080"


def api(method, path, data=None, raw_bytes=None):
    url = f"{VIEWER}{path}"
    if data is not None:
        body = json.dumps(data).encode()
        req = Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
    elif raw_bytes is not None:
        req = Request(url, data=raw_bytes, method=method)
        req.add_header("Content-Type", "image/png")
    else:
        req = Request(url, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except URLError as e:
        sys.exit(
            f"Cannot reach viewer at {VIEWER} ({e.reason}). "
            "Start it first: python scripts/viewer.py"
        )


def get_state():
    return api("GET", "/api/state")


def apply_plan(plan):
    return api("POST", "/api/plan", data=plan)


def clear_canvas():
    return api("POST", "/api/clear")


def set_target(png_bytes):
    return api("POST", "/api/target", raw_bytes=png_bytes)


def show_status(state=None):
    if state is None:
        state = get_state()
    print(f"Iteration: {state['iteration']}")
    print(f"Strokes: {state['strokes_applied']}")
    if state.get("score"):
        s = state["score"]
        print(f"SSIM: {s['ssim']:.4f}  MSE: {s['mse']:.6f}  Composite: {s['composite']:.4f}")
    if state.get("history"):
        print(f"\nHistory ({len(state['history'])} iterations):")
        print(f"{'Iter':>4}  {'SSIM':>8}  {'MSE':>10}  {'Composite':>10}  {'Strokes':>7}")
        for h in state["history"]:
            s = h["score"]
            print(f"{h['iteration']:>4}  {s['ssim']:>8.4f}  {s['mse']:>10.6f}  {s['composite']:>10.4f}  {h['strokes']:>7}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--clear":
        clear_canvas()
        print("Canvas cleared.")

    elif cmd == "--status":
        show_status()

    elif cmd == "--target":
        target_path = Path(sys.argv[2])
        from PIL import Image
        img = Image.open(target_path).convert("RGB").resize((512, 512), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        set_target(buf.getvalue())
        print(f"Target set: {target_path}")

    elif cmd == "--init":
        # Clear + set target + init run dir
        target_path = Path(sys.argv[2])
        clear_canvas()
        from PIL import Image
        img = Image.open(target_path).convert("RGB").resize((512, 512), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        set_target(buf.getvalue())
        # Take initial screenshot state
        state = get_state()
        print(f"Initialized. Target: {target_path}")
        show_status(state)

    else:
        # Assume it's a plan JSON file
        plan_path = Path(cmd)
        plan = json.loads(plan_path.read_text())
        result = apply_plan(plan)
        print(f"Applied {len(plan.get('strokes', []))} strokes. Iteration: {result.get('iteration')}")
        if result.get("score"):
            s = result["score"]
            print(f"SSIM: {s['ssim']:.4f}  MSE: {s['mse']:.6f}  Composite: {s['composite']:.4f}")
