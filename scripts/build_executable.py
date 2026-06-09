#!/usr/bin/env python3
"""Build a one-file PaperTrail executable with PyInstaller."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    static = Path(str(files("papertrail") / "static"))
    if not static.is_dir():
        # Editable install: static lives in src/
        static = root / "src" / "papertrail" / "static"
    if not static.is_dir():
        raise SystemExit("Cannot locate papertrail/static — install the package first")

    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{static}{sep}papertrail/static"
    dist = root / "dist"
    if dist.exists():
        shutil.rmtree(dist)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "papertrail",
        "--add-data",
        add_data,
        "--hidden-import",
        "fitz",
        "--collect-submodules",
        "fitz",
        str(root / "src" / "papertrail" / "cli.py"),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    print(f"Built {list(dist.glob('papertrail*'))}")


if __name__ == "__main__":
    main()
