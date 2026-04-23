from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from playwright.async_api import Page, async_playwright

CANVAS_HTML = Path(__file__).resolve().parents[2] / "canvas" / "index.html"


class PainterBrowser:
    def __init__(self, page: Page):
        self.page = page

    async def clear(self) -> None:
        await self.page.evaluate("() => window.painter.clear()")

    async def draw_stroke(self, spec: dict[str, Any]) -> None:
        await self.page.evaluate("(s) => window.painter.drawStroke(s)", spec)

    async def draw_strokes(self, strokes: list[dict[str, Any]]) -> int:
        """Batch stroke application — one round-trip instead of N."""
        if not strokes:
            return 0
        return await self.page.evaluate("(xs) => window.painter.drawStrokes(xs)", strokes)

    async def snapshot(self) -> str:
        """Capture an in-memory snapshot for later rollback. Returns an id."""
        return await self.page.evaluate("() => window.painter.snapshot()")

    async def restore(self, snapshot_id: str) -> bool:
        return await self.page.evaluate("(id) => window.painter.restore(id)", snapshot_id)

    async def drop_snapshot(self, snapshot_id: str) -> bool:
        return await self.page.evaluate("(id) => window.painter.dropSnapshot(id)", snapshot_id)

    async def screenshot_png(self) -> bytes:
        b64 = await self.page.evaluate("() => window.painter.getPNG()")
        return base64.b64decode(b64)

    async def save_png(self, path: str | Path) -> None:
        Path(path).write_bytes(await self.screenshot_png())


@asynccontextmanager
async def painter_browser(headless: bool = True) -> AsyncIterator[PainterBrowser]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()
        await page.goto(CANVAS_HTML.as_uri())
        await page.wait_for_function("() => window.painter && window.painter.drawStrokes")
        try:
            yield PainterBrowser(page)
        finally:
            await browser.close()
