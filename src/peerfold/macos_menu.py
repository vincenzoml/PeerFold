"""Refresh the native File > Open Recent menu on macOS."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

_handler = None


def refresh_open_recent_menu(paths: list[Path], open_handler: Callable[[str], None]) -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        import objc
    except ImportError:
        return

    global _handler

    class _Handler(AppKit.NSObject):
        def openRecent_(self, sender) -> None:
            raw = sender.representedObject()
            if raw:
                open_handler(str(raw))  # caller must be main-thread safe

    if _handler is None:
        _handler = _Handler.alloc().init()

    app = AppKit.NSApplication.sharedApplication()
    main = app.mainMenu()
    if main is None:
        return

    file_menu = None
    for idx in range(main.numberOfItems()):
        item = main.itemAtIndex_(idx)
        if item.title() == "File":
            file_menu = item.submenu()
            break
    if file_menu is None:
        return

    recent_menu = None
    recent_index = None
    for idx in range(file_menu.numberOfItems()):
        item = file_menu.itemAtIndex_(idx)
        if item.title() == "Open Recent":
            recent_menu = item.submenu()
            recent_index = idx
            break

    if recent_menu is None:
        recent_menu = AppKit.NSMenu.alloc().initWithTitle_("Open Recent")
        recent_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Recent", None, ""
        )
        recent_item.setSubmenu_(recent_menu)
        insert_at = 1 if file_menu.numberOfItems() >= 1 else 0
        file_menu.insertItem_atIndex_(recent_item, insert_at)
        recent_index = insert_at
    else:
        recent_menu.removeAllItems()

    for path in paths:
        item = recent_menu.addItemWithTitle_action_keyEquivalent_(path.name, "openRecent:", "")
        item.setRepresentedObject_(str(path))
        item.setTarget_(_handler)

    if recent_index is not None:
        file_menu.itemAtIndex_(recent_index).setEnabled_(bool(paths))
