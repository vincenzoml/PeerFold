#!/usr/bin/env python3
"""Build a one-file PeerFold executable with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path


def artifact_path(dist: Path, name: str) -> Path:
    base = name[:-4] if name.lower().endswith(".exe") else name
    if sys.platform == "win32":
        return dist / f"{base}.exe"
    return dist / base


def pyinstaller_extras() -> list[str]:
    extras = [
        "--hidden-import",
        "fitz",
        "--collect-submodules",
        "fitz",
        "--hidden-import",
        "webview",
        "--collect-all",
        "webview",
        "--collect-all",
        "clr_loader",
        "--copy-metadata",
        "pywebview",
    ]
    if sys.platform == "win32":
        extras.extend(
            [
                "--hidden-import",
                "webview.platforms.winforms",
                "--hidden-import",
                "webview.platforms.edgechromium",
            ]
        )
    elif sys.platform == "darwin":
        extras.extend(
            [
                "--hidden-import",
                "webview.platforms.cocoa",
            ]
        )
    else:
        extras.extend(
            [
                "--hidden-import",
                "webview.platforms.gtk",
            ]
        )
    return extras


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--name",
        default="peerfold",
        help="Output executable base name (e.g. peerfold-macos; .exe added on Windows)",
    )
    args = ap.parse_args()
    base = args.name[:-4] if args.name.lower().endswith(".exe") else args.name

    root = Path(__file__).resolve().parents[1]
    static = Path(str(files("peerfold") / "static"))
    if not static.is_dir():
        static = root / "src" / "peerfold" / "static"
    if not static.is_dir():
        raise SystemExit("Cannot locate peerfold/static — install the package first")

    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{static}{sep}peerfold/static"
    dist = root / "dist"
    if dist.exists():
        shutil.rmtree(dist)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        base,
        "--add-data",
        add_data,
        *pyinstaller_extras(),
        str(root / "src" / "peerfold" / "cli.py"),
    ]
    subprocess.run(cmd, cwd=root, check=True)
    out = artifact_path(dist, base)
    if not out.is_file():
        raise SystemExit(f"Expected build output missing: {out}")
    print(f"Built {out}")


if __name__ == "__main__":
    main()
