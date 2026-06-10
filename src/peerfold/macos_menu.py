"""Refresh the native File > Open Recent menu on macOS."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from peerfold.recent_files import menu_label

_handler = None
_clear_handler = None
_open_handler: Callable[[str], None] | None = None
_clear_handler_fn: Callable[[], None] | None = None


def refresh_open_recent_menu(
    paths: list[Path],
    open_handler: Callable[[str], None],
    *,
    clear_handler: Callable[[], None] | None = None,
) -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit
    except ImportError:
        return

    global _handler, _clear_handler, _open_handler, _clear_handler_fn

    from peerfold.ui import run_on_main_thread

    _open_handler = open_handler
    _clear_handler_fn = clear_handler

    if _handler is None:
        class PeerFoldOpenRecentHandler(AppKit.NSObject):
            def openRecent_(self, sender) -> None:
                raw = sender.representedObject()
                if raw and _open_handler is not None:
                    run_on_main_thread(lambda: _open_handler(str(raw)))

        _handler = PeerFoldOpenRecentHandler.alloc().init()

    if _clear_handler is None:
        class PeerFoldClearRecentHandler(AppKit.NSObject):
            def clearRecent_(self, _sender) -> None:
                if _clear_handler_fn is not None:
                    run_on_main_thread(_clear_handler_fn)

        _clear_handler = PeerFoldClearRecentHandler.alloc().init()

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

    if paths:
        for path in paths:
            item = recent_menu.addItemWithTitle_action_keyEquivalent_(
                menu_label(path), "openRecent:", ""
            )
            item.setRepresentedObject_(str(path))
            item.setTarget_(_handler)
        recent_menu.addItem_(AppKit.NSMenuItem.separatorItem())
        clear_item = recent_menu.addItemWithTitle_action_keyEquivalent_(
            "Clear Menu", "clearRecent:", ""
        )
        clear_item.setTarget_(_clear_handler)
    else:
        empty = recent_menu.addItemWithTitle_action_keyEquivalent_("(Empty)", "", "")
        empty.setEnabled_(False)

    if recent_index is not None:
        file_menu.itemAtIndex_(recent_index).setEnabled_(True)
