#!/usr/bin/env python3
"""Sync peerfold.py launcher pin from package __version__."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sync_launcher(path: Path, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^(PEERFOLD_VERSION\s*=\s*")[^"]+(")',
        rf'\g<1>{version}\2',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f"Could not update PEERFOLD_VERSION in {path}")
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    init = (ROOT / "src" / "peerfold" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    if not match:
        raise SystemExit("Could not read package version")
    version = match.group(1)
    changed = False
    for rel in ("peerfold.py", "docs/peerfold.py"):
        if sync_launcher(ROOT / rel, version):
            print(f"updated {rel} -> {version}")
            changed = True
    if not changed:
        print(f"launcher pins already at {version}")


if __name__ == "__main__":
    main()
