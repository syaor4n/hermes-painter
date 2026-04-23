"""HTTP tool server: dispatcher, cleanup, CLI entry point.

``ToolHandler`` is a minimal JSON-RPC-ish dispatcher over
``http.server.SimpleHTTPRequestHandler`` — it looks each POST path up in
``TOOLS`` and calls the handler with the decoded JSON body. ``main``
parses CLI flags (``--port`` / ``--host`` / ``--viewer``) and rebinds
``_common.VIEWER_URL`` at startup so ``_viewer_get`` / ``_viewer_post``
see the right upstream.
"""
from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import _common
from ._common import ViewerUnavailable
from .manifest import MANIFEST, TOOLS


class ToolHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _reply(self, status: int, obj) -> None:
        body = json.dumps(obj).encode() if not isinstance(obj, bytes) else obj
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/tool/manifest":
            return self._reply(200, {"tools": MANIFEST})
        if path == "/":
            return self._reply(200, {"tools": sorted(TOOLS.keys()), "viewer": _common.VIEWER_URL})
        self._reply(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/tool/"):
            return self._reply(404, {"error": "not a tool path"})
        name = path[len("/tool/") :]
        fn = TOOLS.get(name)
        if fn is None:
            return self._reply(404, {"error": f"unknown tool: {name}"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            args = json.loads(body) if body else {}
            out = fn(args)
            return self._reply(200, out)
        except ViewerUnavailable as e:
            return self._reply(503, {"error": str(e), "type": "ViewerUnavailable"})
        except KeyError as e:
            return self._reply(400, {"error": f"missing argument: {e}", "type": "KeyError"})
        except Exception as e:
            return self._reply(400, {"error": str(e), "type": type(e).__name__})


def _cleanup_tmp() -> None:
    """Remove stale /tmp/painter_*.png from previous sessions (#3)."""
    import glob
    for p in glob.glob("/tmp/painter_*.png"):
        try:
            Path(p).unlink()
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="Bind address. Default 127.0.0.1 (localhost-only). "
                         "Use 0.0.0.0 to expose on the LAN (UNSAFE — tool layer "
                         "can read files outside the allowlist via load_target).")
    ap.add_argument("--viewer", type=str, default=_common.VIEWER_URL)
    ap.add_argument("--no-cleanup", action="store_true", help="keep old /tmp PNGs")
    args = ap.parse_args()
    # Rebind the shared viewer URL so every handler sees the CLI override.
    _common.VIEWER_URL = args.viewer
    if not args.no_cleanup:
        _cleanup_tmp()
    server = ThreadingHTTPServer((args.host, args.port), ToolHandler)
    print(f"[hermes_tools] listening on http://{args.host}:{args.port}")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"[hermes_tools] WARNING: binding on {args.host} exposes the tool "
              f"API to the network. Set a firewall rule or use --host 127.0.0.1.")
    print(f"[hermes_tools] proxying canvas state via viewer at {_common.VIEWER_URL}")
    print(f"[hermes_tools] GET /tool/manifest for the full tool list")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
