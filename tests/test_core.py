from pathlib import Path

import pytest

from peerfold.core import (
    annotated_path,
    build_citation_index,
    cite_numbers_for_link,
    default_reviewer,
    import_fitz,
    parse_multipart_file_field,
    parse_version_parts,
    pick_cite_for_click,
    sanitize_reviewer,
    static_root,
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


def test_citation_helpers_on_sample_pdf():
    sample = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"
    if not sample.is_file():
        pytest.skip("sample fixture missing")
    fitz = import_fitz()
    doc = fitz.open(sample)
    entries, urls = build_citation_index(doc)
    assert entries
    assert urls
