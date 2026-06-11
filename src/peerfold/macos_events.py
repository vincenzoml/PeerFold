"""macOS Apple Events and Dock integration for PeerFold."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from peerfold.ui import ApplicationMenuApi

_kCoreEventClass = 0x61657674  # 'aevt'
_kAEOpenDocuments = 0x6F646F63  # 'odoc'
_keyDirectObject = 0x2D2D2D2D  # '----'

_open_handler = None
_dock_handler = None
_dock_menu_api: ApplicationMenuApi | None = None


def install_open_documents_handler(open_path: Callable[[str], None]) -> None:
    """Handle Open With / Finder double-click while PeerFold is already running."""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from Foundation import NSAppleEventManager
    except ImportError:
        return

    global _open_handler

    class OpenHandler(objc.lookUpClass("NSObject")):
        def handleOpenEvent_withReplyEvent_(self, event, reply_event) -> None:
            direct = event.paramDescriptorForKeyword_(_keyDirectObject)
            if direct is None:
                return
            count = int(direct.numberOfItems())
            for index in range(1, count + 1):
                item = direct.descriptorAtIndex_(index)
                url = item.fileURLValue()
                if url is not None and url.isFileURL():
                    open_path(str(url.path()))
                    return

    if _open_handler is None:
        _open_handler = OpenHandler.alloc().init()

    NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
        _open_handler,
        "handleOpenEvent:withReplyEvent:",
        _kCoreEventClass,
        _kAEOpenDocuments,
    )


def install_dock_reopen_handler(open_empty_window: Callable[[], None]) -> None:
    """Open a new window when the Dock icon is clicked with no visible windows."""
    if sys.platform != "darwin":
        return
    try:
        from webview.platforms.cocoa import BrowserView

        from peerfold.ui import run_on_main_thread
    except ImportError:
        return

    delegate = BrowserView._shared_app_delegate
    if delegate is None:
        return
    if delegate.respondsToSelector_("applicationShouldHandleReopen:hasVisibleWindows:"):
        return

    def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
        if not visible:
            run_on_main_thread(open_empty_window)
        return True

    delegate.applicationShouldHandleReopen_hasVisibleWindows_ = types.MethodType(
        applicationShouldHandleReopen_hasVisibleWindows_,
        delegate,
    )


def install_dock_menu_handler(menu_api: ApplicationMenuApi) -> None:
    """Show recent files and window actions in the Dock icon menu."""
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        from webview.platforms.cocoa import BrowserView

        from peerfold.recent_files import list_paths, menu_label
        from peerfold.ui import run_on_main_thread
    except ImportError:
        return

    global _dock_handler, _dock_menu_api
    _dock_menu_api = menu_api

    delegate = BrowserView._shared_app_delegate
    if delegate is None:
        return

    if _dock_handler is None:
        class PeerFoldDockHandler(AppKit.NSObject):
            def dockAction_(self, sender) -> None:
                action = str(sender.representedObject() or "")
                api = _dock_menu_api
                if api is None:
                    return
                if action == "new_window":
                    run_on_main_thread(api._menu_new_window)
                elif action == "duplicate_window":
                    run_on_main_thread(api._menu_duplicate_window)
                elif action == "clear_recent":
                    run_on_main_thread(api._clear_recent)
                elif action.startswith("open:"):
                    path = action[5:]
                    run_on_main_thread(lambda: api._open_recent_on_main(path))

        _dock_handler = PeerFoldDockHandler.alloc().init()

    if delegate.respondsToSelector_("applicationDockMenu:"):
        return

    def applicationDockMenu_(self, sender):
        menu = AppKit.NSMenu.alloc().init()
        api = _dock_menu_api
        if api is None:
            return menu

        new_item = menu.addItemWithTitle_action_keyEquivalent_("New Window", "dockAction:", "")
        new_item.setTarget_(_dock_handler)
        new_item.setRepresentedObject_("new_window")

        dup_item = menu.addItemWithTitle_action_keyEquivalent_("Duplicate Window", "dockAction:", "")
        dup_item.setTarget_(_dock_handler)
        dup_item.setRepresentedObject_("duplicate_window")

        paths = list_paths()
        if paths:
            menu.addItem_(AppKit.NSMenuItem.separatorItem())
            for path in paths:
                item = menu.addItemWithTitle_action_keyEquivalent_(
                    menu_label(path), "dockAction:", ""
                )
                item.setTarget_(_dock_handler)
                item.setRepresentedObject_(f"open:{path}")
            menu.addItem_(AppKit.NSMenuItem.separatorItem())
            clear_item = menu.addItemWithTitle_action_keyEquivalent_("Clear Recent", "dockAction:", "")
            clear_item.setTarget_(_dock_handler)
            clear_item.setRepresentedObject_("clear_recent")
        return menu

    delegate.applicationDockMenu_ = types.MethodType(applicationDockMenu_, delegate)
