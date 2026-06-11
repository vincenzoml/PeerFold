#!/usr/bin/env python3
"""Verify package, launcher, and wheel versions stay aligned."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_init_version() -> str:
    text = (ROOT / "src" / "peerfold" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("Could not read __version__ from src/peerfold/__init__.py")
    return match.group(1)


def read_launcher_pin() -> str:
    text = (ROOT / "peerfold.py").read_text(encoding="utf-8")
    match = re.search(r'^PEERFOLD_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise SystemExit("Could not read PEERFOLD_VERSION from peerfold.py")
    return match.group(1)


def read_docs_launcher_pin() -> str:
    text = (ROOT / "docs" / "peerfold.py").read_text(encoding="utf-8")
    match = re.search(r'^PEERFOLD_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise SystemExit("Could not read PEERFOLD_VERSION from docs/peerfold.py")
    return match.group(1)


def read_built_wheel_version() -> str | None:
    dist = ROOT / "dist"
    wheels = sorted(dist.glob("peerfold_review-*.whl"))
    if not wheels:
        return None
    name = wheels[-1].name
    match = re.match(r"peerfold_review-([^-]+)-", name)
    return match.group(1) if match else None


def main() -> None:
    package = read_init_version()
    launcher = read_launcher_pin()
    docs_launcher = read_docs_launcher_pin()
    wheel = read_built_wheel_version()

    errors: list[str] = []
    if launcher != package:
        errors.append(f"peerfold.py pin {launcher} != package {package}")
    if docs_launcher != package:
        errors.append(f"docs/peerfold.py pin {docs_launcher} != package {package}")
    if wheel is not None and wheel != package:
        errors.append(f"built wheel {wheel} != package {package}")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        raise SystemExit(1)

    print(f"versions aligned at {package}" + (f" (wheel {wheel})" if wheel else ""))


if __name__ == "__main__":
    main()
