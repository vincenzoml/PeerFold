"""Native file dialogs safe with pywebview on macOS."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any


def save_text_file(
    window,
    suggested_name: str,
    content: str,
    fmt: str,
) -> dict[str, Any]:
    """Show a save panel and write UTF-8 text.

    pywebview's create_file_dialog schedules work with AppHelper.callAfter and
    blocks the caller on a semaphore. Calling it from the AppKit main thread
    deadlocks forever; the JS API runs on a worker thread and is safe.
    """
    if not window:
        return {"ok": False, "error": "no window"}

    if fmt == "markdown":
        file_types = ("Markdown (*.md)", "All files (*.*)")
        default = suggested_name if suggested_name.endswith(".md") else f"{suggested_name}.md"
    else:
        file_types = ("Plain text (*.txt)", "All files (*.*)")
        default = suggested_name if suggested_name.endswith(".txt") else f"{suggested_name}.txt"

    if sys.platform == "darwin" and threading.current_thread() is threading.main_thread():
        return _macos_save_panel(default, content)

    import webview

    result = window.create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=default,
        file_types=file_types,
    )
    if not result:
        return {"ok": False, "cancelled": True}
    path = result if isinstance(result, str) else result[0]
    target = Path(path).expanduser()
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(target.resolve())}


def _macos_save_panel(default_name: str, content: str) -> dict[str, Any]:
    import AppKit

    panel = AppKit.NSSavePanel.savePanel()
    panel.setNameFieldStringValue_(default_name)
    if panel.runModal() != AppKit.NSFileHandlingPanelOKButton:
        return {"ok": False, "cancelled": True}
    url = panel.URL()
    if url is None:
        return {"ok": False, "error": "no path chosen"}
    path = Path(str(url.path())).expanduser()
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(path.resolve())}


def pick_pdf_file(window) -> str | None:
    if not window:
        return None
    if sys.platform == "darwin" and threading.current_thread() is threading.main_thread():
        return _macos_open_pdf_panel()
    import webview

    result = window.create_file_dialog(
        webview.OPEN_DIALOG,
        allow_multiple=False,
        file_types=("PDF files (*.pdf)", "All files (*.*)"),
    )
    if not result:
        return None
    path = result[0] if isinstance(result, (list, tuple)) else result
    return str(Path(path).expanduser().resolve())


def _macos_open_pdf_panel() -> str | None:
    import AppKit

    panel = AppKit.NSOpenPanel.openPanel()
    panel.setCanChooseFiles_(True)
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setAllowedFileTypes_(["pdf"])
    if panel.runModal() != AppKit.NSFileHandlingPanelOKButton:
        return None
    names = panel.filenames()
    if not names:
        return None
    return str(Path(names[0]).expanduser().resolve())
