"""Native window UI for PeerFold (pywebview)."""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse


class WebviewUnavailableError(RuntimeError):
    """Native window could not be opened."""


def ssh_session() -> bool:
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))


def headless_environment() -> bool:
    if ssh_session():
        return True
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return True
    return False


def webview_available() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except ImportError:
        return False


def webview_unavailable_help(*, url: str | None = None, detail: str | None = None) -> str:
    lines = [
        "PeerFold couldn't open a native window.",
        "",
    ]
    if ssh_session():
        lines.append("You're on SSH — there's no local display for a desktop window.")
        lines.append("Use the web UI instead:")
    else:
        lines.append("Open PeerFold in your browser instead:")
    lines.append("")
    lines.append("  peerfold … --web")
    lines.append("")
    if url and ssh_session():
        parsed = urlparse(url)
        port = parsed.port or 80
        lines.append("Then open the URL in your laptop browser. Forward the port, e.g.:")
        lines.append(f"  ssh -L {port}:127.0.0.1:{port} you@host")
        lines.append(f"  → http://127.0.0.1:{port}/")
    elif url:
        lines.append(f"PeerFold will print a local URL (e.g. {url}).")
    if detail:
        lines.append("")
        lines.append(f"({detail})")
    return "\n".join(lines)


def open_webview(url: str, title: str) -> None:
    import webview

    webview.create_window(
        title,
        url,
        width=1440,
        height=900,
        min_size=(720, 480),
        background_color="#0c0c0e",
        text_select=True,
    )
    webview.start(debug=False)


def open_webview_strict(url: str, title: str) -> None:
    """Open native window or raise — never falls back to the system browser."""
    if not webview_available():
        raise WebviewUnavailableError("pywebview is not installed")
    try:
        open_webview(url, title)
    except Exception as exc:
        raise WebviewUnavailableError(str(exc)) from exc


def launch_web_ui(url: str) -> None:
    """Serve via the system browser, with SSH-friendly instructions when needed."""
    print(f"\n  {url}\n")
    if ssh_session():
        parsed = urlparse(url)
        port = parsed.port or 80
        print("SSH: open that URL in your laptop browser (forward the port if needed):")
        print(f"  ssh -L {port}:127.0.0.1:{port} you@host")
        return
    open_url(url)


def open_url(url: str) -> None:
    """Open a local PeerFold URL in the default browser."""
    if sys.platform == "darwin":
        subprocess.Popen(
            ["open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return

    import webbrowser

    webbrowser.open(url)
