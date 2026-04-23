# -*- coding: utf-8 -*-
"""Web viewer for the painting agent — serves a live canvas on port 8080.

Usage:
  python scripts/viewer.py [--port 8080]

Endpoints (JSON unless noted):
  GET  /                      — Live viewer UI
  GET  /api/state             — Current canvas PNG + score as JSON
  GET  /api/snapshots         — List all available snapshots
  GET  /api/iteration/{N}     — Canvas snapshot at iteration N
  GET  /api/heatmap           — Per-pixel error vs. target (PNG)
  GET  /api/regions           — Worst N=24 8x8 cells (error map)
  GET  /api/list_personas     — Proxy to tool-server list_personas: {personas, count}
  POST /api/stroke            — Apply a stroke: {"type":"fill_rect", ...}
  POST /api/plan              — Apply a plan: {"strokes":[...]}
  POST /api/score_plan        — Imagine a plan (render locally, return score)
  POST /api/clear             — Reset canvas to white
  POST /api/snapshot          — Capture a restore point, returns {"id": str}
  POST /api/restore           — Restore a snapshot: {"id": str}
  GET  /api/target            — Current target image (if set)
  POST /api/target            — Set target image (multipart upload or raw PNG)
  POST /api/paint             — Run auto_paint.py on current target
  POST /api/morph_preview     — Re-paint current target with dimensional biases
  POST /api/suggest_morph     — Proxy to tool-server plan_style_schedule: {schedule, candidates}
  POST /api/paint_duet        — Run two-persona duet: {"persona_a":str, "persona_b":str, "max_turns"?:int}
"""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Lock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from painter.browser import painter_browser
from painter.executor import execute_plan
from painter.critic import score as score_func
from painter.critic import heatmap_bytes, region_errors, score_plan as imagine_plan
from painter import local_renderer as _local_renderer

MAX_SNAPSHOTS = 40   # bound the in-memory history so long sessions don't OOM

# v15: canvas size configurable via --size flag. Default 512 for back-compat;
# 1024 enables hi-res rendering for masterwork fidelity.
CANVAS_SIZE = 512

# Renderer backend. 'browser' uses Playwright + canvas/index.html (full fidelity,
# linen texture, true snapshots). 'pil' uses painter.local_renderer and needs no
# Chromium install — useful for CI and judges who just want `make demo`.
RENDERER = "browser"

# Tool server URL for proxied endpoints. Configurable via --tool-url CLI flag.
TOOL_URL = "http://127.0.0.1:8765"

# Viewer port for passing to subprocesses. Stored at module level in main().
VIEWER_PORT = 8080

_PIL_CANVAS_BYTES: bytes | None = None
_PIL_SNAPSHOTS: "OrderedDict[str, bytes]" = OrderedDict()

# --- Shared state ---
STATE = {
    "canvas_png": None,       # current canvas base64
    "target_png": None,       # bytes
    "target_b64": None,       # base64 for display
    "target_name": None,      # filename
    "score": None,
    "iteration": 0,
    "strokes_applied": 0,
    "history": [],            # list of {iteration, score, strokes, reasoning}
    "snapshots": OrderedDict(),  # iteration -> base64 canvas snapshot (bounded)
    "stroke_log": OrderedDict(), # iteration -> list[stroke dict] (bounded, for replay)
    "busy": False,
    "job_status": "idle",            # idle | running | success | failed
    "job_started_at": None,          # ISO timestamp when subprocess spawned
    "job_finished_at": None,         # ISO timestamp when subprocess exited
    "job_exit_code": None,           # int, 0 on success, non-zero on failure
    "job_kind": None,                # "paint" | "duet" | "morph_preview"
    "job_stderr_tail": "",           # last ~500 chars of stderr, for debugging
    "last_error": None,              # the most recent error message (persists across jobs)
}

STATE_LOCK = Lock()


def _try_claim_busy() -> bool:
    """Atomic check-and-set: returns True if we claimed the busy slot,
    False if another run is already in progress."""
    with STATE_LOCK:
        if STATE["busy"]:
            return False
        STATE["busy"] = True
        return True


def _release_busy() -> None:
    """Always call this in the `finally` of whatever spawned a paint run."""
    with STATE_LOCK:
        STATE["busy"] = False


