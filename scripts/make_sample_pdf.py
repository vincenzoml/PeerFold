#!/usr/bin/env python3
"""Create tests/fixtures/sample.pdf with a minimal References section."""

from pathlib import Path

import fitz

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.pdf"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    page0 = doc.load_page(0)
    page1 = doc.load_page(1)
    page0.insert_text((72, 72), "Sample paper with a citation [1].", fontsize=12)
    page1.insert_text((72, 72), "References", fontsize=14)
    page1.insert_text((72, 96), "1. Example Reference https://doi.org/10.1000/example", fontsize=11)
    page1.insert_link(
        {
            "kind": fitz.LINK_URI,
            "from": fitz.Rect(72, 94, 300, 108),
            "uri": "https://doi.org/10.1000/example",
        }
    )
    page0.insert_link(
        {
            "kind": fitz.LINK_GOTO,
            "from": fitz.Rect(280, 70, 295, 84),
            "page": 1,
            "to": fitz.Point(72, 96),
        }
    )
    doc.save(OUT)
    doc.close()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
