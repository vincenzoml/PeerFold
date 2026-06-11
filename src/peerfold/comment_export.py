"""Export review comments to human-readable Markdown or plain text."""

from __future__ import annotations

from typing import Any, Literal

from peerfold.core import LINE_Y_TOL, _rects_overlap

ExportFormat = Literal["markdown", "text"]


def parse_toc(doc) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in doc.get_toc(simple=True) or []:
        if len(raw) < 3:
            continue
        level, title, page = int(raw[0]), str(raw[1]).strip(), int(raw[2])
        if not title:
            continue
        entries.append({"level": level, "title": title, "page": max(0, page - 1)})
    return entries


def section_for_page(toc: list[dict[str, Any]], page_index: int) -> str | None:
    best: dict[str, Any] | None = None
    for entry in toc:
        if entry["level"] > 2:
            continue
        if entry["page"] > page_index:
            continue
        if best is None or entry["page"] >= best["page"]:
            if best is None or entry["page"] > best["page"] or entry["level"] >= best["level"]:
                best = entry
    return best["title"] if best else None


def quote_for_rects(spans: list[dict[str, Any]], rects: list[list[float]]) -> str:
    if not spans or not rects:
        return ""
    hits = [sp for sp in spans if any(_rects_overlap(sp["bbox"], rect) for rect in rects)]
    if not hits:
        return ""
    ordered = sorted(hits, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    parts: list[str] = []
    last_y: float | None = None
    for sp in ordered:
        y = sp["bbox"][1]
        if last_y is not None and abs(y - last_y) > LINE_Y_TOL:
            parts.append("\n")
        elif parts and not parts[-1].endswith("\n"):
            parts.append(" ")
        parts.append(sp["text"])
        last_y = y
    return "".join(parts).strip()


def annotation_sort_key(ann: dict[str, Any]) -> tuple[int, float, float]:
    rects = ann.get("rects") or [[0.0, 0.0, 0.0, 0.0]]
    return (
        int(ann.get("page") or 0),
        min(r[1] for r in rects),
        min(r[0] for r in rects),
    )


def location_label(ann: dict[str, Any], section: str | None) -> str:
    page = int(ann.get("page") or 0) + 1
    bits = [f"p.{page}"]
    if section:
        bits.append(f"§ {section}")
    reviewer = (ann.get("title") or "").strip()
    if reviewer:
        bits.append(reviewer)
    color = (ann.get("color") or "").strip()
    if color:
        bits.append(color)
    return " · ".join(bits)


def _format_markdown(entries: list[dict[str, Any]], doc_name: str) -> str:
    lines = [f"# Comments on {doc_name}", ""]
    current_section: str | None = None
    for item in entries:
        section = item.get("section")
        if section and section != current_section:
            current_section = section
            lines.extend([f"## {section}", ""])
        meta = item["location"]
        quote = item["quote"]
        body = item["content"]
        lines.append(f"### {meta}")
        lines.append("")
        if quote:
            lines.append(f"> {quote.replace(chr(10), ' ')}")
            lines.append("")
        if body:
            lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_text(entries: list[dict[str, Any]], doc_name: str) -> str:
    lines = [f"Comments on {doc_name}", "=" * max(20, len(doc_name) + 12), ""]
    current_section: str | None = None
    for idx, item in enumerate(entries):
        if idx:
            lines.append("-" * 40)
            lines.append("")
        section = item.get("section")
        if section and section != current_section:
            current_section = section
            lines.extend([section.upper(), ""])
        lines.append(f"[{item['location']}]")
        quote = item["quote"]
        if quote:
            lines.append(f"\"{quote}\"")
            lines.append("")
        body = item["content"]
        if body:
            lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_export_entries(
    annotations: list[dict[str, Any]],
    *,
    page_spans: dict[int, list[dict[str, Any]]],
    toc: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(annotations, key=annotation_sort_key)
    entries: list[dict[str, Any]] = []
    for ann in ordered:
        page = int(ann.get("page") or 0)
        rects = ann.get("rects") or []
        spans = page_spans.get(page, [])
        quote = quote_for_rects(spans, rects)
        section = section_for_page(toc, page)
        entries.append(
            {
                "id": ann.get("id"),
                "section": section,
                "location": location_label(ann, section),
                "quote": quote,
                "content": (ann.get("content") or "").strip(),
            }
        )
    return entries


def export_comments(
    *,
    doc_name: str,
    annotations: list[dict[str, Any]],
    page_spans: dict[int, list[dict[str, Any]]],
    toc: list[dict[str, Any]],
    fmt: ExportFormat,
) -> str:
    entries = build_export_entries(annotations, page_spans=page_spans, toc=toc)
    if fmt == "markdown":
        return _format_markdown(entries, doc_name)
    return _format_text(entries, doc_name)


def suggested_export_name(doc_name: str, fmt: ExportFormat, *, selected: bool) -> str:
    stem = doc_name.rsplit(".", 1)[0] if "." in doc_name else doc_name
    suffix = "-selected-comments" if selected else "-comments"
    ext = "md" if fmt == "markdown" else "txt"
    return f"{stem}{suffix}.{ext}"