def _mark_job_started(kind: str) -> None:
    """Record that a subprocess job of the given kind just launched.
    Must be called while holding the lock OR right after a successful
    _try_claim_busy()."""
    with STATE_LOCK:
        STATE["job_status"] = "running"
        STATE["job_kind"] = kind
        STATE["job_started_at"] = datetime.now(timezone.utc).isoformat()
        STATE["job_finished_at"] = None
        STATE["job_exit_code"] = None
        STATE["job_stderr_tail"] = ""


def _mark_job_finished(exit_code: int, stderr_bytes: bytes = b"") -> None:
    """Record job completion. Called in the subprocess thread's finally."""
    tail = stderr_bytes.decode("utf-8", errors="replace")[-500:] if stderr_bytes else ""
    with STATE_LOCK:
        STATE["job_status"] = "success" if exit_code == 0 else "failed"
        STATE["job_finished_at"] = datetime.now(timezone.utc).isoformat()
        STATE["job_exit_code"] = exit_code
        STATE["job_stderr_tail"] = tail
        if exit_code != 0:
            STATE["last_error"] = tail.strip().splitlines()[-1] if tail.strip() else f"Subprocess exited with code {exit_code}"


BROWSER = None
LOOP = None
_BROWSER_LOCK: asyncio.Lock | None = None  # created lazily once LOOP exists


async def get_browser():
    global BROWSER, _BROWSER_LOCK
    if _BROWSER_LOCK is None:
        _BROWSER_LOCK = asyncio.Lock()
    async with _BROWSER_LOCK:
        if BROWSER is None:
            import playwright.async_api
            pw = await playwright.async_api.async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            canvas_html = Path(__file__).resolve().parent.parent / "canvas" / "index.html"
            # v15: pass ?size=N so canvas matches CANVAS_SIZE
            url = f"{canvas_html.as_uri()}?size={CANVAS_SIZE}"
            await page.goto(url)
            await page.wait_for_function("() => window.painter && window.painter.drawStrokes")
            BROWSER = type('B', (), {'page': page, 'browser': browser, 'pw': pw})()
    return BROWSER


def _pil_blank_png(size: int = None) -> bytes:
    """Warm off-white base matching canvas/index.html clear() — without the grain
    texture. For pil-renderer mode; parity is close enough for testing."""
    from PIL import Image
    s = size or CANVAS_SIZE
    img = Image.new("RGB", (s, s), (251, 247, 238))  # #fbf7ee
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pil_apply(strokes: list[dict]) -> None:
    """Render strokes on top of the current PIL canvas; updates _PIL_CANVAS_BYTES
    and STATE['canvas_png']."""
    global _PIL_CANVAS_BYTES
    base = _PIL_CANVAS_BYTES or _pil_blank_png()
    _PIL_CANVAS_BYTES = _local_renderer.render_to_png(
        strokes, base_png=base, size=(CANVAS_SIZE, CANVAS_SIZE)
    )
    STATE["canvas_png"] = base64.b64encode(_PIL_CANVAS_BYTES).decode("ascii")
    _store_snapshot(STATE["iteration"], STATE["canvas_png"])


def _pil_clear() -> None:
    global _PIL_CANVAS_BYTES
    _PIL_CANVAS_BYTES = _pil_blank_png()
    STATE["canvas_png"] = base64.b64encode(_PIL_CANVAS_BYTES).decode("ascii")
    STATE["iteration"] = 0
    STATE["strokes_applied"] = 0
    STATE["history"] = []
    STATE["snapshots"].clear()
    STATE["stroke_log"].clear()
    STATE["score"] = None
    _PIL_SNAPSHOTS.clear()


def _pil_snapshot() -> str:
    import uuid
    sid = uuid.uuid4().hex[:12]
    _PIL_SNAPSHOTS[sid] = _PIL_CANVAS_BYTES or _pil_blank_png()
    while len(_PIL_SNAPSHOTS) > MAX_SNAPSHOTS:
        _PIL_SNAPSHOTS.popitem(last=False)
    return sid


def _pil_restore(snap_id: str) -> bool:
    global _PIL_CANVAS_BYTES
    blob = _PIL_SNAPSHOTS.get(snap_id)
    if blob is None:
        return False
    _PIL_CANVAS_BYTES = blob
    STATE["canvas_png"] = base64.b64encode(_PIL_CANVAS_BYTES).decode("ascii")
    return True


