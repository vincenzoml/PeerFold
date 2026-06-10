from pathlib import Path

from peerfold.recent_files import add, list_paths


def test_recent_files_roundtrip(tmp_path, monkeypatch):
    store = tmp_path / "recent.json"
    monkeypatch.setattr("peerfold.recent_files._store_path", lambda: store)
    monkeypatch.setattr("peerfold.recent_files.note_system_recent", lambda _path: None)

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"%PDF-1.4")
    b.write_bytes(b"%PDF-1.4")

    add(a)
    add(b)
    paths = list_paths()
    assert paths == [b.resolve(), a.resolve()]

    add(a)
    assert list_paths() == [a.resolve(), b.resolve()]
