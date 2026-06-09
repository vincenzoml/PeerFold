#!/usr/bin/env python3
"""Capture a PeerFold UI screenshot for the GitHub Pages site."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "hero.png"
DEMO = ROOT / "docs" / "demo.pdf"
PORT = 18765

_SRC = ROOT / "src"
_SCRIPTS = Path(__file__).resolve().parent
if _SRC.is_dir():
    sys.path = [p for p in sys.path if p not in {str(_SRC), str(_SCRIPTS)}]
    sys.path.insert(0, str(_SRC))


def capture_hero(url: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit("Install dev deps: pip install -e '.[dev]' && playwright install chromium") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page.emulate_media(color_scheme="dark")
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".comment-card", timeout=15000)
        page.wait_for_timeout(600)
        page.locator(".comment-card").first.click(timeout=8000)
        page.wait_for_timeout(700)
        png = page.screenshot(type="png")
        browser.close()
    return png


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_demo_pdf.py")], check=True)
    if not DEMO.is_file():
        raise SystemExit(f"Demo PDF missing: {DEMO}")

    from peerfold.core import run_server  # noqa: PLC0415

    def serve() -> None:
        run_server(DEMO, reviewer="RB", port=PORT, ui="none")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(1.5)

    url = f"http://127.0.0.1:{PORT}/"
    png = capture_hero(url)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    if b"acTL" in png or b"fcTL" in png:
        raise SystemExit("Expected a plain PNG, got animated chunks")
    print(f"Wrote {OUT} ({len(png)} bytes)")

    for sidecar in DEMO.parent.glob(f"{DEMO.stem}_*-*.pdf"):
        sidecar.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
