"""Native window UI for PeerFold (pywebview)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from peerfold.icons import icon_png
from peerfold.recent_files import add as add_recent_file
from peerfold.recent_files import list_paths as list_recent_paths


class WebviewUnavailableError(RuntimeError):
    """Native window could not be opened."""


class PeerFoldApi:
    """JS bridge for native file dialogs and application menus."""

    def __init__(self) -> None:
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    def pick_pdf(self) -> str | None:
        import webview

        windows = webview.windows
        if not windows:
            return None
        result = windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("PDF files (*.pdf)", "All files (*.*)"),
        )
        if not result:
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        return str(Path(path).expanduser().resolve())

    def open_url(self, url: str) -> None:
        open_url(url)

    def menu_open(self) -> None:
        path = self.pick_pdf()
        if path:
            self._open_path(path)

    def open_recent(self, path: str) -> None:
        self._open_path(path)

    def document_opened(self, path: str) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved.is_file():
            add_recent_file(resolved)
            refresh_application_menu(self)

    def menu_undo(self) -> None:
        self._dispatch("undo")

    def menu_redo(self) -> None:
        self._dispatch("redo")

    def check_for_updates(self) -> None:
        self._dispatch("check-updates")

    def show_about(self) -> None:
        from peerfold import __version__

        message = (
            f"PeerFold {__version__}\n\n"
            "PDF review with standard highlight annotations.\n\n"
            "https://vincenzoml.github.io/PeerFold/"
        )
        if sys.platform == "darwin":
            import AppKit

            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_(f"PeerFold {__version__}")
            alert.setInformativeText_(
                "PDF review with standard highlight annotations.\n"
                "https://vincenzoml.github.io/PeerFold/"
            )
            alert.addButtonWithTitle_("OK")
            alert.runModal()
            return
        if self._window:
            self._window.create_confirmation_dialog("About PeerFold", message)

    def _dispatch(self, action: str) -> None:
        if not self._window:
            return
        payload = json.dumps(action)
        self._window.evaluate_js(
            f'window.dispatchEvent(new CustomEvent("peerfold-menu", '
            f"{{detail: {{action: {payload}}}}}))"
        )

    def _open_path(self, path: str) -> None:
        if not self._window:
            return
        payload = json.dumps(path)
        self._window.evaluate_js(
            f'window.dispatchEvent(new CustomEvent("peerfold-open-path", '
            f"{{detail: {payload}}}))"
        )


def build_application_menu(api: PeerFoldApi):
    from webview.menu import Menu, MenuAction, MenuSeparator

    recent_paths = list_recent_paths()
    recent_items: list = []
    if recent_paths:
        for path in recent_paths:
            recent_items.append(
                MenuAction(path.name, (lambda p=str(path): api.open_recent(p)))
            )
    else:
        recent_items.append(MenuAction("(Empty)", lambda: None))

    file_menu = Menu(
        "File",
        [
            MenuAction("Open…", api.menu_open),
            MenuSeparator(),
            Menu("Open Recent", recent_items),
        ],
    )

    return [
        Menu(
            "__app__",
            [
                MenuAction("Check for Updates…", api.check_for_updates),
            ],
        ),
        file_menu,
        Menu(
            "Help",
            [
                MenuAction("About PeerFold", api.show_about),
                MenuAction("Check for Updates…", api.check_for_updates),
            ],
        ),
    ]


def refresh_application_menu(api: PeerFoldApi) -> None:
    from peerfold.macos_menu import refresh_open_recent_menu

    refresh_open_recent_menu(list_recent_paths(), api.open_recent)


def _set_application_icon() -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(icon_png(512)))
        if image is not None:
            AppKit.NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        pass


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


def _bind_native_drop_paths(window) -> None:
    """Forward full paths from native drag-drop (macOS/Linux GTK/Qt) to the UI."""
    from webview.dom import DOMEventHandler

    def on_drop(event: dict) -> None:
        for file in event.get("dataTransfer", {}).get("files") or []:
            raw = file.get("pywebviewFullPath")
            if not raw:
                continue
            path = Path(str(raw)).expanduser()
            if path.suffix.lower() != ".pdf":
                continue
            payload = json.dumps(str(path.resolve()))
            window.evaluate_js(
                "window.dispatchEvent("
                f'new CustomEvent("peerfold-drop-path", {{detail: {payload}}})'
                ")"
            )
            return

    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


def open_webview(url: str, title: str) -> None:
    import webview

    api = PeerFoldApi()
    window = webview.create_window(
        title,
        url,
        width=1440,
        height=900,
        min_size=(720, 480),
        background_color="#0c0c0e",
        text_select=True,
        js_api=api,
    )
    api.set_window(window)

    def on_start() -> None:
        try:
            _set_application_icon()
            _bind_native_drop_paths(window)
            refresh_application_menu(api)
        except Exception:
            pass

    webview.start(on_start, menu=build_application_menu(api), debug=False)


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
