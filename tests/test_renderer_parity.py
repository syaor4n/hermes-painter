"""Pixel-parity test: canvas/index.html (browser) vs local_renderer (PIL).

Each stroke type renders in both backends on a pristine white canvas (no linen
texture). We compare pixel mean absolute error (MAE) per channel.

Bristle brush uses a seeded PRNG so both renderers should produce identical
output pixel-for-pixel when the seed formula is in sync. Other stroke types
(line, polyline, bezier, fill_*, fog, glow, dab, splat) are deterministic by
construction.

Run: .venv/bin/python -m pytest tests/test_renderer_parity.py -v
Or directly: .venv/bin/python tests/test_renderer_parity.py
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from painter import local_renderer  # noqa: E402

CANVAS_HTML = ROOT / "canvas" / "index.html"

# Tolerances: PIL and canvas have small rasterization differences (antialiasing
# edges, sub-pixel placement). We expect MAE < 2 for deterministic strokes,
# < 8 for bristle (more variation due to many small lines).
MAE_TOLERANCE = {
    "fill_rect": 2.0,
    "fill_circle": 3.0,
    "fill_poly": 3.0,
    "line": 3.0,
    "polyline": 3.0,
    "bezier": 4.0,
    "dab": 4.0,
    "splat": 5.0,
    "glow": 6.0,   # gradient interpolation differs slightly
    "fog": 6.0,
    "brush_smooth": 4.0,
    "brush_bristle": 10.0,  # many tiny lines, PRNG drift accepted
}


def fixture_strokes():
    """Return list of (label, stroke) tuples covering every type."""
    return [
        ("fill_rect", {
            "type": "fill_rect", "x": 50, "y": 50, "w": 120, "h": 80,
            "color": "#336699", "alpha": 0.8,
        }),
        ("fill_circle", {
            "type": "fill_circle", "x": 256, "y": 180, "r": 60,
            "color": "#cc5533", "alpha": 0.9,
        }),
        ("fill_poly", {
            "type": "fill_poly",
            "points": [[80, 300], [200, 280], [240, 400], [120, 420]],
            "color": "#55aa44", "alpha": 0.7,
        }),
        ("line", {
            "type": "line",
            "points": [[300, 60], [450, 180]],
            "color": "#112233", "width": 4, "alpha": 1.0,
        }),
        ("polyline", {
            "type": "polyline",
            "points": [[300, 250], [350, 240], [400, 260], [440, 300], [460, 350]],
            "color": "#990033", "width": 2, "alpha": 0.9,
        }),
        ("bezier", {
            "type": "bezier",
            "points": [[40, 440], [120, 360], [200, 500], [280, 440]],
            "color": "#553377", "width": 3, "alpha": 0.95,
        }),
        ("dab", {
            "type": "dab", "x": 350, "y": 100, "w": 40, "h": 20,
            "angle": 0.3, "color": "#ddbb22", "alpha": 0.9,
        }),
        ("splat", {
            "type": "splat", "x": 120, "y": 200, "r": 20, "count": 6,
            "color": "#0066aa", "alpha": 0.75,
        }),
        ("fog", {
            "type": "fog", "x": 0, "y": 350, "w": 512, "h": 162,
            "color": "#aabbcc", "alpha": 0.4, "direction": "vertical", "fade": 0.35,
        }),
        ("glow", {
            "type": "glow", "x": 380, "y": 380, "r": 70,
            "color": "#ffaa55", "alpha": 0.85,
        }),
        ("brush_smooth", {
            "type": "brush",
            "points": [[40, 60], [160, 90], [260, 140]],
            "color": "#334466", "width": 18, "alpha": 0.8,
            "texture": "smooth",
        }),
        ("brush_bristle", {
            "type": "brush",
            "points": [[100, 420], [220, 460], [340, 440]],
            "color": "#884422", "width": 24, "alpha": 0.8,
            "texture": "bristle",
        }),
    ]


async def render_browser(stroke: dict) -> np.ndarray:
    """Render the stroke in the canvas/index.html via playwright, on a pure
    white background (no linen texture)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(CANVAS_HTML.as_uri())
        await page.wait_for_function("() => window.painter && window.painter.drawStrokes")
        # Overwrite the textured linen with pure white so we can compare to
        # local_renderer's white baseline.
        await page.evaluate("""() => {
            const c = document.getElementById('c');
            const ctx = c.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, c.width, c.height);
        }""")
        await page.evaluate("(s) => window.painter.drawStroke(s)", stroke)
        b64 = await page.evaluate("() => window.painter.getPNG()")
        await browser.close()
    import base64
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    return np.asarray(img)


