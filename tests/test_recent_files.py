from pathlib import Path

from peerfold.recent_files import add, clear, folder_short, list_paths, list_payload, menu_label, remove


def test_recent_files_roundtrip(tmp_path, monkeypatch):
    store = tmp_path / "recent.json"
    monkeypatch.setattr("peerfold.recent_files._store_path", lambda: store)
    monkeypatch.setattr("peerfold.recent_files.note_system_recent", lambda _path: None)
    monkeypatch.setattr("peerfold.recent_files._refresh_menu", lambda: None)

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


def test_recent_files_clear_and_remove(tmp_path, monkeypatch):
    store = tmp_path / "recent.json"
    monkeypatch.setattr("peerfold.recent_files._store_path", lambda: store)
    monkeypatch.setattr("peerfold.recent_files.note_system_recent", lambda _path: None)
    monkeypatch.setattr("peerfold.recent_files._refresh_menu", lambda: None)

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"%PDF-1.4")
    b.write_bytes(b"%PDF-1.4")
    add(a)
    add(b)

    remove(a)
    assert list_paths() == [b.resolve()]

    clear()
    assert list_paths() == []


def test_recent_files_prunes_missing(tmp_path, monkeypatch):
    store = tmp_path / "recent.json"
    monkeypatch.setattr("peerfold.recent_files._store_path", lambda: store)
    monkeypatch.setattr("peerfold.recent_files.note_system_recent", lambda _path: None)
    monkeypatch.setattr("peerfold.recent_files._refresh_menu", lambda: None)

    gone = tmp_path / "gone.pdf"
    store.write_text('["%s"]\n' % gone, encoding="utf-8")
    assert list_paths() == []


def test_recent_menu_label_uses_home(tmp_path, monkeypatch):
    monkeypatch.setattr("peerfold.recent_files.Path.home", lambda: tmp_path)
    pdf = tmp_path / "docs" / "paper.pdf"
    pdf.parent.mkdir()
    label = menu_label(pdf)
    assert "paper.pdf" in label
    assert "docs" in label


def test_list_payload(tmp_path, monkeypatch):
    store = tmp_path / "recent.json"
    monkeypatch.setattr("peerfold.recent_files._store_path", lambda: store)
    monkeypatch.setattr("peerfold.recent_files.note_system_recent", lambda _path: None)
    monkeypatch.setattr("peerfold.recent_files._refresh_menu", lambda: None)
    monkeypatch.setattr("peerfold.recent_files.Path.home", lambda: tmp_path)

    pdf = tmp_path / "papers" / "draft.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    add(pdf)

    payload = list_payload()
    assert len(payload) == 1
    assert payload[0]["name"] == "draft.pdf"
    assert payload[0]["path"] == str(pdf.resolve())
    assert folder_short(pdf.resolve()) == "~/papers"
