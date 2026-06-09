#!/usr/bin/env python3
"""Build PeerFold standalone executables with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path


def artifact_path(dist: Path, name: str) -> Path:
    base = name[:-4] if name.lower().endswith(".exe") else name
    if sys.platform == "darwin":
        return dist / base / base
    if sys.platform == "win32":
        return dist / f"{base}.exe"
    return dist / base


def pyinstaller_extras() -> list[str]:
    # Standalone builds use the system browser (no pywebview) for fast, reliable startup.
    return [
        "--hidden-import",
        "fitz",
        "--collect-submodules",
        "fitz",
    ]


def package_macos(dist: Path, name: str) -> Path:
    archive = dist / f"{name}.zip"
    if archive.exists():
        archive.unlink()
    shutil.make_archive(str(archive.with_suffix("")), "zip", dist, name)
    return archive


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

    # macOS onefile hangs in the PyInstaller bootloader; use onedir + zip.
    bundle = "--onedir" if sys.platform == "darwin" else "--onefile"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        bundle,
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

    if sys.platform == "darwin":
        archive = package_macos(dist, base)
        print(f"Built {out}")
        print(f"Packaged {archive}")
    else:
        print(f"Built {out}")


if __name__ == "__main__":
    main()
