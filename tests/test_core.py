from pathlib import Path

import pytest

from peerfold.core import (
    annotated_path,
    build_citation_index,
    cite_numbers_for_link,
    import_fitz,
    pick_cite_for_click,
    sanitize_reviewer,
    static_root,
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


def test_static_root_exists():
    root = static_root()
    assert (root / "index.html").is_file()
    assert (root / "app.js").is_file()


def test_citation_helpers_on_sample_pdf():
    sample = Path(__file__).resolve().parent / "fixtures" / "sample.pdf"
    if not sample.is_file():
        pytest.skip("sample fixture missing")
    fitz = import_fitz()
    doc = fitz.open(sample)
    entries, urls = build_citation_index(doc)
    assert entries
    assert urls
