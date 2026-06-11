"""Refresh native menus on macOS (Open Recent, shortcuts, Window)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from peerfold.recent_files import menu_label

if TYPE_CHECKING:
    from peerfold.ui import ApplicationMenuApi

_handler = None
_clear_handler = None
_remove_handler = None
_menu_handler = None
_open_handler: Callable[[str], None] | None = None
_clear_handler_fn: Callable[[], None] | None = None
_remove_handler_fn: Callable[[str], None] | None = None
_menu_api: ApplicationMenuApi | None = None
_EDIT_MARKER = "PeerFoldUndo"
_VIEW_MARKER = "PeerFoldZoomIn"
_WINDOW_MARKER = "PeerFoldNewWindow"
_COPY_COMMENTS_MARKER = "PeerFoldCopyComments"


def refresh_application_menus(api: ApplicationMenuApi) -> None:
    if sys.platform != "darwin":
        return
    global _menu_api
    _menu_api = api
    from peerfold.recent_files import list_paths

    refresh_open_recent_menu(
        list_paths(),
        api._open_recent_on_main,
        clear_handler=api._clear_recent,
        remove_handler=api._remove_recent_on_main,
    )
    refresh_standard_menus(api)


def _main_menu():
    try:
        import AppKit
    except ImportError:
        return None
    return AppKit.NSApplication.sharedApplication().mainMenu()


def _submenu(title: str):
    main = _main_menu()
    if main is None:
        return None
    for idx in range(main.numberOfItems()):
        item = main.itemAtIndex_(idx)
        if item.title() == title:
            return item.submenu()
    return None


def _menu_handler_obj():
    global _menu_handler
    if _menu_handler is not None:
        return _menu_handler
    try:
        import AppKit
    except ImportError:
        return None

    from peerfold.ui import run_on_main_thread

    class PeerFoldMenuHandler(AppKit.NSObject):
        def peerfoldMenu_(self, sender) -> None:
            action = str(sender.representedObject() or "")
            if not action or _menu_api is None:
                return
            method = getattr(_menu_api, action, None)
            if callable(method):
                run_on_main_thread(method)

    _menu_handler = PeerFoldMenuHandler.alloc().init()
    return _menu_handler


def _insert_action(
    menu,
    index: int,
    title: str,
    action_name: str,
    key: str,
    *,
    shift: bool = False,
    marker: str = "",
) -> None:
    import AppKit

    handler = _menu_handler_obj()
    if handler is None:
        return
    item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "peerfoldMenu:", key)
    item.setTarget_(handler)
    item.setRepresentedObject_(action_name)
    if marker:
        item.setTag_(hash(marker) & 0x7FFFFFFF)
    if shift and key:
        item.setKeyEquivalentModifierMask_(AppKit.NSCommandKeyMask | AppKit.NSShiftKeyMask)
    menu.insertItem_atIndex_(item, index)


def _menu_has_marker(menu, marker: str) -> bool:
    tag = hash(marker) & 0x7FFFFFFF
    for idx in range(menu.numberOfItems()):
        if int(menu.itemAtIndex_(idx).tag()) == tag:
            return True
    return False


def refresh_standard_menus(api: ApplicationMenuApi) -> None:
    if sys.platform != "darwin":
        return
    global _menu_api
    _menu_api = api
    try:
        import AppKit
    except ImportError:
        return

    edit = _submenu("Edit")
    if edit is not None and not _menu_has_marker(edit, _EDIT_MARKER):
        _insert_action(edit, 0, "Undo", "menu_undo", "z", marker=_EDIT_MARKER)
        _insert_action(edit, 1, "Redo", "menu_redo", "Z", shift=True, marker=_EDIT_MARKER)
        edit.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 2)
    if edit is not None and not _menu_has_marker(edit, _COPY_COMMENTS_MARKER):
        _insert_action(
            edit,
            3,
            "Copy Comments",
            "menu_copy_comments",
            "c",
            shift=True,
            marker=_COPY_COMMENTS_MARKER,
        )

    view = _submenu("View")
    if view is not None and not _menu_has_marker(view, _VIEW_MARKER):
        _insert_action(view, 0, "Zoom In", "menu_zoom_in", "+", marker=_VIEW_MARKER)
        _insert_action(view, 1, "Zoom Out", "menu_zoom_out", "-", marker=_VIEW_MARKER)
        _insert_action(view, 2, "Actual Size", "menu_zoom_reset", "0", marker=_VIEW_MARKER)
        view.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 3)

    window = _submenu("Window")
    main = _main_menu()
    if window is None and main is not None:
        window_menu = AppKit.NSMenu.alloc().initWithTitle_("Window")
        window_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Window", None, "")
        window_item.setSubmenu_(window_menu)
        main.addItem_(window_item)
        window = window_menu

    if window is not None and not _menu_has_marker(window, _WINDOW_MARKER):
        _insert_action(
            window,
            0,
            "New Window",
            "menu_new_window",
            "n",
            shift=True,
            marker=_WINDOW_MARKER,
        )
        _insert_action(
            window,
            1,
            "Duplicate Window",
            "menu_duplicate_window",
            "d",
            shift=True,
            marker=_WINDOW_MARKER,
        )


def refresh_open_recent_menu(
    paths: list[Path],
    open_handler: Callable[[str], None],
    *,
    clear_handler: Callable[[], None] | None = None,
    remove_handler: Callable[[str], None] | None = None,
) -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit
    except ImportError:
        return

    global _handler, _clear_handler, _remove_handler, _open_handler, _clear_handler_fn, _remove_handler_fn

    from peerfold.ui import run_on_main_thread

    _open_handler = open_handler
    _clear_handler_fn = clear_handler
    _remove_handler_fn = remove_handler

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

    if _remove_handler is None:
        class PeerFoldRemoveRecentHandler(AppKit.NSObject):
            def removeRecent_(self, sender) -> None:
                raw = sender.representedObject()
                if raw and _remove_handler_fn is not None:
                    run_on_main_thread(lambda: _remove_handler_fn(str(raw)))

        _remove_handler = PeerFoldRemoveRecentHandler.alloc().init()

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
        for path in paths:
            item = recent_menu.addItemWithTitle_action_keyEquivalent_(
                f"Remove “{path.name}”", "removeRecent:", ""
            )
            item.setRepresentedObject_(str(path))
            item.setTarget_(_remove_handler)
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
