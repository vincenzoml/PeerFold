"""Native window UI for PeerFold (pywebview)."""

from __future__ import annotations

import sys


def webview_available() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except ImportError:
        return False


def open_webview(url: str, title: str) -> None:
    import webview

    webview.create_window(
        title,
        url,
        width=1440,
        height=900,
        min_size=(720, 480),
    )
    webview.start()


def open_webview_or_browser(url: str, title: str) -> str:
    """Open the UI; returns 'webview' or 'browser'."""
    if webview_available():
        try:
            open_webview(url, title)
            return "webview"
        except Exception as exc:
            print(f"PeerFold: embedded window failed ({exc}); using system browser.", file=sys.stderr)

    import webbrowser

    webbrowser.open(url)
    return "browser"
