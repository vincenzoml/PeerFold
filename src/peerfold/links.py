"""Official PeerFold URLs."""

from __future__ import annotations

from pathlib import Path

WEBSITE = "https://vincenzoml.github.io/PeerFold/"
REPOSITORY = "https://github.com/vincenzoml/PeerFold"

ABOUT_TAGLINE = "PDF review with standard highlight annotations."


def launch_banner_lines(
    *,
    version: str,
    pdf: Path | None = None,
    local_url: str | None = None,
) -> list[str]:
    if pdf is not None:
        head = f"PeerFold {version} · {pdf.name}"
    else:
        head = f"PeerFold {version}"
    lines = [head, f"Website: {WEBSITE}", f"GitHub:  {REPOSITORY}"]
    if local_url:
        lines.append(f"Open:    {local_url}")
    return lines


def about_body(*, version: str) -> str:
    return f"{ABOUT_TAGLINE}\n\n{WEBSITE}\n{REPOSITORY}"
