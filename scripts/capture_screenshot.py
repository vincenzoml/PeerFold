#!/usr/bin/env python3
"""Capture an animated PeerFold screenshot (APNG) for the GitHub Pages site."""

from __future__ import annotations

import struct
import subprocess
import sys
import threading
import time
import zlib
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "hero.png"
DEMO = ROOT / "docs" / "demo.pdf"
PORT = 18765
FRAME_DELAY_MS = 700

_SRC = ROOT / "src"
_SCRIPTS = Path(__file__).resolve().parent
if _SRC.is_dir():
    sys.path = [p for p in sys.path if p not in {str(_SRC), str(_SCRIPTS)}]
    sys.path.insert(0, str(_SRC))


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _read_png(png_bytes: bytes) -> tuple[bytes, bytes]:
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")
    pos = 8
    ihdr = b""
    idat_parts: list[bytes] = []
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
        pos += 4
        tag = png_bytes[pos : pos + 4]
        pos += 4
        data = png_bytes[pos : pos + length]
        pos += length + 4
        if tag == b"IHDR":
            ihdr = data
        elif tag == b"IDAT":
            idat_parts.append(data)
        elif tag == b"IEND":
            break
    if not ihdr or not idat_parts:
        raise ValueError("Invalid PNG structure")
    return ihdr, b"".join(idat_parts)


def write_apng(frames: list[bytes], path: Path, *, delay_ms: int = FRAME_DELAY_MS) -> None:
    """Write PNG frames as a looping animated PNG (first frame stays PNG-compatible)."""
    if not frames:
        raise ValueError("No frames to write")
    if len(frames) == 1:
        path.write_bytes(frames[0])
        return

    first_ihdr, first_idat = _read_png(frames[0])
    width, height = struct.unpack(">II", first_ihdr[0:8])
    out = BytesIO()
    out.write(b"\x89PNG\r\n\x1a\n")
    out.write(_png_chunk(b"IHDR", first_ihdr))
    out.write(_png_chunk(b"IDAT", first_idat))
    out.write(_png_chunk(b"acTL", struct.pack(">II", len(frames), 0)))

    seq = 0
    for index, frame in enumerate(frames[1:], start=1):
        _, idat = _read_png(frame)
        seq += 1
        fctl = struct.pack(">IIIIIHHBB", seq, width, height, 0, 0, delay_ms, 1000, 1, 0)
        out.write(_png_chunk(b"fcTL", fctl))
        seq += 1
        out.write(_png_chunk(b"fdAT", struct.pack(">I", seq) + idat))

    out.write(_png_chunk(b"IEND", b""))
    path.write_bytes(out.getvalue())


def capture_frames(url: str) -> list[bytes]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit("Install dev deps: pip install -e '.[dev]' && playwright install chromium") from exc

    frames: list[bytes] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page.emulate_media(color_scheme="dark")
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".comment-card", timeout=15000)
        page.wait_for_timeout(600)

        cards = page.locator(".comment-card")
        count = cards.count()
        frames.append(page.screenshot(type="png"))

        for i in range(min(count, 3)):
            if i > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(350)
            cards.nth(i).click(timeout=8000)
            page.wait_for_timeout(500)
            frames.append(page.screenshot(type="png"))

        browser.close()
    return frames


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
    frames = capture_frames(url)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_apng(frames, OUT)
    print(f"Wrote {OUT} ({len(frames)} frames, APNG)")

    for sidecar in DEMO.parent.glob(f"{DEMO.stem}_*-*.pdf"):
        sidecar.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
