"""Optional headless-browser re-check for pages that look blank before JavaScript runs.

Needs `pip install playwright && playwright install chromium`.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def rendered_text_lengths(urls: list[str], timeout: float = 15.0) -> dict[str, int]:
    """Visible text length of each page after rendering; missing keys mean the render failed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("--render-blank needs playwright; skipping browser re-check")
        return {}

    out: dict[str, int] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            for url in urls:
                try:
                    page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                    text = page.evaluate("() => document.body ? document.body.innerText : ''")
                    media = page.evaluate(
                        "() => document.querySelectorAll('img,svg,video,canvas,iframe').length")
                    out[url] = len(" ".join(text.split())) + (30 if media else 0)
                except Exception as exc:
                    log.info("Render failed for %s: %s", url, exc)
        finally:
            browser.close()
    return out
