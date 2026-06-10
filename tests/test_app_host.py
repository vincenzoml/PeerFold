import threading
from pathlib import Path

import pytest

from peerfold.app_host import AppHost, DocumentWindow


@pytest.fixture
def host():
    previous = AppHost._instance
    AppHost._instance = None
    h = AppHost("tester")
    AppHost._instance = h
    yield h
    AppHost._instance = previous


def test_open_document_starts_isolated_servers(host, tmp_path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")

    doc_a = host.open_document(pdf_a)
    doc_b = host.open_document(pdf_b)

    assert doc_a is not None and doc_b is not None
    assert doc_a.port != doc_b.port
    assert doc_a.url != doc_b.url
    assert len(host.documents()) == 2


def test_open_document_path_ignores_non_pdf(host, tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    before = len(host.documents())
    host.open_document_path(str(text))
    assert len(host.documents()) == before


def test_document_close_shuts_down_server(host, tmp_path):
    pdf = tmp_path / "one.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    doc = host.open_document(pdf)
    assert doc is not None
    thread = doc._thread
    host._on_document_closed(doc)
    assert doc not in host.documents()
    thread.join(timeout=2)


def test_additional_window_spawns_on_background_thread(host, tmp_path, monkeypatch):
    pdf = tmp_path / "bg.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    host._started = True
    created = threading.Event()

    def fake_create(self):
        created.set()

    monkeypatch.setattr(DocumentWindow, "create_webview_window", fake_create)
    host.open_document(pdf)
    assert created.wait(timeout=2)


def test_create_webview_window_does_not_bind_drop_at_creation(monkeypatch):
    bound = []

    class FakeEventSlot:
        def __iadd__(self, _fn):
            return self

    class FakeEvents:
        closed = FakeEventSlot()
        loaded = FakeEventSlot()

    class FakeWindow:
        events = FakeEvents()

    class FakeApi:
        def set_window(self, _window):
            pass

    monkeypatch.setattr("peerfold.app_host._bind_native_drop_paths", lambda _w: bound.append(True))
    monkeypatch.setattr("peerfold.ui.PeerFoldApi", FakeApi)
    monkeypatch.setattr("webview.create_window", lambda *a, **k: FakeWindow())

    host = AppHost("tester")
    doc = DocumentWindow(host, "tester", None)
    doc.create_webview_window()
    assert bound == []
