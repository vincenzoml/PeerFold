"""Multi-document native window host for PeerFold."""

from __future__ import annotations

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
    run_on_main_thread_sync,
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

    def open_document(self, pdf: Path | None) -> DocumentWindow | None:
        if pdf is not None:
            pdf = pdf.expanduser().resolve()
            if not pdf.is_file():
                return None

        doc = DocumentWindow(self, self.reviewer, pdf)
        doc.start_server()
        with self._docs_lock:
            self._documents.append(doc)

        if not self._documents:
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
        path = run_on_main_thread_sync(self._pick_pdf_path)
        if path:
            self.menu_api._open_recent_on_main(path)

    def open_empty_window(self) -> None:
        self.open_document(None)

    def _pick_pdf_path(self) -> str | None:
        import webview

        win = webview.active_window()
        if win is None and webview.windows:
            win = webview.windows[0]
        if win is None:
            return None
        result = win.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("PDF files (*.pdf)", "All files (*.*)"),
        )
        if not result:
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        return str(Path(path).expanduser().resolve())

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
                    from peerfold.macos_events import install_dock_reopen_handler

                    install_dock_reopen_handler(self.open_empty_window)
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
