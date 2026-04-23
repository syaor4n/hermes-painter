"""Manual end-to-end test: draw a handful of strokes, save the result.

Usage:
    pip install -e .
    playwright install chromium
    python scripts/demo_stroke.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from painter.browser import painter_browser
from painter.executor import execute_plan

DEMO_PLAN = {
    "strokes": [
        {"type": "fill_rect", "x": 0, "y": 0, "w": 512, "h": 300, "color": "#cfe8ff"},
        {"type": "fill_rect", "x": 0, "y": 300, "w": 512, "h": 212, "color": "#f4e8d0"},
        {"type": "fill_circle", "x": 400, "y": 120, "r": 48, "color": "#ffd34d"},
        {"type": "fill_poly",
         "points": [[0, 360], [140, 300], [260, 360], [380, 290], [512, 340], [512, 512], [0, 512]],
         "color": "#4a6b3a"},
        {"type": "bezier",
         "points": [[220, 420], [235, 280], [285, 280], [300, 420]],
         "color": "#6b3e1a", "width": 14},
        {"type": "fill_circle", "x": 260, "y": 280, "r": 60, "color": "#2e5a2a"},
        {"type": "line", "points": [[0, 511], [512, 511]], "color": "#3a2a1a", "width": 4},
    ],
}

OUT = Path(__file__).resolve().parent.parent / "runs" / "demo.png"


async def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    async with painter_browser(headless=True) as browser:
        await browser.clear()
        await execute_plan(browser, DEMO_PLAN)
        await browser.save_png(OUT)
    print(f"saved {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
