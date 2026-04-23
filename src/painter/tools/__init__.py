"""Tool server for an external agent (e.g. Hermes) to drive the painter.

Exposes a flat JSON-RPC-ish HTTP API that is easy to wrap as MCP tools
without pulling a full MCP SDK. Everything maps 1:1 to a single
agent-callable action with well-typed inputs and outputs.

Usage:
  python scripts/hermes_tools.py --port 8765

Endpoints (all POST unless noted):
  POST /tool/load_target    {"path": "targets/foo.jpg"} -> {image_type, metadata}
  POST /tool/draw_strokes   {"strokes": [...]} -> {score, strokes_applied, iteration}
  POST /tool/score_plan     {"strokes": [...]} -> {imagined: {..., delta_ssim}}
  POST /tool/get_heatmap    {} -> PNG bytes (base64 under "png_b64")
  POST /tool/get_regions    {"top": 8} -> {regions: [...]}
  POST /tool/get_state      {} -> {canvas_b64, target_b64, score, iteration}
  POST /tool/dump_canvas    {} -> {path: "/tmp/painter_canvas.png"}   # then Read it
  POST /tool/dump_target    {} -> {path: "/tmp/painter_target.png"}
  POST /tool/dump_heatmap   {} -> {path: "/tmp/painter_heatmap.png"}
  POST /tool/dump_all       {} -> {canvas, target, heatmap} paths
  POST /tool/clear          {} -> {ok}
  POST /tool/snapshot       {} -> {id}
  POST /tool/restore        {"id": "..."} -> {ok}
  POST /tool/list_skills    {"image_type": "..."} -> {skills: [{name, tags, confidence, body}]}
  POST /tool/save_skill     {"name", "body", "scope_types", "tags"} -> {path}
  POST /tool/list_journal   {"n": 20} -> {entries: [...]}
  POST /tool/save_journal_entry {"run","target","final_ssim","note",...} -> {ok}
  POST /tool/read_style     {} -> {body}
  POST /tool/update_style   {"body", "evolution_note"} -> {ok}
  GET  /tool/manifest       -> list of every tool + schema (for MCP wiring)

Separate from viewer.py so you can run the viewer on :8080 for humans and
the tool server on :8765 for the agent. Both share the same canvas via
the viewer — the tool server talks to http://localhost:8080/api/*.

Package layout:
  _common    — viewer HTTP bridge, path allowlist, /tmp dump helpers,
               target array fetch, mask loading, shared filesystem anchors.
  canvas     — viewer-facing primitives: load/draw/score, dumps, palette,
               gaps, sampling, and get/set state.
  analyze    — target inspection: edges, gradients, saliency, segmentation,
               face detection, heuristic critique.
  plans      — stroke-planning passes: edges, details, contours, highlights,
               sculpt corrections, face details, accent preservation.
  memory     — skills/journal/style/reflections + skill promotion loop.
  manifest   — aggregates the TOOLS map and MANIFEST list.
  server     — HTTP dispatcher, /tmp cleanup, CLI entry point.

Re-exports ``TOOLS`` / ``MANIFEST`` / ``main`` at the package root so
callers importing ``painter.tools`` keep working after the split out of
``scripts/hermes_tools.py``.
"""
from .manifest import MANIFEST, TOOLS
from .server import main

__all__ = ["MANIFEST", "TOOLS", "main"]
