"""macOS Apple Events for opening documents in a running PeerFold process."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable

_kCoreEventClass = 0x61657674  # 'aevt'
_kAEOpenDocuments = 0x6F646F63  # 'odoc'
_keyDirectObject = 0x2D2D2D2D  # '----'

_open_handler = None


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
