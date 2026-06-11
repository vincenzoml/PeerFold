"""Recently opened PDF paths."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_RECENT = 12
_FILENAME = "recent.json"


def _store_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "PeerFold"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "peerfold"
    base.mkdir(parents=True, exist_ok=True)
    return base / _FILENAME


def _read_store() -> list[str]:
    store = _store_path()
    if not store.is_file():
        return []
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(raw) for raw in data]


def _write_store(paths: list[Path]) -> None:
    _store_path().write_text(
        json.dumps([str(p) for p in paths], indent=2) + "\n",
        encoding="utf-8",
    )


def folder_short(path: Path) -> str:
    path = path.expanduser().resolve()
    parent = path.parent
    try:
        short_parent = str(parent.relative_to(Path.home()))
        if not short_parent.startswith(".."):
            return f"~/{short_parent}" if short_parent != "." else "~"
    except ValueError:
        pass
    return str(parent)


def menu_label(path: Path) -> str:
    path = path.expanduser().resolve()
    return f"{path.name}  —  {folder_short(path)}"


def list_payload() -> list[dict[str, str]]:
    return [
        {
            "path": str(path),
            "name": path.name,
            "folder": folder_short(path),
        }
        for path in list_paths()
    ]


def list_paths() -> list[Path]:
    out: list[Path] = []
    for raw in _read_store():
        path = Path(str(raw)).expanduser()
        if path.is_file() and path.suffix.lower() == ".pdf":
            out.append(path.resolve())
    if len(out) != len(_read_store()):
        _write_store(out)
    return out


def add(path: Path) -> list[Path]:
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return list_paths()
    items = [path, *[p for p in list_paths() if p != path]][:MAX_RECENT]
    _write_store(items)
    note_system_recent(path)
    _refresh_menu()
    return items


def remove(path: Path) -> list[Path]:
    needle = str(path.expanduser())
    remaining = [
        raw
        for raw in _read_store()
        if raw != needle and Path(raw).expanduser() != path.expanduser()
    ]
    out: list[Path] = []
    for raw in remaining:
        candidate = Path(raw).expanduser()
        if candidate.is_file() and candidate.suffix.lower() == ".pdf":
            out.append(candidate.resolve())
    _write_store(out)
    _refresh_menu()
    return out


def clear() -> None:
    _write_store([])
    _refresh_menu()


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