def _store_snapshot(iteration: int, b64: str) -> None:
    """Bounded snapshot store — drop the oldest when we exceed MAX_SNAPSHOTS."""
    snaps = STATE["snapshots"]
    if iteration in snaps:
        snaps.move_to_end(iteration)
    snaps[iteration] = b64
    while len(snaps) > MAX_SNAPSHOTS:
        snaps.popitem(last=False)


def _store_strokes(iteration: int, strokes: list) -> None:
    """Bounded stroke log so clicking a history entry can replay the strokes.

    v10 #2: store gzipped JSON instead of raw Python lists. Typical 2300-stroke
    iteration: ~500 KB raw → ~80 KB gzipped. At 40 iterations that's ~3 MB
    instead of ~20 MB.
    """
    import gzip
    log = STATE["stroke_log"]
    if iteration in log:
        log.move_to_end(iteration)
    log[iteration] = gzip.compress(json.dumps(strokes).encode(), compresslevel=6)
    while len(log) > MAX_SNAPSHOTS:
        log.popitem(last=False)


def _load_strokes(iteration: int):
    """Inverse of _store_strokes: decompress on read. Returns list or None."""
    import gzip
    log = STATE["stroke_log"]
    blob = log.get(iteration)
    if blob is None:
        return None
    if isinstance(blob, list):
        return blob  # legacy (pre-v10)
    return json.loads(gzip.decompress(blob).decode())


async def refresh_state():
    if RENDERER == "pil":
        if _PIL_CANVAS_BYTES is None:
            _pil_clear()
        STATE["canvas_png"] = base64.b64encode(_PIL_CANVAS_BYTES).decode("ascii")
        _store_snapshot(STATE["iteration"], STATE["canvas_png"])
        return
    b = await get_browser()
    b64 = await b.page.evaluate("() => window.painter.getPNG()")
    STATE["canvas_png"] = b64
    _store_snapshot(STATE["iteration"], b64)


async def async_clear():
    if RENDERER == "pil":
        _pil_clear()
        return
    b = await get_browser()
    await b.page.evaluate("() => window.painter.clear()")
    STATE["iteration"] = 0
    STATE["strokes_applied"] = 0
    STATE["history"] = []
    STATE["snapshots"].clear()
    STATE["stroke_log"].clear()
    STATE["score"] = None
    await refresh_state()


async def async_apply_stroke(spec):
    if RENDERER == "pil":
        _pil_apply([spec])
        STATE["strokes_applied"] = STATE.get("strokes_applied", 0) + 1
    else:
        b = await get_browser()
        await b.page.evaluate("(s) => window.painter.drawStroke(s)", spec)
        STATE["strokes_applied"] = STATE.get("strokes_applied", 0) + 1
        await refresh_state()
    if STATE["target_png"]:
        canvas_bytes = base64.b64decode(STATE["canvas_png"])
        s = score_func(STATE["target_png"], canvas_bytes)
        STATE["score"] = s


async def async_apply_plan(plan):
    strokes = plan.get("strokes", []) or []
    if RENDERER == "pil":
        if strokes:
            _pil_apply(strokes)
    else:
        b = await get_browser()
        if strokes:
            await b.page.evaluate("(xs) => window.painter.drawStrokes(xs)", strokes)
    n = len(strokes)
    STATE["strokes_applied"] = STATE.get("strokes_applied", 0) + n
    STATE["iteration"] = STATE.get("iteration", 0) + 1
    _store_strokes(STATE["iteration"], strokes)
    if RENDERER != "pil":
        await refresh_state()
    if STATE["target_png"]:
        canvas_bytes = base64.b64decode(STATE["canvas_png"])
        s = score_func(STATE["target_png"], canvas_bytes)
        STATE["score"] = s
    else:
        s = None
    STATE["history"].append({
        "iteration": STATE["iteration"],
        "score": s,
        "strokes": n,
        "reasoning": plan.get("reasoning", ""),
    })
    while len(STATE["history"]) > MAX_SNAPSHOTS:
        STATE["history"].pop(0)


async def async_snapshot() -> str:
    if RENDERER == "pil":
        return _pil_snapshot()
    b = await get_browser()
    return await b.page.evaluate("() => window.painter.snapshot()")


async def async_restore(snap_id: str) -> bool:
    if RENDERER == "pil":
        return _pil_restore(snap_id)
    b = await get_browser()
    ok = await b.page.evaluate("(id) => window.painter.restore(id)", snap_id)
    if ok:
        await refresh_state()
    return ok


