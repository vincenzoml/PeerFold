"""Native window UI for PeerFold (pywebview)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

T = TypeVar("T")

from peerfold.icons import icon_png
from peerfold.recent_files import add as add_recent_file
from peerfold.recent_files import clear as clear_recent_files
from peerfold.recent_files import list_paths as list_recent_paths
from peerfold.recent_files import menu_label as recent_menu_label
from peerfold.recent_files import remove as remove_recent_file


class WebviewUnavailableError(RuntimeError):
    """Native window could not be opened."""


def run_on_main_thread(fn: Callable[[], None]) -> None:
    """Schedule work on the AppKit main thread (pywebview menus run off-thread)."""
    if threading.current_thread() is threading.main_thread():
        fn()
        return
    if sys.platform == "darwin":
        from PyObjCTools.AppHelper import callAfter

        callAfter(fn)
        return
    fn()


def run_on_main_thread_sync(fn: Callable[[], T]) -> T:
    """Run on the AppKit main thread and return (for file dialogs)."""
    if threading.current_thread() is threading.main_thread():
        return fn()
    if sys.platform != "darwin":
        return fn()

    import objc
    from Foundation import NSObject

    state: dict[str, Any] = {}

    class Runner(NSObject):
        def runOnMain_(self, _sender) -> None:
            try:
                state["result"] = fn()
            except BaseException as exc:
                state["error"] = exc

    runner = Runner.alloc().init()
    runner.performSelectorOnMainThread_withObject_waitUntilDone_(
        objc.selector(runner.runOnMain_, signature=b"v@:@"),
        None,
        True,
    )
    if "error" in state:
        raise state["error"]
    return state["result"]


def _escape_applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _osascript_dialog(title: str, body: str) -> None:
    script = (
        f'display alert "{_escape_applescript_string(title)}" '
        f'message "{_escape_applescript_string(body)}" '
        'buttons {"OK"} default button "OK"'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def show_native_confirm(
    title: str,
    body: str,
    *,
    primary: str = "OK",
    secondary: str = "Cancel",
) -> bool:
    if sys.platform == "darwin":
        script = (
            f'set response to display alert "{_escape_applescript_string(title)}" '
            f'message "{_escape_applescript_string(body)}" '
            f'buttons {{"{_escape_applescript_string(secondary)}", '
            f'"{_escape_applescript_string(primary)}"}} '
            f'default button "{_escape_applescript_string(primary)}" '
            f'cancel button "{_escape_applescript_string(secondary)}"\n'
            "return button returned of response"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() == primary
    import webview

    win = webview.active_window()
    if win is None and webview.windows:
        win = webview.windows[0]
    if win is not None:
        return bool(win.create_confirmation_dialog(title, body))
    return False


def show_native_message(title: str, body: str) -> None:
    if sys.platform == "darwin":
        _osascript_dialog(title, body)
        return
    import webview

    win = webview.active_window()
    if win is None and webview.windows:
        win = webview.windows[0]
    if win is not None:
        win.create_confirmation_dialog(title, body)


def show_about_dialog() -> None:
    from peerfold import __version__

    show_native_message(
        f"PeerFold {__version__}",
        "PDF review with standard highlight annotations.\n"
        "https://vincenzoml.github.io/PeerFold/",
    )


def show_update_check_dialog(info: dict[str, Any]) -> None:
    from peerfold import __version__

    current = info.get("current") or __version__
    if not info.get("check_ok"):
        show_native_message("PeerFold", "Could not check for updates.")
        return
    if info.get("update_available"):
        latest = info.get("latest") or "?"
        if info.get("can_install") and show_native_confirm(
            "PeerFold",
            f"Update available: v{latest} (you have v{current}).",
            primary="Install",
            secondary="Later",
        ):
            from peerfold.updater import install_latest_update, relaunch_after_update

            try:
                result = install_latest_update()
            except Exception as exc:
                show_native_message("PeerFold", str(exc))
                return
            if result.get("ok"):
                show_native_message("PeerFold", str(result.get("message") or "Update installed."))
                if result.get("relaunch"):
                    relaunch_after_update()
            else:
                show_native_message("PeerFold", str(result.get("error") or "Update failed."))
            return
        body = f"Update available: v{latest} (you have v{current})."
        url = info.get("download_url") or info.get("url") or ""
        if url:
            body += f"\n\n{url}"
        show_native_message("PeerFold", body)
        return
    latest = info.get("latest")
    if latest and latest != current:
        body = f"PeerFold v{current} is up to date (latest release: v{latest})."
    else:
        body = f"PeerFold v{current} is up to date."
    show_native_message("PeerFold", body)


class ApplicationMenuApi:
    """Application menu actions (shared across document windows)."""

    def __init__(self, host) -> None:
        self._host = host

    def menu_open(self) -> None:
        run_on_main_thread(self._menu_open)

    def _menu_open(self) -> None:
        self._host.open_via_dialog()

    def menu_new_window(self) -> None:
        run_on_main_thread(self._menu_new_window)

    def _menu_new_window(self) -> None:
        self._host.open_empty_window()

    def open_recent(self, path: str) -> None:
        run_on_main_thread(lambda: self._open_recent_on_main(path))

    def _open_recent_on_main(self, path: str) -> None:
        pdf = Path(path).expanduser().resolve()
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            remove_recent_file(pdf)
            refresh_application_menu_for_host()
            return
        self._host.open_document(pdf)

    def clear_recent(self) -> None:
        run_on_main_thread(self._clear_recent)

    def _clear_recent(self) -> None:
        clear_recent_files()

    def menu_undo(self) -> None:
        run_on_main_thread(self._menu_undo)

    def _menu_undo(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_undo()

    def menu_redo(self) -> None:
        run_on_main_thread(self._menu_redo)

    def _menu_redo(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_redo()

    def check_for_updates(self) -> None:
        from peerfold.core import update_check_payload

        show_update_check_dialog(update_check_payload())

    def show_about(self) -> None:
        show_about_dialog()


class PeerFoldApi:
    """JS bridge for native file dialogs in the active document window."""

    def __init__(self) -> None:
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    def pick_pdf(self) -> str | None:
        if not self._window:
            return None
        import webview

        result = self._window.create_file_dialog(
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

    def install_update(self) -> dict[str, Any]:
        from peerfold.updater import install_latest_update, relaunch_after_update

        try:
            result = install_latest_update()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if result.get("ok") and result.get("relaunch"):
            run_on_main_thread(relaunch_after_update)
        return result

    def document_opened(self, path: str) -> None:
        resolved = Path(path).expanduser().resolve()
        if resolved.is_file():
            add_recent_file(resolved)
            run_on_main_thread(refresh_application_menu_for_host)

    def menu_undo(self) -> None:
        self._dispatch("undo")

    def menu_redo(self) -> None:
        self._dispatch("redo")

    def check_for_updates(self) -> None:
        from peerfold.core import update_check_payload

        show_update_check_dialog(update_check_payload())

    def show_about(self) -> None:
        show_about_dialog()

    def _dispatch(self, action: str) -> None:
        if not self._window:
            return

        def emit() -> None:
            payload = json.dumps(action)
            self._window.evaluate_js(
                f'window.dispatchEvent(new CustomEvent("peerfold-menu", '
                f"{{detail: {{action: {payload}}}}}))"
            )

        run_on_main_thread(emit)

    def _open_path(self, path: str) -> None:
        if not self._window:
            return

        def emit() -> None:
            payload = json.dumps(path)
            self._window.evaluate_js(
                f'window.dispatchEvent(new CustomEvent("peerfold-open-path", '
                f"{{detail: {payload}}}))"
            )

        run_on_main_thread(emit)


def refresh_application_menu_for_host() -> None:
    try:
        from peerfold.app_host import AppHost

        refresh_application_menu(AppHost.instance().menu_api)
    except RuntimeError:
        pass


def build_application_menu(api: ApplicationMenuApi):
    from webview.menu import Menu, MenuAction, MenuSeparator

    recent_paths = list_recent_paths()
    recent_items: list = []
    if recent_paths:
        for path in recent_paths:
            recent_items.append(
                MenuAction(recent_menu_label(path), (lambda p=str(path): api.open_recent(p)))
            )
        recent_items.append(MenuSeparator())
        recent_items.append(MenuAction("Clear Menu", api.clear_recent))
    else:
        recent_items.append(MenuAction("(Empty)", lambda: None))

    file_menu = Menu(
        "File",
        [
            MenuAction("Open…", api.menu_open),
            MenuAction("New Window", api.menu_new_window),
            MenuSeparator(),
            Menu("Open Recent", recent_items),
        ],
    )

    return [
        Menu(
            "__app__",
            [
                MenuAction("About PeerFold", api.show_about),
                MenuSeparator(),
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


def refresh_application_menu(api: ApplicationMenuApi) -> None:
    run_on_main_thread(lambda: _refresh_application_menu_on_main(api))


def _refresh_application_menu_on_main(api: ApplicationMenuApi) -> None:
    from peerfold.macos_menu import refresh_open_recent_menu

    refresh_open_recent_menu(
        list_recent_paths(),
        api._open_recent_on_main,
        clear_handler=api._clear_recent,
    )


def _set_macos_dock_name(name: str = "PeerFold") -> None:
    """Show PeerFold in the Dock tooltip instead of Python (dev and PyInstaller builds)."""
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        AppKit.NSProcessInfo.processInfo().setProcessName_(name)
    except Exception:
        pass


def _set_application_icon() -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        _set_macos_dock_name()
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

    webview.start(on_start, debug=False)


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
