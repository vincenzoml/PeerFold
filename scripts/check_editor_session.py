#!/usr/bin/env python3
"""Run the comment-editor harness inside the real desktop engine.

PeerFold ships in pywebview, which on macOS is WKWebView. Focus and selection
are exactly where engines differ, and the bug this guards against -- the caret
leaving the comment box when a save fires -- was invisible in every check that
asked only who had focus. So the harness (tests/browser/editor_session_harness.js)
runs here, in a real window, against a real server on a throwaway copy of a PDF:

    python scripts/check_editor_session.py path/to/some.pdf

A window appears for about thirty seconds, types into comments on its own, and
closes. The process exits 0 when every check passes and prints each result.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "browser" / "editor_session_harness.js"


def start_server(pdf: Path) -> tuple[subprocess.Popen, str]:
    # The tree this script lives in, not whatever the venv has installed: the
    # point is to test the code beside it, including an old checkout.
    env = dict(os.environ, PEERFOLD_DEV="1", PEERFOLD_LOCAL=str(ROOT),
               PYTHONPATH=str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    proc = subprocess.Popen(
        [sys.executable, "-m", "peerfold", str(pdf), "--reviewer", "HARNESS", "--web"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + 60
    for line in proc.stdout:
        match = re.search(r"http://127\.0\.0\.1:\d+/", line)
        if match:
            return proc, match.group(0)
        if time.time() > deadline:
            break
    proc.kill()
    raise SystemExit("the PeerFold server did not announce a URL")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).expanduser().resolve()
    work = Path(tempfile.mkdtemp(prefix="peerfold-harness-"))
    pdf = work / "harness.pdf"
    shutil.copy(source, pdf)                       # never the person's own file
    server, url = start_server(pdf)

    import webview

    outcome: dict = {}

    def drive(window) -> None:
        try:
            try:                                   # a key window, so focus is real
                from AppKit import NSApplication
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass
            for _ in range(120):
                if window.evaluate_js("Boolean(window.__peerfold)"):
                    break
                time.sleep(0.25)
            else:
                outcome["error"] = "the page never exposed the dev handle"
                return
            time.sleep(1.0)
            window.evaluate_js(HARNESS.read_text(encoding="utf-8"))
            window.evaluate_js("window.__harnessResult = null; window.__runEditorHarness();")
            for _ in range(240):
                raw = window.evaluate_js("window.__harnessResult && JSON.stringify(window.__harnessResult)")
                if raw:
                    outcome.update(json.loads(raw))
                    break
                time.sleep(0.5)
            else:
                outcome["error"] = "the harness did not finish in two minutes"
        except Exception as exc:                   # report, never hang
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            window.destroy()

    window = webview.create_window("PeerFold editor harness", url, width=1200, height=820)
    try:
        webview.start(drive, window)
    finally:
        server.terminate()
        shutil.rmtree(work, ignore_errors=True)

    if "error" in outcome:
        print("ERROR:", outcome["error"])
        return 2
    for r in outcome.get("results", []):
        mark = "ok  " if r["ok"] else "FAIL"
        extra = {k: v for k, v in r.items() if k not in ("name", "ok")}
        print(f"{mark} {r['name']}" + (f"   {extra}" if extra and not r["ok"] else ""))
    print(f"\n{outcome.get('passed', 0)} passed, {outcome.get('failed', 0)} failed")
    return 0 if outcome.get("failed") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