async def async_set_target(png_bytes, filename=None, fit_mode="crop"):
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    ratio = max(w, h) / min(w, h)
    # #13: auto-letterbox when aspect is far from 1:1 unless user forced crop.
    # fit_mode="crop" (default) always center-crops to square.
    # fit_mode="letterbox" always preserves aspect and pads with white.
    # fit_mode="auto" letterboxes when ratio > 1.4, otherwise crops.
    if fit_mode == "auto":
        fit_mode = "letterbox" if ratio > 1.4 else "crop"
    # v15: target is resized to the active canvas size (CANVAS_SIZE)
    C = CANVAS_SIZE
    if fit_mode == "letterbox":
        scale = C / max(w, h)
        nw, nh = int(w * scale), int(h * scale)
        resized = img.resize((nw, nh), Image.LANCZOS)
        padded = Image.new("RGB", (C, C), (255, 255, 255))
        padded.paste(resized, ((C - nw) // 2, (C - nh) // 2))
        img = padded
    else:  # crop
        size = min(w, h)
        left = (w - size) // 2
        top = (h - size) // 2
        img = img.crop((left, top, left + size, top + size)).resize((C, C), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    STATE["target_png"] = buf.getvalue()
    STATE["target_b64"] = base64.b64encode(STATE["target_png"]).decode("ascii")
    STATE["target_name"] = filename or "uploaded"


def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, LOOP)
    return future.result(timeout=30)


def _parse_multipart_file(body: bytes, content_type: str) -> tuple[bytes | None, str | None]:
    """Extract the first file part from a multipart/form-data body.

    Replacement for cgi.FieldStorage (cgi is removed in Python 3.13).
    """
    import re
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
    if not m:
        return None, None
    boundary = (m.group(1) or m.group(2)).strip().encode()
    delim = b"--" + boundary
    parts = body.split(delim)
    for part in parts:
        if b"filename=" not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end < 0:
            continue
        headers = part[:header_end].decode("utf-8", errors="replace")
        payload = part[header_end + 4 :]
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        fn = re.search(r'filename="([^"]*)"', headers)
        filename = fn.group(1) if fn else "uploaded"
        return payload, filename
    return None, None


class ViewerHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            # Re-read from disk so UI edits take effect without restart.
            try:
                html = _INDEX_HTML_PATH.read_text(encoding="utf-8")
            except FileNotFoundError:
                html = INDEX_HTML
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())

        elif path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "canvas_png": STATE["canvas_png"],
                "score": STATE["score"],
                "iteration": STATE["iteration"],
                "strokes_applied": STATE["strokes_applied"],
                "history": STATE["history"],
                "has_target": STATE["target_png"] is not None,
                "target_name": STATE.get("target_name"),
                "busy": STATE["busy"],
                "snapshot_count": len(STATE["snapshots"]),
                "job_status": STATE["job_status"],
                "job_kind": STATE["job_kind"],
                "job_started_at": STATE["job_started_at"],
                "job_finished_at": STATE["job_finished_at"],
                "job_exit_code": STATE["job_exit_code"],
                "job_stderr_tail": STATE["job_stderr_tail"],
                "last_error": STATE["last_error"],
            }
            self.wfile.write(json.dumps(data).encode())

        elif path.startswith("/api/iteration/"):
            # /api/iteration/{N}          -> PNG snapshot JSON
            # /api/iteration/{N}/strokes  -> stroke list for iteration N (replay)
            parts = path.split("/")
            try:
                iter_num = int(parts[3])
            except (ValueError, IndexError):
                self.send_response(400)
                self.end_headers()
                return
            want_strokes = len(parts) >= 5 and parts[4] == "strokes"
            if want_strokes:
                strokes = _load_strokes(iter_num)
                if strokes is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    prev_snap = STATE["snapshots"].get(iter_num - 1) if iter_num > 0 else None
                    self.wfile.write(json.dumps({
                        "iteration": iter_num,
                        "strokes": strokes,
                        "prev_canvas_png": prev_snap,
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"No strokes for iteration {iter_num}"}).encode())
            else:
                snapshot = STATE["snapshots"].get(iter_num)
                if snapshot:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"iteration": iter_num, "canvas_png": snapshot}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"No snapshot for iteration {iter_num}"}).encode())

        elif path == "/api/snapshots":
            # List all available snapshots
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"iterations": sorted(STATE["snapshots"].keys())}).encode())

        elif path == "/api/target":
            if STATE["target_b64"]:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"target_png": STATE["target_b64"], "name": STATE.get("target_name")}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        elif path == "/api/heatmap":
            if not STATE["target_png"] or not STATE["canvas_png"]:
                self.send_response(404)
                self.end_headers()
                return
            cur = base64.b64decode(STATE["canvas_png"])
            png = heatmap_bytes(STATE["target_png"], cur)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)

        elif path == "/api/regions":
            if not STATE["target_png"] or not STATE["canvas_png"]:
                self.send_response(404)
                self.end_headers()
                return
            cur = base64.b64decode(STATE["canvas_png"])
            cells = region_errors(STATE["target_png"], cur, grid=8)[:24]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"regions": cells}).encode())

        elif path == "/api/list_personas":
            # Proxy to tool-server /tool/list_personas so the browser stays
            # same-origin (viewer:8080 vs tool-server:8765 would otherwise
            # require CORS). 5-second timeout.
            import urllib.request
            import urllib.error
            try:
                req = urllib.request.Request(
                    TOOL_URL + "/tool/list_personas",
                    data=b"{}",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_body = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp_body)
            except urllib.error.URLError as exc:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": f"tool server not reachable on :8765 ({exc.reason})"
                }).encode())
            except TimeoutError:
                self.send_response(504)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "list_personas timed out"
                }).encode())
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": f"list_personas failed: {type(exc).__name__}: {exc}"
                }).encode())

        elif path.startswith("/assets/"):
            # Static assets for viewer/index.html (studio background, icons, etc.).
            # Path is confined to viewer/assets/ via resolve() + is_relative_to().
            rel = path[len("/assets/"):]
            root = (Path(__file__).resolve().parent.parent / "viewer" / "assets").resolve()
            try:
                candidate = (root / rel).resolve()
                candidate.relative_to(root)  # raises if outside root
            except (ValueError, OSError):
                self.send_response(404); self.end_headers(); return
            if not candidate.is_file():
                self.send_response(404); self.end_headers(); return
            ctype = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".svg": "image/svg+xml",
                ".webp": "image/webp", ".ico": "image/x-icon",
            }.get(candidate.suffix.lower(), "application/octet-stream")
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        elif path.startswith("/gallery/"):
            # Static gallery thumbnails for the preset bar + future UI.
            # Path is confined to gallery/ via resolve() + relative_to().
            rel = path[len("/gallery/"):]
            root = (Path(__file__).resolve().parent.parent / "gallery").resolve()
            try:
                candidate = (root / rel).resolve()
                candidate.relative_to(root)  # raises if outside root
            except (ValueError, OSError):
                self.send_response(404); self.end_headers(); return
            if not candidate.is_file():
                self.send_response(404); self.end_headers(); return
            ctype = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".svg": "image/svg+xml",
                ".webp": "image/webp",
            }.get(candidate.suffix.lower(), "application/octet-stream")
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/api/stroke":
            try:
                spec = json.loads(body)
                run_async(async_apply_stroke(spec))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "score": STATE["score"]}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif path == "/api/plan":
            # NB: /api/plan must NOT claim the busy lock. It's the endpoint
            # the paint subprocess POSTs strokes to DURING an in-flight run —
            # only the entry points that SPAWN paint runs (/api/paint,
            # /api/paint_duet, /api/morph_preview) claim the lock.
            try:
                plan = json.loads(body)
                run_async(async_apply_plan(plan))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "score": STATE["score"], "iteration": STATE["iteration"]}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif path == "/api/clear":
            run_async(async_clear())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

        elif path == "/api/score_plan":
            try:
                plan = json.loads(body)
                if not STATE["target_png"]:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"no target set")
                    return
                cur_bytes = base64.b64decode(STATE["canvas_png"]) if STATE["canvas_png"] else None
                out = imagine_plan(plan, target_png=STATE["target_png"], current_png=cur_bytes)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "imagined": out}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif path == "/api/snapshot":
            try:
                sid = run_async(async_snapshot())
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "id": sid}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif path == "/api/restore":
            try:
                data = json.loads(body)
                ok = run_async(async_restore(data["id"]))
                self.send_response(200 if ok else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": bool(ok)}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif path == "/api/paint":
            # Start the painting agent on the current target
            if not STATE["target_png"]:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No target uploaded"}).encode())
                return

            import subprocess
            style_mode = "balanced"
            style_personality = ""
            style_schedule_json = ""
            _ALLOWED_PERSONALITIES = {
                "",  # empty/missing → Classical (no personality)
                "van_gogh",
                "tenebrism",
                "pointillism",
                "engraving",
                "lumiere_doree",
            }
            # Note: schedule start/end allow-list is _ALLOWED_PERSONALITIES
            # minus the empty string — every slot in a schedule must be a
            # real style name.
            _ALLOWED_SCHEDULE_STYLES = _ALLOWED_PERSONALITIES - {""}
            try:
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {}
            style_mode = payload.get("style_mode", "balanced")
            if style_mode not in ("balanced", "tight", "loose", "segmented"):
                style_mode = "balanced"
            style_personality = payload.get("style_personality", "") or ""
            if style_personality not in _ALLOWED_PERSONALITIES:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": f"Unknown style_personality: {style_personality!r}"
                }).encode())
                return
            schedule = payload.get("style_schedule")
            if schedule is not None:
                if not isinstance(schedule, dict):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "style_schedule must be a JSON object"
                    }).encode())
                    return
                s_start = schedule.get("start")
                s_end = schedule.get("end")
                if not s_start or not s_end:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "style_schedule requires both start and end"
                    }).encode())
                    return
                if s_start not in _ALLOWED_SCHEDULE_STYLES:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"Unknown style_schedule.start: {s_start!r}"
                    }).encode())
                    return
                if s_end not in _ALLOWED_SCHEDULE_STYLES:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"Unknown style_schedule.end: {s_end!r}"
                    }).encode())
                    return
                rationale = schedule.get("rationale", "")
                if not isinstance(rationale, str):
                    rationale = ""
                normalized = {"start": s_start, "end": s_end, "rationale": rationale}
                if style_personality:
                    # Precedence documented in spec: schedule wins.
                    print("[warn] /api/paint: style_schedule supersedes "
                          "style_personality", file=sys.stderr)
                    style_personality = ""
                style_schedule_json = json.dumps(normalized)

            # All validation complete. Now claim the busy lock atomically.
            if not _try_claim_busy():
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "a paint run is already in progress"
                }).encode())
                return

            _mark_job_started("paint")
            def run_painter():
                import os
                env = dict(os.environ)
                env["PAINTER_STYLE_MODE"] = style_mode
                env["PAINTER_STYLE_PERSONALITY"] = style_personality
                env["PAINTER_STYLE_SCHEDULE"] = style_schedule_json
                env["PAINTER_VIEWER_URL"] = f"http://127.0.0.1:{VIEWER_PORT}"
                env["PAINTER_TOOL_URL"] = TOOL_URL
                exit_code = -1
                stderr_bytes = b""
                try:
                    result = subprocess.run(
                        [sys.executable, "scripts/auto_paint.py"],
                        cwd=str(Path(__file__).resolve().parent.parent),
                        env=env,
                        capture_output=True
                    )
                    exit_code = result.returncode
                    stderr_bytes = result.stderr or b""
                except Exception as exc:
                    stderr_bytes = f"{type(exc).__name__}: {exc}".encode()
                finally:
                    _mark_job_finished(exit_code, stderr_bytes)
                    _release_busy()
            Thread(target=run_painter, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": "Painting started"}).encode())

        elif path == "/api/suggest_morph":
            # Proxy to tool-server /tool/plan_style_schedule so the browser
            # stays same-origin (viewer:8080 vs tool-server:8765 would
            # otherwise trigger CORS; tool server doesn't send CORS headers).
            import urllib.request
            import urllib.error
            try:
                forward_payload = body if body else b"{}"
                req = urllib.request.Request(
                    TOOL_URL + "/tool/plan_style_schedule",
                    data=forward_payload,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp_body = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp_body)
            except urllib.error.URLError as exc:
                # Connection refused, DNS, socket errors — treat as tool-server-down.
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": f"tool server not reachable on :8765 ({exc.reason})"
                }).encode())
            except TimeoutError:
                self.send_response(504)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "suggest_morph timed out"
                }).encode())
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": f"suggest_morph failed: {type(exc).__name__}: {exc}"
                }).encode())

        elif path == "/api/paint_duet":
            # Validate body, dump current target to /tmp, spawn scripts/duet.py
            # as a subprocess. Busy lock is held until the subprocess exits.
            if not STATE["target_png"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "no target loaded — load an image before running a duet"
                }).encode())
                return
            try:
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {}
            persona_a = (payload.get("persona_a") or "").strip()
            persona_b = (payload.get("persona_b") or "").strip()
            if not persona_a:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "persona_a is required"}).encode())
                return
            if not persona_b:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "persona_b is required"}).encode())
                return
            if persona_a == persona_b:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "duet requires two different personas"
                }).encode())
                return
            # Lazy-import persona allowlist once, cache on the server instance.
            if not hasattr(self.server, "_persona_set_cache"):
                try:
                    _scripts = Path(__file__).resolve().parent
                    if str(_scripts) not in sys.path:
                        sys.path.insert(0, str(_scripts))
                    from paint_lib.duet import PERSONAS as _PERSONAS
                    self.server._persona_set_cache = set(_PERSONAS.keys())
                except Exception as exc:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"failed to load persona registry: "
                                 f"{type(exc).__name__}: {exc}"
                    }).encode())
                    return
            persona_set = self.server._persona_set_cache
            for name, label in ((persona_a, "persona_a"), (persona_b, "persona_b")):
                if name not in persona_set:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"unknown persona: {name!r} "
                                 f"(available: {sorted(persona_set)})"
                    }).encode())
                    return
            try:
                max_turns = int(payload.get("max_turns", 6))
            except Exception:
                max_turns = 6
            max_turns = max(2, min(20, max_turns))

            # All validation complete. Dump current target to /tmp and spawn subprocess.
            target_path = Path("/tmp/painter_duet_target.png")
            target_path.write_bytes(STATE["target_png"])

            import subprocess
            # Claim lock atomically before spawning.
            if not _try_claim_busy():
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "a paint run is already in progress"
                }).encode())
                return

            _mark_job_started("duet")
            def run_duet():
                import os
                env = dict(os.environ)
                repo_root = Path(__file__).resolve().parent.parent
                pp = env.get("PYTHONPATH", "")
                parts = [str(repo_root / "src"), str(repo_root / "scripts")]
                env["PYTHONPATH"] = os.pathsep.join(parts + ([pp] if pp else []))
                env["PAINTER_VIEWER_URL"] = f"http://127.0.0.1:{VIEWER_PORT}"
                env["PAINTER_TOOL_URL"] = TOOL_URL
                exit_code = -1
                stderr_bytes = b""
                try:
                    result = subprocess.run(
                        [sys.executable, "scripts/duet.py",
                         str(target_path),
                         "--personas", f"{persona_a},{persona_b}",
                         "--max-turns", str(max_turns),
                         "--seed", "42"],
                        cwd=str(repo_root),
                        env=env,
                        capture_output=True,
                    )
                    exit_code = result.returncode
                    stderr_bytes = result.stderr or b""
                except Exception as exc:
                    stderr_bytes = f"{type(exc).__name__}: {exc}".encode()
                finally:
                    _mark_job_finished(exit_code, stderr_bytes)
                    _release_busy()
            Thread(target=run_duet, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": "Duet started"}).encode())

        elif path == "/api/morph_preview":
            # POST {"contrast_boost":f, "complementary_shadow":f, "van_gogh_bias":f,
            #        "tenebrism_bias":f, "pointillism_bias":f}
            # Re-paints current target with override params and returns SSIM.
            if not STATE["target_png"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "no target loaded"}).encode())
                return
            try:
                params = json.loads(body) if body else {}
                contrast_boost = float(params.get("contrast_boost", 0.25))
                complementary_shadow = float(params.get("complementary_shadow", 0.12))
                van_gogh_bias = float(params.get("van_gogh_bias", 0.0))
                tenebrism_bias = float(params.get("tenebrism_bias", 0.0))
                pointillism_bias = float(params.get("pointillism_bias", 0.0))

                # Derive style_mode: pick highest bias if >= 0.2, else None
                bias_map = {
                    "van_gogh": van_gogh_bias,
                    "tenebrism": tenebrism_bias,
                    "pointillism": pointillism_bias,
                }
                best_style, best_val = max(bias_map.items(), key=lambda kv: kv[1])
                style_mode = best_style if best_val >= 0.2 else None

                # Write target to a temp file
                import tempfile, time as _time
                target_bytes = STATE["target_png"]
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                    tf.write(target_bytes)
                    tmp_path = tf.name

                # All validation complete. Claim lock atomically before starting work.
                if not _try_claim_busy():
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": "a paint run is already in progress"
                    }).encode())
                    import os as _os
                    try:
                        _os.unlink(tmp_path)
                    except Exception:
                        pass
                    return

                t0 = _time.time()
                try:
                    # Clear canvas first
                    run_async(async_clear())

                    import sys as _sys
                    _scripts_dir = str(Path(__file__).resolve().parent)
                    if _scripts_dir not in _sys.path:
                        _sys.path.insert(0, _scripts_dir)
                    from paint_lib import auto_paint as _auto_paint
                    result = _auto_paint(
                        tmp_path,
                        seed=42,
                        verbose=False,
                        contrast_boost=contrast_boost,
                        complementary_shadow=complementary_shadow,
                        style_mode=style_mode,
                    )
                    duration_s = _time.time() - t0

                    # Grab SSIM from viewer state (updated by auto_paint via strokes)
                    ssim_val = None
                    if STATE.get("score") and STATE["score"]:
                        ssim_val = STATE["score"].get("ssim")

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "ok": True,
                        "ssim": ssim_val,
                        "duration_s": round(duration_s, 2),
                        "style_mode": style_mode,
                    }).encode())
                finally:
                    _release_busy()
                    import os as _os
                    try:
                        _os.unlink(tmp_path)
                    except Exception:
                        pass
            except Exception as e:
                _release_busy()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif path == "/api/target":
            # Optional ?fit=crop|letterbox|auto
            qs = urlparse(self.path).query
            fit_mode = "crop"
            if qs:
                from urllib.parse import parse_qs
                fit_mode = parse_qs(qs).get("fit", ["crop"])[0]
                if fit_mode not in ("crop", "letterbox", "auto"):
                    fit_mode = "crop"
            content_type = self.headers.get("Content-Type", "")
            if "multipart" in content_type:
                png_bytes, filename = _parse_multipart_file(body, content_type)
                if png_bytes is not None:
                    run_async(async_set_target(png_bytes, filename, fit_mode=fit_mode))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "filename": filename, "fit": fit_mode}).encode())
                else:
                    self.send_response(400)
                    self.end_headers()
            else:
                run_async(async_set_target(body, fit_mode=fit_mode))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "fit": fit_mode}).encode())

        else:
            self.send_response(404)
            self.end_headers()


