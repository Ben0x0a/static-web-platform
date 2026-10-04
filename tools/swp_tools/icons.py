"""icons.py — render the app icon SVG into the PNGs a PWA needs (swp icons).

Defines : render(svg_path) → writes icon-512.png, icon-192.png and
          apple-touch-icon.png (180px) next to the SVG.
Used by : cli.py (`swp icons`), after changing src/icons/icon.svg.
Uses    : Playwright driving the installed Google Chrome (no browser download).

Usage: npx swp icons [src/icons/icon.svg]
"""

import base64
import logging
import pathlib

from playwright.sync_api import sync_playwright

_LOG = logging.getLogger("swp.icons")
SIZES = {"icon-512.png": 512, "icon-192.png": 192, "apple-touch-icon.png": 180}


def render(svg_path: pathlib.Path) -> None:
    data = base64.b64encode(svg_path.read_bytes()).decode()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for filename, size in SIZES.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                f'<body style="margin:0"><img src="data:image/svg+xml;base64,{data}" '
                f'width="{size}" height="{size}" style="display:block"></body>')
            out = svg_path.with_name(filename)
            page.screenshot(path=str(out))
            _LOG.info(f"{out} ({size}x{size})")
        browser.close()
