#!/usr/bin/env python3
"""Build PeerFold standalone executables with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "pyinstaller"
DIST_BUILD = ROOT / "dist" / "build"


def artifact_in_appdir(app_dir: Path, name: str) -> Path:
    base = name[:-4] if name.lower().endswith(".exe") else name
    if sys.platform == "win32":
        return app_dir / f"{base}.exe"
    return app_dir / base


def pyinstaller_extras() -> list[str]:
    return [
        "--hidden-import",
        "fitz",
        "--collect-submodules",
        "fitz",
    ]


def use_onedir() -> bool:
    # macOS/Linux: onedir + self-extracting wrapper. Windows: native onefile .exe.
    return sys.platform != "win32"


def package_outputs(app_dir: Path, name: str) -> list[Path]:
    from package_release import make_dmg, make_sfx, read_version  # noqa: PLC0415

    version = read_version(ROOT)
    dist = ROOT / "dist"
    outputs: list[Path] = []

    sfx_name = f"{name}.command" if sys.platform == "darwin" else name
    sfx = dist / sfx_name
    make_sfx(app_dir, sfx, name, version)
    outputs.append(sfx)

    if sys.platform == "darwin":
        dmg = dist / f"{name}.dmg"
        make_dmg(app_dir, dmg, name, version)
        outputs.append(dmg)

    return outputs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--name",
        default="peerfold",
        help="Output executable base name (e.g. peerfold-macos)",
    )
    args = ap.parse_args()
    base = args.name[:-4] if args.name.lower().endswith(".exe") else args.name

    static = Path(str(files("peerfold") / "static"))
    if not static.is_dir():
        static = ROOT / "src" / "peerfold" / "static"
    if not static.is_dir():
        raise SystemExit("Cannot locate peerfold/static — install the package first")

    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{static}{sep}peerfold/static"

    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    DIST_BUILD.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    bundle_flag = "--onedir" if use_onedir() else "--onefile"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        bundle_flag,
        "--name",
        base,
        "--distpath",
        str(DIST_BUILD),
        "--workpath",
        str(BUILD_ROOT),
        "--specpath",
        str(BUILD_ROOT),
        "--add-data",
        add_data,
        *pyinstaller_extras(),
        str(ROOT / "src" / "peerfold" / "cli.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)

    if use_onedir():
        app_dir = DIST_BUILD / base
        binary = artifact_in_appdir(app_dir, base)
        if not binary.is_file():
            raise SystemExit(f"Expected build output missing: {binary}")
        sys.path.insert(0, str(ROOT / "scripts"))
        packaged = package_outputs(app_dir, base)
        print(f"Built {binary}")
        for path in packaged:
            print(f"Packaged {path}")
    else:
        binary = DIST_BUILD / f"{base}.exe"
        if not binary.is_file():
            raise SystemExit(f"Expected build output missing: {binary}")
        final = dist / f"{base}.exe"
        shutil.move(str(binary), str(final))
        print(f"Built {final}")


if __name__ == "__main__":
    main()
