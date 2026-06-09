#!/usr/bin/env python3
"""Capture a PeerFold UI screenshot for the GitHub Pages site (fictional demo PDF only)."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshot.png"
DEMO = ROOT / "docs" / "demo.pdf"
PORT = 18765


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_demo_pdf.py")], check=True)
    if not DEMO.is_file():
        raise SystemExit(f"Demo PDF missing: {DEMO}")

    from peerfold.core import run_server  # noqa: PLC0415

    def serve() -> None:
        run_server(DEMO, reviewer="RB", port=PORT, open_browser=False)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(1.5)

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit("Install dev deps: pip install -e '.[dev]' && playwright install chromium") from exc

    url = f"http://127.0.0.1:{PORT}/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".comment-card", timeout=15000)
        page.wait_for_timeout(800)
        # Show an active highlight + comment thread in the pane.
        page.locator(".comment-card").first.click()
        page.wait_for_timeout(400)
        page.locator(".highlight-group.active, .highlight-group").first.click()
        page.wait_for_timeout(600)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT), full_page=False)
        browser.close()

    # Autosave writes an annotated copy beside the demo PDF — discard it.
    for sidecar in DEMO.parent.glob(f"{DEMO.stem}_*-*.pdf"):
        sidecar.unlink(missing_ok=True)

    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
