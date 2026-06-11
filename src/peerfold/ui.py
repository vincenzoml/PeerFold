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


def _osascript_about(version: str, website: str, repository: str) -> None:
    title = f"PeerFold {version}"
    script = (
        f'set website to "{_escape_applescript_string(website)}"\n'
        f'set github to "{_escape_applescript_string(repository)}"\n'
        f'set response to display alert "{_escape_applescript_string(title)}" '
        f'message "{_escape_applescript_string("PDF review with standard highlight annotations.")}" '
        'buttons {"Visit website", "View on GitHub", "OK"} default button "OK"\n'
        "set choice to button returned of response\n"
        'if choice is "Visit website" then open location website\n'
        'if choice is "View on GitHub" then open location github'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def show_about_dialog() -> None:
    from peerfold import __version__
    from peerfold.links import REPOSITORY, WEBSITE, about_body

    if sys.platform == "darwin":
        _osascript_about(__version__, WEBSITE, REPOSITORY)
        return
    show_native_message(f"PeerFold {__version__}", about_body(version=__version__))


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

    def menu_copy(self) -> None:
        run_on_main_thread(self._menu_copy)

    def _menu_copy(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_copy()

    def menu_select_all(self) -> None:
        run_on_main_thread(self._menu_select_all)

    def _menu_select_all(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_select_all()

    def menu_copy_comments(self) -> None:
        run_on_main_thread(self._menu_copy_comments)

    def _menu_copy_comments(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_copy_comments()

    def menu_export_markdown(self) -> None:
        run_on_main_thread(self._menu_export_markdown)

    def _menu_export_markdown(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_export_markdown()

    def menu_export_text(self) -> None:
        run_on_main_thread(self._menu_export_text)

    def _menu_export_text(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_export_text()

    def menu_zoom_in(self) -> None:
        run_on_main_thread(self._menu_zoom_in)

    def _menu_zoom_in(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_zoom_in()

    def menu_zoom_out(self) -> None:
        run_on_main_thread(self._menu_zoom_out)

    def _menu_zoom_out(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_zoom_out()

    def menu_zoom_reset(self) -> None:
        run_on_main_thread(self._menu_zoom_reset)

    def _menu_zoom_reset(self) -> None:
        api = self._host.api_for_active_window()
        if api is not None:
            api.menu_zoom_reset()

    def menu_duplicate_window(self) -> None:
        run_on_main_thread(self._menu_duplicate_window)

    def _menu_duplicate_window(self) -> None:
        self._host.duplicate_active_window()

    def remove_recent(self, path: str) -> None:
        run_on_main_thread(lambda: self._remove_recent_on_main(path))

    def _remove_recent_on_main(self, path: str) -> None:
        remove_recent_file(Path(path).expanduser())
        refresh_application_menu_for_host()

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

    def save_export(self, suggested_name: str, content: str, fmt: str) -> dict[str, Any]:
        if not self._window:
            return {"ok": False, "error": "no window"}
        import webview

        if fmt == "markdown":
            file_types = ("Markdown (*.md)", "All files (*.*)")
            default = suggested_name if suggested_name.endswith(".md") else f"{suggested_name}.md"
        else:
            file_types = ("Plain text (*.txt)", "All files (*.*)")
            default = suggested_name if suggested_name.endswith(".txt") else f"{suggested_name}.txt"
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default,
            file_types=file_types,
        )
        if not result:
            return {"ok": False, "cancelled": True}
        path = result if isinstance(result, str) else result[0]
        Path(path).write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(Path(path).expanduser().resolve())}

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

    def menu_copy(self) -> None:
        self._dispatch("copy")

    def menu_select_all(self) -> None:
        self._dispatch("select-all")

    def menu_copy_comments(self) -> None:
        self._dispatch("copy-comments")

    def menu_export_markdown(self) -> None:
        self._dispatch("export-markdown")

    def menu_export_text(self) -> None:
        self._dispatch("export-text")

    def menu_zoom_in(self) -> None:
        self._dispatch("zoom-in")

    def menu_zoom_out(self) -> None:
        self._dispatch("zoom-out")

    def menu_zoom_reset(self) -> None:
        self._dispatch("zoom-reset")

    def new_window(self) -> None:
        run_on_main_thread(self._new_window)

    def _new_window(self) -> None:
        try:
            from peerfold.app_host import AppHost

            AppHost.instance().open_empty_window()
        except RuntimeError:
            pass

    def duplicate_window(self) -> None:
        run_on_main_thread(self._duplicate_window)

    def _duplicate_window(self) -> None:
        try:
            from peerfold.app_host import AppHost

            AppHost.instance().duplicate_active_window()
        except RuntimeError:
            pass

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
            MenuAction("Duplicate Window", api.menu_duplicate_window),
            MenuSeparator(),
            Menu("Open Recent", recent_items),
            MenuSeparator(),
            MenuAction("Export Comments as Markdown…", api.menu_export_markdown),
            MenuAction("Export Comments as Text…", api.menu_export_text),
        ],
    )

    edit_menu = Menu(
        "Edit",
        [
            MenuAction("Undo", api.menu_undo),
            MenuAction("Redo", api.menu_redo),
            MenuSeparator(),
            MenuAction("Copy", api.menu_copy),
            MenuAction("Copy Comments", api.menu_copy_comments),
            MenuAction("Select All Comments", api.menu_select_all),
        ],
    )
    view_menu = Menu(
        "View",
        [
            MenuAction("Zoom In", api.menu_zoom_in),
            MenuAction("Zoom Out", api.menu_zoom_out),
            MenuAction("Actual Size", api.menu_zoom_reset),
        ],
    )
    window_menu = Menu(
        "Window",
        [
            MenuAction("New Window", api.menu_new_window),
            MenuAction("Duplicate Window", api.menu_duplicate_window),
        ],
    )

    menus = [
        Menu(
            "__app__",
            [
                MenuAction("About PeerFold", api.show_about),
                MenuSeparator(),
                MenuAction("Check for Updates…", api.check_for_updates),
            ],
        ),
        file_menu,
    ]
    if sys.platform != "darwin":
        menus.extend([edit_menu, view_menu, window_menu])
    menus.append(
        Menu(
            "Help",
            [
                MenuAction("About PeerFold", api.show_about),
                MenuAction("Check for Updates…", api.check_for_updates),
            ],
        ),
    )
    return menus


def refresh_application_menu(api: ApplicationMenuApi) -> None:
    run_on_main_thread(lambda: _refresh_application_menu_on_main(api))


def _refresh_application_menu_on_main(api: ApplicationMenuApi) -> None:
    from peerfold.macos_menu import refresh_application_menus

    refresh_application_menus(api)


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
    from peerfold.core import print_launch_banner

    print_launch_banner(local_url=url)
    print()
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
