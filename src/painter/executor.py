from __future__ import annotations

from typing import Any

from .browser import PainterBrowser


async def execute_plan(browser: PainterBrowser, plan: dict[str, Any]) -> int:
    """Apply every stroke in a plan. Returns the number of strokes drawn."""
    strokes = plan.get("strokes", [])
    if not strokes:
        return 0
    return await browser.draw_strokes(strokes)
