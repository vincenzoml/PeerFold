"""macOS Apple Events for opening documents in a running PeerFold process."""

from __future__ import annotations

import sys
from collections.abc import Callable

_kCoreEventClass = 0x61657674  # 'aevt'
_kAEOpenDocuments = 0x6F646F63  # 'odoc'
_keyDirectObject = 0x2D2D2D2D  # '----'

_open_handler = None
_reopen_handler = None
_reopen_proxy = None


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
    """Open a new empty window when the Dock icon is clicked with no windows."""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from AppKit import NSApplication, NSObject
    except ImportError:
        return

    global _reopen_handler, _reopen_proxy

    app = NSApplication.sharedApplication()
    delegate = app.delegate()
    if delegate is None:
        return

    class ReopenProxy(NSObject):
        def initWithDelegate_callback_(self, original, callback):
            self = objc.super(ReopenProxy, self).init()
            if self is None:
                return None
            self._original = original
            self._callback = callback
            return self

        def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
            if not visible:
                self._callback()
            if self._original is not None and self._original.respondsToSelector_(
                "applicationShouldHandleReopen:hasVisibleWindows:"
            ):
                return self._original.applicationShouldHandleReopen_hasVisibleWindows_(
                    application, visible
                )
            return True

        def respondsToSelector_(self, selector):
            if selector == b"applicationShouldHandleReopen:hasVisibleWindows:":
                return True
            if self._original is not None:
                return self._original.respondsToSelector_(selector)
            return objc.super(ReopenProxy, self).respondsToSelector_(selector)

        def forwardingTargetForSelector_(self, selector):
            if self._original is not None and self._original.respondsToSelector_(selector):
                return self._original
            return objc.super(ReopenProxy, self).forwardingTargetForSelector_(selector)

    if _reopen_proxy is None:
        _reopen_handler = open_empty_window
        _reopen_proxy = ReopenProxy.alloc().initWithDelegate_callback_(
            delegate, lambda: _reopen_handler()
        )
        app.setDelegate_(_reopen_proxy)