# HTML UI extracted to viewer/index.html (Path 2 of the CODE_REVIEW cleanup).
# Read at import time; change the file on disk without restarting Python
# is out of scope (the existing viewer had no hot-reload either).
_INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
try:
    INDEX_HTML = _INDEX_HTML_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    raise RuntimeError(
        f"viewer/index.html not found at {_INDEX_HTML_PATH}. "
        f"Did you delete the frontend? See Path 2 in CODE_REVIEW.md."
    )


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="127.0.0.1",
                    help="Bind address. Default 127.0.0.1 (localhost-only). "
                         "Use 0.0.0.0 to expose on the LAN (UNSAFE — the viewer "
                         "will serve uploaded targets to any peer).")
    p.add_argument("--size", type=int, default=512,
                    help="canvas size NxN (512 default, 1024 for hi-res)")
    p.add_argument("--renderer", choices=["browser", "pil"], default="browser",
                    help="browser: Playwright+canvas (full fidelity). "
                          "pil: server-side local_renderer (no Chromium needed).")
    p.add_argument("--tool-url", default="http://127.0.0.1:8765",
                   help="URL of the tool server (default http://127.0.0.1:8765). "
                        "Set when running the tool server on a non-default port.")
    args = p.parse_args()
    global CANVAS_SIZE, LOOP, RENDERER, TOOL_URL, VIEWER_PORT
    CANVAS_SIZE = int(args.size)
    RENDERER = args.renderer
    TOOL_URL = args.tool_url
    VIEWER_PORT = int(args.port)
    print(f"[viewer] canvas size: {CANVAS_SIZE}×{CANVAS_SIZE} · renderer: {RENDERER}")
    if RENDERER == "pil":
        _pil_clear()
    loop = asyncio.new_event_loop()
    LOOP = loop

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    Thread(target=run_loop, daemon=True).start()

    if RENDERER == "browser":
        run_async(get_browser())
    else:
        print("[viewer] pil mode — skipping Playwright/Chromium init")
    run_async(refresh_state())

    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"[viewer] http://{args.host}:{args.port}")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[viewer] WARNING: binding on {args.host} exposes the canvas "
              f"to the network. Uploaded targets are reachable over HTTP.")
    print(f"[viewer] Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
