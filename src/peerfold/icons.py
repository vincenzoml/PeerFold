"""PeerFold icon paths (generated from assets/icon.svg)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def icon_png(size: int = 512) -> Path:
    static = Path(str(files("peerfold") / "static"))
    path = static / f"icon-{size}.png"
    if path.is_file():
        return path
    fallback = Path(__file__).resolve().parent / "static" / f"icon-{size}.png"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"PeerFold icon missing (icon-{size}.png); run scripts/build_icon.py")


def favicon_png() -> Path:
    static = Path(str(files("peerfold") / "static"))
    path = static / "favicon.png"
    if path.is_file():
        return path
    return icon_png(32)
