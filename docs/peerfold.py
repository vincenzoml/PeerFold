#!/usr/bin/env python3
"""Repo-local PeerFold launcher: venv + pip install/upgrade + run.

Copy into any paper repo as scripts/peerfold.py, then:

    python3 scripts/peerfold.py review-builds/paper.pdf --reviewer AB

Creates .venv-peerfold/ (gitignored), installs peerfold-review from PyPI,
and runs peerfold. Safe to re-run — upgrades to the latest release each time.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv-peerfold"
PACKAGE = "peerfold-review"


def venv_paths() -> tuple[Path, Path]:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe", VENV / "Scripts" / "peerfold.exe"
    return VENV / "bin" / "python", VENV / "bin" / "peerfold"


def ensure_venv() -> tuple[Path, Path]:
    py, peerfold = venv_paths()
    if not py.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run(
        [str(py), "-m", "pip", "install", "-U", "pip", PACKAGE],
        check=True,
    )
    if not peerfold.is_file():
        raise SystemExit(f"peerfold not found after installing {PACKAGE}")
    return py, peerfold


def main() -> None:
    _, peerfold = ensure_venv()
    result = subprocess.run([str(peerfold), *sys.argv[1:]])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
