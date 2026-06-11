"""Keep repo-root peerfold.py launcher from shadowing the peerfold package."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for index, entry in enumerate(list(sys.path)):
    try:
        if Path(entry).resolve() == ROOT:
            sys.path.pop(index)
            break
    except OSError:
        continue

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

loaded = sys.modules.get("peerfold")
launcher = str(ROOT / "peerfold.py")
if loaded is not None and getattr(loaded, "__file__", "") == launcher:
    del sys.modules["peerfold"]