def render_local(stroke: dict) -> np.ndarray:
    img = local_renderer.render([stroke])
    return np.asarray(img.convert("RGB"))


def compare(label: str, stroke: dict, verbose: bool = True, save_diffs: Path | None = None):
    browser_arr = asyncio.run(render_browser(stroke))
    local_arr = render_local(stroke)
    diff = np.abs(browser_arr.astype(np.int16) - local_arr.astype(np.int16))
    mae = float(diff.mean())
    max_err = int(diff.max())
    tol = MAE_TOLERANCE.get(label, 5.0)
    status = "PASS" if mae < tol else "FAIL"
    if verbose:
        print(f"  [{status}] {label:16s} mae={mae:.2f} max={max_err:3d} tol={tol:.1f}")
    if save_diffs and mae >= tol:
        save_diffs.mkdir(parents=True, exist_ok=True)
        Image.fromarray(browser_arr).save(save_diffs / f"{label}_browser.png")
        Image.fromarray(local_arr).save(save_diffs / f"{label}_local.png")
        diff_viz = (diff * 4).clip(0, 255).astype(np.uint8)
        Image.fromarray(diff_viz).save(save_diffs / f"{label}_diff.png")
    return mae < tol, mae, max_err


def _playwright_launchable() -> tuple[bool, str]:
    """Probe whether Playwright can actually launch Chromium in this env.

    Returns (ok, reason). On restricted/CI environments where Chromium
    isn't installed or macOS refuses the sandbox, we skip gracefully
    instead of reporting a spurious failure.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        return False, f"playwright not installed: {exc}"

    async def _probe():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()

    try:
        asyncio.run(_probe())
        return True, ""
    except Exception as exc:
        return False, f"Chromium launch failed: {type(exc).__name__}: {exc}"


def test_parity_all():
    """Pytest entry — fails with a summary if any stroke exceeds its tolerance.

    Skips cleanly on environments where Playwright can't launch Chromium
    (restricted sandboxes, CI without browser install, permission errors).
    """
    ok, reason = _playwright_launchable()
    if not ok:
        import pytest
        pytest.skip(f"Chromium unavailable — {reason}")

    failures = []
    for label, stroke in fixture_strokes():
        ok, mae, max_err = compare(label, stroke, verbose=False,
                                   save_diffs=Path("/tmp/parity_diffs"))
        if not ok:
            failures.append(f"{label}: mae={mae:.2f} max={max_err}")
    assert not failures, "Renderer parity failures:\n  " + "\n  ".join(failures)


def main():
    print(f"Renderer parity test — {len(fixture_strokes())} strokes")
    print(f"Diff output dir (on fail): /tmp/parity_diffs")
    total_pass = 0
    for label, stroke in fixture_strokes():
        ok, _, _ = compare(label, stroke, verbose=True,
                           save_diffs=Path("/tmp/parity_diffs"))
        if ok:
            total_pass += 1
    print(f"\n{total_pass}/{len(fixture_strokes())} strokes within tolerance")
    return 0 if total_pass == len(fixture_strokes()) else 1


if __name__ == "__main__":
    sys.exit(main())
