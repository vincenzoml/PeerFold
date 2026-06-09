#!/usr/bin/env python3
"""Capture a PaperTrail UI screenshot for the GitHub Pages site."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshot.png"
SAMPLE = ROOT / "tests" / "fixtures" / "sample.pdf"
DEMO = Path.home() / "data/local/repos/papers/ISOLA26-DIGITAL-TWINS/review-builds/main-2026-06-09-95908b8.pdf"
PORT = 18765


def main() -> None:
    pdf = DEMO if DEMO.is_file() else SAMPLE
    if not pdf.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_sample_pdf.py")], check=True)
        pdf = SAMPLE

    from papertrail.core import run_server  # noqa: PLC0415

    def serve() -> None:
        run_server(pdf, reviewer="VC", port=PORT, open_browser=False)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(1.2)

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit("Install dev deps: pip install -e '.[dev]' && playwright install chromium") from exc

    url = f"http://127.0.0.1:{PORT}/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1500)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT), full_page=False)
        browser.close()

    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
