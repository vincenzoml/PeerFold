#!/usr/bin/env python3
"""Reproduce pywebview save-dialog deadlock on macOS (for manual pdb inspection).

Run from repo root:
    .venv/bin/python scripts/debug_export_dialog.py

On macOS main thread, pywebview's create_file_dialog() schedules AppHelper.callAfter
then blocks on a semaphore. Because the main run loop is blocked, the dialog never
opens and the process beachballs.

PeerFold avoids this by calling NSSavePanel.runModal() on the main thread and
pywebview.create_file_dialog only from worker threads (JS API / export worker).
"""

from __future__ import annotations

import sys
import threading
import time


def _demo_pywebview_deadlock() -> None:
    import webview

    window = webview.create_window("Export dialog debug", html="<p>debug</p>", js_api=object())

    def on_start() -> None:
        def hang_forever() -> None:
            print(f"[main] create_file_dialog on thread={threading.current_thread().name}", flush=True)
            # Uncomment the next line and relaunch to watch the beachball under pdb:
            # import pdb; pdb.set_trace()
            window.create_file_dialog(webview.SAVE_DIALOG, save_filename="comments.md")
            print("[main] dialog returned (unexpected if deadlocked)", flush=True)

        threading.Timer(0.5, hang_forever).start()

    webview.start(on_start)


def _demo_safe_worker() -> None:
    import webview

    from peerfold.native_dialogs import save_text_file

    window = webview.create_window("Safe export debug", html="<p>debug</p>", js_api=object())

    def on_start() -> None:
        def worker() -> None:
            print(f"[worker] save_text_file on thread={threading.current_thread().name}", flush=True)
            result = save_text_file(window, "comments.md", "# PeerFold export test\n", "markdown")
            print(f"[worker] result={result}", flush=True)

        threading.Thread(target=worker, daemon=True).start()

    webview.start(on_start)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "safe"
    if mode == "deadlock":
        _demo_pywebview_deadlock()
    else:
        _demo_safe_worker()
