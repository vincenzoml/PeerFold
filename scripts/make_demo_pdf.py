#!/usr/bin/env python3
"""Create docs/demo.pdf — fictional paper with baked-in highlights for marketing screenshots."""

from __future__ import annotations

from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo.pdf"

BODY = """Latent Geometry of Synthetic Neural Manifolds
R. Brook · T. Hale · K. Mensch
Institute for Fictional Science, Example City

ABSTRACT
We study how latent representations fold under cohort-level validation across
synthetic neural manifolds. Recent work suggests manifold curvature predicts
generalization better than parameter count [1,2]. We report three findings across
twelve fictional benchmarks and release all code under a permissive license.

1. INTRODUCTION
Scientific peer review should focus on claims, not formatting. Our baseline
comparison against prior manifold-learning methods remains limited to synthetic
tasks. Topological summaries align with Chen et al. [1] but require clearer
notation for readers unfamiliar with persistent homology.

2. METHODS
We estimate manifold curvature from Jacobian spectra on held-out folds. Each
cohort-level validation split uses disjoint subject IDs. Hyperparameters follow
Vale & Mensch [2] unless noted otherwise.
"""

REFERENCES = """References

1. Chen, R., Hale, T. Geometry of latent folds. Journal of Fictional ML 4(1), 2024.
   https://doi.org/10.5555/fictional-chen-2024

2. Vale, K., Mensch, K. Curvature and generalization in synthetic manifolds. Proc. Fictional AI, 2023.
   https://doi.org/10.5555/fictional-vale-2023
"""

HIGHLIGHTS = [
    {
        "phrase": "cohort-level validation",
        "color": (1.0, 0.92, 0.23),
        "reviewer": "RB",
        "comment": "Define cohort here — single-site or multi-site?",
    },
    {
        "phrase": "manifold curvature",
        "color": (0.55, 0.76, 0.29),
        "reviewer": "RB",
        "comment": "Does [1] actually support this? Their method assumes Euclidean embeddings.",
    },
    {
        "phrase": "baseline comparison",
        "color": (0.96, 0.56, 0.69),
        "reviewer": "RB",
        "comment": "Add a standard ImageNet baseline — hard to judge improvement without it.",
    },
]


def _add_cite_links(page: fitz.Page, ref_page: int) -> None:
    for token in ("[1,2]", "[1]", "[2]"):
        hits = page.search_for(token)
        if not hits:
            continue
        page.insert_link(
            {
                "kind": fitz.LINK_GOTO,
                "from": hits[0],
                "page": ref_page,
                "to": fitz.Point(72, 120),
            }
        )


def _add_ref_links(page: fitz.Page) -> None:
    for doi in ("10.5555/fictional-chen-2024", "10.5555/fictional-vale-2023"):
        hits = page.search_for(doi)
        if not hits:
            continue
        page.insert_link(
            {
                "kind": fitz.LINK_URI,
                "from": hits[0],
                "uri": f"https://doi.org/{doi}",
            }
        )


def _add_highlights(page: fitz.Page, spec: dict) -> None:
    hits = page.search_for(spec["phrase"])
    if not hits:
        raise RuntimeError(f"phrase not found: {spec['phrase']!r}")
    annot = page.add_highlight_annot(hits[0].quad)
    annot.set_colors(stroke=spec["color"])
    annot.set_info(title=spec["reviewer"], content=spec["comment"])
    annot.set_opacity(0.45)
    annot.update()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    body_page = doc.load_page(0)
    ref_page = doc.load_page(1)
    body_page.insert_textbox(fitz.Rect(72, 72, 523, 770), BODY, fontsize=11, lineheight=1.35)
    ref_page.insert_textbox(fitz.Rect(72, 72, 523, 770), REFERENCES, fontsize=10.5, lineheight=1.35)
    _add_cite_links(body_page, ref_page.number)
    _add_ref_links(ref_page)
    for spec in HIGHLIGHTS:
        _add_highlights(body_page, spec)
    doc.save(OUT, garbage=3, deflate=True)
    doc.close()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
