"""Multi-document native window host for PeerFold."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from peerfold.core import (
    QuietThreadingHTTPServer,
    ReviewHandler,
    ServerSession,
    farewell_message,
    pick_port,
    print_launch_banner,
    print_review_target,
    terminal_verbose,
)
from peerfold.ui import (
    ApplicationMenuApi,
    WebviewUnavailableError,
    _bind_native_drop_paths,
    _set_application_icon,
    build_application_menu,
    refresh_application_menu,
    run_on_main_thread,
    webview_available,
)


class DocumentWindow:
    """One PDF document backed by its own HTTP server and webview window."""

    def __init__(self, host: AppHost, reviewer: str, pdf: Path | None) -> None:
        self._host = host
        self.session = ServerSession(reviewer, pdf)
        self.port = pick_port(0)
        self.url = f"http://127.0.0.1:{self.port}/"
        self.title = f"PeerFold · {pdf.name}" if pdf else "PeerFold"
        self.api = None  # set when the webview window is created
        self.window = None
        self._server = None
        self._thread = None

    def start_server(self) -> None:
        handler = type("BoundReviewHandler", (ReviewHandler,), {})
        handler.session = self.session
        handler.fitz_mod = None
        self._server = QuietThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"peerfold-http-{self.port}",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self.session.close()

    def create_webview_window(self) -> None:
        from peerfold.ui import PeerFoldApi

        import webview

        api = PeerFoldApi()
        self.api = api
        self.window = webview.create_window(
            self.title,
            self.url,
            width=1440,
            height=900,
            min_size=(720, 480),
            background_color="#0c0c0e",
            text_select=True,
            js_api=api,
        )
        api.set_window(self.window)
        self.window.events.closed += self._on_closed

        def on_loaded() -> None:
            try:
                _bind_native_drop_paths(self.window)
            except Exception:
                pass

        self.window.events.loaded += on_loaded

    def _on_closed(self) -> None:
        self._host._on_document_closed(self)


class AppHost:
    """Owns every open document window in the native app."""

    _instance: AppHost | None = None

    def __init__(self, reviewer: str) -> None:
        self.reviewer = reviewer
        self.menu_api = ApplicationMenuApi(self)
        self._documents: list[DocumentWindow] = []
        self._docs_lock = threading.Lock()
        self._started = False

    @classmethod
    def instance(cls) -> AppHost:
        if cls._instance is None:
            raise RuntimeError("PeerFold is not running")
        return cls._instance

    @classmethod
    def run(cls, *, pdf: Path | None, reviewer: str) -> None:
        if not webview_available():
            raise WebviewUnavailableError("pywebview is not installed")
        host = cls._instance = cls(reviewer)
        host.open_document(pdf)
        host._run_webview_loop()

    def documents(self) -> list[DocumentWindow]:
        with self._docs_lock:
            return list(self._documents)

    def api_for_active_window(self):
        import webview

        docs = self.documents()
        active = webview.active_window()
        if active is not None:
            for doc in docs:
                if doc.window is active and doc.api is not None:
                    return doc.api
            for doc in docs:
                if doc.window is not None and doc.window.uid == active.uid and doc.api is not None:
                    return doc.api
        for doc in docs:
            if doc.api is not None:
                return doc.api
        for win in webview.windows:
            for doc in docs:
                if doc.window is win and doc.api is not None:
                    return doc.api
        return None

    def active_document(self) -> DocumentWindow | None:
        import webview

        docs = self.documents()
        active = webview.active_window()
        if active is not None:
            for doc in docs:
                if doc.window is active:
                    return doc
            for doc in docs:
                if doc.window is not None and doc.window.uid == active.uid:
                    return doc
        return docs[0] if docs else None

    def export_comments(self, fmt: str) -> None:
        doc = self.active_document()
        if doc is None or doc.window is None:
            return
        threading.Thread(
            target=self._export_comments_worker,
            args=(doc, fmt),
            name="peerfold-export",
            daemon=True,
        ).start()

    def copy_comments(self) -> None:
        doc = self.active_document()
        if doc is None or doc.window is None:
            return
        threading.Thread(
            target=self._copy_comments_worker,
            args=(doc,),
            name="peerfold-copy-comments",
            daemon=True,
        ).start()

    def _export_comments_worker(self, doc: DocumentWindow, fmt: str) -> None:
        from peerfold.native_dialogs import save_text_file

        try:
            payload = doc.session.export_comments_payload(fmt)
            result = save_text_file(doc.window, payload["suggested_name"], payload["text"], fmt)
            if result.get("ok"):
                count = payload["count"]
                suffix = "" if count == 1 else "s"
                self._notify_ui(doc, f"Exported {count} comment{suffix}", 2500)
            elif not result.get("cancelled"):
                self._notify_ui(doc, result.get("error") or "Could not save export", 3000)
        except ValueError as exc:
            self._notify_ui(doc, str(exc), 3000)
        except Exception as exc:
            self._notify_ui(doc, str(exc) or "Could not export comments", 3000)

    def _copy_comments_worker(self, doc: DocumentWindow) -> None:
        try:
            payload = doc.session.export_comments_payload("text")
            self._copy_text_to_clipboard(payload["text"])
            count = payload["count"]
            suffix = "" if count == 1 else "s"
            self._notify_ui(doc, f"All {count} comment{suffix} copied", 2000)
        except ValueError as exc:
            self._notify_ui(doc, str(exc), 3000)
        except Exception as exc:
            self._notify_ui(doc, str(exc) or "Could not copy comments", 3000)

    @staticmethod
    def _copy_text_to_clipboard(text: str) -> None:
        if sys.platform == "darwin":
            import AppKit

            pasteboard = AppKit.NSPasteboard.generalPasteboard()
            pasteboard.clearContents()
            pasteboard.setString_forType_(text, AppKit.NSStringPboardType)
            return
        raise RuntimeError("clipboard copy requires the in-app Copy button")

    @staticmethod
    def _notify_ui(doc: DocumentWindow, message: str, ms: int) -> None:
        if doc.window is None:
            return
        escaped = json.dumps(message)
        doc.window.evaluate_js(f"window.peerfoldToast?.({escaped}, {int(ms)})")

    def open_document(self, pdf: Path | None) -> DocumentWindow | None:
        if pdf is not None:
            pdf = pdf.expanduser().resolve()
            if not pdf.is_file():
                return None

        doc = DocumentWindow(self, self.reviewer, pdf)
        doc.start_server()
        with self._docs_lock:
            first_window = not self._documents
            self._documents.append(doc)

        if first_window:
            print_launch_banner(pdf=pdf, local_url=doc.url)
            if terminal_verbose():
                print_review_target(doc.session)

        if self._started:
            threading.Thread(
                target=doc.create_webview_window,
                name="peerfold-new-window",
                daemon=True,
            ).start()
        return doc

    def open_document_path(self, path: str) -> None:
        self.menu_api._open_recent_on_main(path)

    def open_via_dialog(self) -> None:
        def worker() -> None:
            path = self._pick_pdf_path()
            if path:
                run_on_main_thread(lambda: self.menu_api._open_recent_on_main(path))

        threading.Thread(target=worker, name="peerfold-open-dialog", daemon=True).start()

    def open_empty_window(self) -> None:
        self.open_document(None)

    def duplicate_active_window(self) -> None:
        import webview

        active = webview.active_window()
        for doc in self.documents():
            if doc.window is active or (
                active is not None
                and doc.window is not None
                and doc.window.uid == active.uid
            ):
                info = doc.session.document_info()
                source = str(info.get("source") or "").strip()
                if info.get("open") and source:
                    self.open_document(Path(source))
                else:
                    self.open_empty_window()
                return
        self.open_empty_window()

    def _pick_pdf_path(self) -> str | None:
        import webview

        from peerfold.native_dialogs import pick_pdf_file

        win = webview.active_window()
        if win is None and webview.windows:
            win = webview.windows[0]
        return pick_pdf_file(win)

    def _on_document_closed(self, doc: DocumentWindow) -> None:
        with self._docs_lock:
            if doc in self._documents:
                self._documents.remove(doc)
        doc.shutdown()

    def _run_webview_loop(self) -> None:
        import webview

        first = self._documents[0]
        first.create_webview_window()

        def on_start() -> None:
            try:
                _set_application_icon()
                _bind_native_drop_paths(first.window)
                refresh_application_menu(self.menu_api)
                if sys.platform == "darwin":
                    from peerfold.macos_events import install_open_documents_handler

                    install_open_documents_handler(self.open_document_path)
            except Exception:
                pass

        def on_first_shown(_window=None) -> None:
            self._started = True
            try:
                if sys.platform == "darwin":
                    from peerfold.macos_events import (
                        install_dock_menu_handler,
                        install_dock_reopen_handler,
                    )

                    install_dock_reopen_handler(self.open_empty_window)
                    install_dock_menu_handler(self.menu_api)
            except Exception:
                pass

        first.window.events.shown += on_first_shown

        try:
            webview.start(
                on_start,
                menu=build_application_menu(self.menu_api),
                debug=False,
            )
        finally:
            with self._docs_lock:
                docs = list(self._documents)
                self._documents.clear()
            for doc in docs:
                doc.shutdown()
            AppHost._instance = None
            farewell_message()


def run_webview_app(pdf: Path | None, *, reviewer: str) -> None:
    """Start PeerFold with one or more native document windows."""
    AppHost.run(pdf=pdf, reviewer=reviewer)
