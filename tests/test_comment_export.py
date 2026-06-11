import fitz

from peerfold.comment_export import (
    build_export_entries,
    export_comments,
    parse_toc,
    quote_for_rects,
    section_for_page,
    suggested_export_name,
)


def test_section_for_page_uses_nearest_outline():
    toc = [
        {"level": 1, "title": "Introduction", "page": 0},
        {"level": 2, "title": "Methods", "page": 2},
    ]
    assert section_for_page(toc, 0) == "Introduction"
    assert section_for_page(toc, 1) == "Introduction"
    assert section_for_page(toc, 2) == "Methods"
    assert section_for_page(toc, 5) == "Methods"
    assert section_for_page([], 0) is None


def test_quote_for_rects_joins_words_on_line():
    spans = [
        {"text": "hello", "bbox": [72.0, 100.0, 90.0, 110.0]},
        {"text": "world", "bbox": [92.0, 100.0, 120.0, 110.0]},
        {"text": "next", "bbox": [72.0, 112.0, 90.0, 122.0]},
    ]
    quote = quote_for_rects(spans, [[70.0, 99.0, 125.0, 111.0]])
    assert quote == "hello world"


def test_export_comments_markdown_and_text():
    annotations = [
        {
            "id": 1,
            "page": 0,
            "rects": [[72.0, 100.0, 120.0, 110.0]],
            "color": "yellow",
            "content": "Needs citation.",
            "title": "VC",
        }
    ]
    spans = {0: [{"text": "hello", "bbox": [72.0, 100.0, 120.0, 110.0]}]}
    toc = [{"level": 1, "title": "Intro", "page": 0}]
    md = export_comments(
        doc_name="paper.pdf",
        annotations=annotations,
        page_spans=spans,
        toc=toc,
        fmt="markdown",
    )
    assert "# Comments on paper.pdf" in md
    assert "Needs citation." in md
    assert "hello" in md
    assert "VC" in md
    txt = export_comments(
        doc_name="paper.pdf",
        annotations=annotations,
        page_spans=spans,
        toc=toc,
        fmt="text",
    )
    assert "Comments on paper.pdf" in txt
    assert "Needs citation." in txt


def test_build_export_entries_sorts_by_page_and_position():
    annotations = [
        {"id": 2, "page": 1, "rects": [[0, 0, 1, 1]], "content": "b", "title": "", "color": "blue"},
        {"id": 1, "page": 0, "rects": [[0, 0, 1, 1]], "content": "a", "title": "", "color": "yellow"},
    ]
    entries = build_export_entries(annotations, page_spans={}, toc=[])
    assert [e["content"] for e in entries] == ["a", "b"]


def test_suggested_export_name():
    assert suggested_export_name("main.pdf", "markdown", selected=False) == "main-comments.md"
    assert suggested_export_name("main.pdf", "text", selected=True) == "main-selected-comments.txt"


def test_parse_toc_from_pdf(tmp_path):
    pdf = tmp_path / "toc.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.set_toc([[1, "Chapter One", 1], [2, "Section A", 2]])
    doc.save(pdf)
    doc.close()
    doc = fitz.open(pdf)
    toc = parse_toc(doc)
    doc.close()
    assert toc[0]["title"] == "Chapter One"
    assert toc[0]["page"] == 0
    assert toc[1]["page"] == 1
