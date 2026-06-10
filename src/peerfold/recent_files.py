"""Recently opened PDF paths."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_RECENT = 10
_FILENAME = "recent.json"


def _store_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "PeerFold"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "peerfold"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


def list_paths() -> list[Path]:
    store = _store_path()
    if not store.is_file():
        return []
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[Path] = []
    for raw in data if isinstance(data, list) else []:
        path = Path(str(raw)).expanduser()
        if path.is_file() and path.suffix.lower() == ".pdf":
            out.append(path.resolve())
    return out


def add(path: Path) -> list[Path]:
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return list_paths()
    items = [path, *[p for p in list_paths() if p != path]][:MAX_RECENT]
    _store_path().write_text(
        json.dumps([str(p) for p in items], indent=2) + "\n",
        encoding="utf-8",
    )
    note_system_recent(path)
    _refresh_menu()
    return items


def _refresh_menu() -> None:
    try:
        from peerfold.ui import refresh_application_menu_for_host

        refresh_application_menu_for_host()
    except Exception:
        pass


def note_system_recent(path: Path) -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        from Foundation import NSURL

        url = NSURL.fileURLWithPath_(str(path))
        AppKit.NSDocumentController.sharedDocumentController().noteNewRecentDocumentURL_(url)
    except Exception:
        pass
