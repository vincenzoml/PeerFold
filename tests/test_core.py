from datetime import date
from pathlib import Path

import pytest

from peerfold import __version__
from peerfold.core import (
    PALETTE,
    PdfSession,
    _rects_overlap,
    annotated_path,
    app_version,
    build_citation_index,
    cite_numbers_for_link,
    default_reviewer,
    hex_to_rgb,
    import_fitz,
    nearest_palette_name,
    parse_multipart_file_field,
    parse_version_parts,
    pick_cite_for_click,
    resolve_color,
    rgb_to_hex,
    sanitize_reviewer,
    save_copy_enabled,
    ServerSession,
    session_paths,
    static_root,
    update_check_payload,
    version_newer,
)


def test_sanitize_reviewer_ok():
    assert sanitize_reviewer("VC") == "VC"
    assert sanitize_reviewer("alice.bob") == "alice.bob"


def test_sanitize_reviewer_bad():
    with pytest.raises(ValueError):
        sanitize_reviewer("way too long a name")


def test_annotated_path():
    p = annotated_path(Path("draft.pdf"), "VC", stamp="2026-06-09")
    assert p.name == "draft_VC-2026-06-09.pdf"


def test_parse_multipart_file_field():
    boundary = "----PeerFoldTest"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="paper.pdf"\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
        "%PDF-1.4 test"
        f"\r\n--{boundary}--\r\n"
    ).encode("ascii")
    name, data = parse_multipart_file_field(
        body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    assert name == "paper.pdf"
    assert data == b"%PDF-1.4 test"


def test_annotated_path_beside_source():
    src = Path("/Users/reviewer/Desktop/paper.pdf")
    out = annotated_path(src, "VC", stamp="2026-06-09")
    assert out.parent == src.parent
    assert out.name == "paper_VC-2026-06-09.pdf"


def test_save_copy_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PEERFOLD_SAVE_COPY", raising=False)
    assert not save_copy_enabled()


def test_session_paths_in_place(monkeypatch, tmp_path):
    monkeypatch.delenv("PEERFOLD_SAVE_COPY", raising=False)
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"x")
    open_path, save_path = session_paths(source, "VC")
    assert open_path == save_path == source.resolve()


def test_session_paths_sidecar_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("PEERFOLD_SAVE_COPY", "1")
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"x")
    open_path, save_path = session_paths(source, "VC")
    assert open_path == source.resolve()
    assert save_path.name == "paper_VC-" + date.today().isoformat() + ".pdf"


def test_static_root_exists():
    root = static_root()
    assert (root / "index.html").is_file()
    assert (root / "app.js").is_file()


def test_version_newer():
    assert version_newer("0.1.12", "0.1.11")
    assert version_newer("0.2.0", "0.1.99")
    assert not version_newer("0.1.11", "0.1.11")
    assert not version_newer("0.1.10", "0.1.11")
    assert parse_version_parts("v0.1.12") == (0, 1, 12)


def test_default_reviewer(monkeypatch):
    import getpass

    monkeypatch.delenv("PEERFOLD_REVIEWER", raising=False)
    monkeypatch.delenv("REVIEW_VIEWER", raising=False)
    monkeypatch.setattr(getpass, "getuser", lambda: "vincenzo")
    assert default_reviewer() == "vincenzo"


def test_app_version_matches_package():
    assert app_version() == __version__


def test_empty_document_includes_app_version():
    session = ServerSession("VC", None)
    info = session.document_info()
    assert info["app_version"] == __version__


def test_update_check_payload_shape():
    payload = update_check_payload()
    assert payload["current"] == __version__
    assert "latest" in payload
    assert "update_available" in payload
    assert "check_ok" in payload
    assert "can_install" in payload
    assert "download_url" in payload
    assert payload["url"].startswith("https://github.com/")


def test_citation_helpers_on_sample_pdf():
    sample = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"
    if not sample.is_file():
        pytest.skip("sample fixture missing")
    fitz = import_fitz()
    doc = fitz.open(sample)
    entries, urls = build_citation_index(doc)
    assert entries
    assert urls


def test_resolve_color_named_and_hex():
    name, rgb = resolve_color("blue")
    assert name == "blue"
    assert rgb == PALETTE["blue"]
    name, rgb = resolve_color("#a1b2c3")
    assert name == "#a1b2c3"
    assert rgb_to_hex(rgb) == "#a1b2c3"


def test_hex_to_rgb_roundtrip():
    rgb = hex_to_rgb("#ff8040")
    assert rgb_to_hex(rgb) == "#ff8040"


def test_nearest_palette_name_returns_hex_for_unknown():
    custom = (0.12, 0.34, 0.56)
    assert nearest_palette_name(custom) == rgb_to_hex(custom)


def test_batch_update_colors(tmp_path, monkeypatch):
    monkeypatch.delenv("PEERFOLD_SAVE_COPY", raising=False)
    fitz = import_fitz()
    pdf = tmp_path / "batch.pdf"
    doc = fitz.open()
    page = doc.new_page()
    for y in (72, 96, 120):
        page.insert_text((72, y), "highlight target")
    doc.save(pdf)
    doc.close()

    session = PdfSession(pdf, "VC", fitz, defer_maintenance=True)
    try:
        spans = session.page_spans(0)
        assert len(spans) >= 3
        highlight_ids = [s["id"] for s in spans if s["text"] == "highlight"]
        assert len(highlight_ids) == 3
        ids = []
        for sid in highlight_ids:
            created = session.create_highlight(0, [sid], "yellow", f"note {sid}")
            ids.append(created["id"])
        result = session.batch_update_colors(ids, "blue")
        assert len(result["items"]) == 3
        assert all(item["color"] == "blue" for item in result["items"])
        listed = session.list_annotations()
        assert len(listed) == 3
        assert all(item["color"] == "blue" for item in listed)
    finally:
        session.close()


def test_rects_overlap_corner_touch_is_not_overlap():
    new_rect = [270.2026110197368, 167.78248596191406, 304.9469299316406, 182.896484375]
    existing = [304.9469299316406, 151.8187255859375, 411.3168640136719, 166.9327392578125]
    assert not _rects_overlap(new_rect, existing)


def test_rects_overlap_positive_area():
    assert _rects_overlap([0, 0, 10, 10], [5, 5, 15, 15])
    assert not _rects_overlap([0, 0, 10, 10], [10, 0, 20, 10])
    assert not _rects_overlap([0, 0, 10, 10], [0, 10, 10, 20])
