#!/usr/bin/env python3
"""Capture PeerFold UI screenshots for the GitHub Pages site."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "shots"
HERO = ROOT / "docs" / "hero.png"
DEMO = ROOT / "docs" / "demo.pdf"
SAMPLES = ROOT / "docs" / "sample-papers"
STORE = ROOT / ".screenshot-tmp" / "recent.json"
PORT = 18765

_SRC = ROOT / "src"
_SCRIPTS = Path(__file__).resolve().parent
if _SRC.is_dir():
    sys.path = [p for p in sys.path if p not in {str(_SRC), str(_SCRIPTS)}]
    sys.path.insert(0, str(_SRC))


def patch_recent_store() -> None:
    import peerfold.recent_files as rf  # noqa: PLC0415

    STORE.parent.mkdir(parents=True, exist_ok=True)
    rf._store_path = lambda: STORE  # type: ignore[method-assign]


def seed_sample_pdfs() -> list[Path]:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_demo_pdf.py")], check=True)
    if not DEMO.is_file():
        raise SystemExit(f"Demo PDF missing: {DEMO}")
    SAMPLES.mkdir(parents=True, exist_ok=True)
    paths = [DEMO.resolve()]
    for name in ("manuscript.pdf", "supplement.pdf", "rebuttal.pdf"):
        target = SAMPLES / name
        if not target.is_file():
            shutil.copy(DEMO, target)
        paths.append(target.resolve())
    STORE.write_text(json.dumps([str(p) for p in paths], indent=2) + "\n", encoding="utf-8")
    return paths


def serve(pdf: Path | None, port: int, *, recent_store: Path | None = None) -> subprocess.Popen[bytes]:
    pdf_arg = "None" if pdf is None else f"Path({str(pdf)!r})"
    store_patch = ""
    if recent_store is not None:
        store_patch = f"""
import peerfold.recent_files as rf
rf._store_path = lambda: Path({str(recent_store)!r})
"""
    code = f"""
from pathlib import Path
{store_patch}
from peerfold.core import run_server
run_server({pdf_arg}, reviewer="RB", port={port}, ui="none")
"""
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(_SRC)
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=_SRC,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    time.sleep(1.8)
    if proc.poll() is not None:
        err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace")
        raise SystemExit(f"PeerFold server exited early:\n{err}")
    return proc


def stop_server(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def playwright_page():
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        raise SystemExit(
            "Install dev deps: pip install -e '.[dev]' && playwright install chromium"
        ) from exc
    return sync_playwright()


def write_png(path: Path, png: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    if b"acTL" in png or b"fcTL" in png:
        raise SystemExit(f"Expected a plain PNG, got animated chunks: {path}")
    print(f"Wrote {path} ({len(png)} bytes)")


def release_ports(*ports: int) -> None:
    for port in ports:
        subprocess.run(
            ["sh", "-c", f"lsof -ti :{port} | xargs kill -9 2>/dev/null || true"],
            check=False,
        )


def capture_all() -> None:
    release_ports(PORT, PORT + 1)
    patch_recent_store()
    seed_sample_pdfs()

    with playwright_page() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page.emulate_media(color_scheme="dark")

        welcome_proc = serve(None, PORT, recent_store=STORE)
        page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")
        page.wait_for_selector(".welcome-recent-item", timeout=15000)
        page.wait_for_timeout(500)
        write_png(SHOTS / "01-welcome.png", page.screenshot(type="png"))
        stop_server(welcome_proc)

        review_port = PORT + 1
        review_proc = serve(DEMO, review_port)
        url = f"http://127.0.0.1:{review_port}/"
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector(".comment-card", timeout=15000)
        page.wait_for_timeout(600)

        write_png(SHOTS / "02-workspace.png", page.screenshot(type="png"))

        page.locator(".comment-card .comment-edit-hit").first.click(timeout=8000)
        page.wait_for_function(
            "() => !document.getElementById('comment-editor')?.hidden",
            timeout=8000,
        )
        page.wait_for_selector("#comment-editor-ta", timeout=8000)
        page.wait_for_timeout(500)
        write_png(SHOTS / "03-editor.png", page.screenshot(type="png"))

        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => document.getElementById('comment-editor')?.hidden",
            timeout=8000,
        )
        page.wait_for_timeout(400)
        page.locator("#workspace").click(position={"x": 520, "y": 420}, force=True)
        page.wait_for_timeout(500)
        write_png(SHOTS / "04-annotations.png", page.screenshot(type="png"))

        page.locator("#comments-pane").evaluate("el => { el.scrollTop = 0; }")
        page.wait_for_timeout(300)
        write_png(SHOTS / "05-comments.png", page.screenshot(type="png"))

        browser.close()
        stop_server(review_proc)

    write_png(HERO, (SHOTS / "02-workspace.png").read_bytes())

    for sidecar in DEMO.parent.glob(f"{DEMO.stem}_*-*.pdf"):
        sidecar.unlink(missing_ok=True)
    shutil.rmtree(STORE.parent, ignore_errors=True)


def main() -> None:
    capture_all()


if __name__ == "__main__":
    main()
