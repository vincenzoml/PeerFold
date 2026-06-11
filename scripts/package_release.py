#!/usr/bin/env python3
"""Package onedir builds as self-extracting binaries and macOS DMG installers."""

from __future__ import annotations

import importlib.util
import io
import plistlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

MARKER = "__ARCHIVE__\n"

STUB = """#!/usr/bin/env bash
set -euo pipefail
NAME="__NAME__"
VERSION="__VERSION__"
if [[ "$OSTYPE" == darwin* ]]; then
  ROOT="${HOME}/Library/Caches/PeerFold/${VERSION}"
else
  ROOT="${XDG_CACHE_HOME:-${HOME}/.cache}/peerfold/${VERSION}"
fi
MARKER="${ROOT}/.installed"
ARCHIVE_LINE=$(awk '/^__ARCHIVE__$/{print NR + 1; exit 0;}' "$0")
mkdir -p "${ROOT}"
if [[ ! -f "${MARKER}" ]]; then
  rm -rf "${ROOT:?}/"*
  tail -n "+${ARCHIVE_LINE}" "$0" | tar xz -C "${ROOT}"
  touch "${MARKER}"
fi
RUN="${ROOT}/${NAME}/${NAME}"
exec "${RUN}" "$@"
"""

LAUNCHER = """#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources/runtime" && pwd)"
RUN="${DIR}/__BINARY__"
if [[ $# -eq 0 ]]; then
  PDF=$(osascript -e 'POSIX path of (choose file with prompt "Select PDF to review" of type {"com.adobe.pdf", "pdf"})' 2>/dev/null || true)
  [[ -z "${PDF}" ]] && exit 0
  exec -a PeerFold "${RUN}" "${PDF}"
fi
exec -a PeerFold "${RUN}" "$@"
"""

MACOS_LAUNCHER_SRC = Path(__file__).resolve().parent / "macos" / "peerfold_launcher.m"


def _compile_macos_launcher(macos_dir: Path, binary_name: str) -> Path:
    if not MACOS_LAUNCHER_SRC.is_file():
        raise SystemExit(f"macOS launcher source missing: {MACOS_LAUNCHER_SRC}")
    launcher = macos_dir / "peerfold"
    source = MACOS_LAUNCHER_SRC.read_text(encoding="utf-8").replace("__BINARY__", binary_name)
    src = macos_dir / "_peerfold_launcher.m"
    src.write_text(source, encoding="utf-8")
    try:
        subprocess.run(
            [
                "clang",
                "-fobjc-arc",
                "-O2",
                "-framework",
                "Cocoa",
                "-framework",
                "UniformTypeIdentifiers",
                "-o",
                str(launcher),
                str(src),
            ],
            check=True,
        )
    finally:
        src.unlink(missing_ok=True)
    launcher.chmod(0o755)
    return launcher


def _install_macos_launcher(macos_dir: Path, binary_name: str) -> None:
    if sys.platform == "darwin" and shutil.which("clang"):
        _compile_macos_launcher(macos_dir, binary_name)
        return
    launcher = macos_dir / "peerfold"
    launcher.write_text(LAUNCHER.replace("__BINARY__", binary_name), encoding="utf-8")
    launcher.chmod(0o755)


def _macos_bundle_plist_extras() -> dict[str, object]:
    """Load plist extras without importing the peerfold package (peerfold.py shadows it)."""
    handlers_py = Path(__file__).resolve().parents[1] / "src" / "peerfold" / "handlers.py"
    spec = importlib.util.spec_from_file_location("_peerfold_handlers", handlers_py)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {handlers_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.macos_bundle_plist_extras()


def read_version(root: Path) -> str:
    for line in (root / "src" / "peerfold" / "__init__.py").read_text().splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("Could not read package version")


def make_sfx(app_dir: Path, output: Path, name: str, version: str) -> Path:
    if not app_dir.is_dir():
        raise SystemExit(f"App directory missing: {app_dir}")
    binary = app_dir / name
    if not binary.is_file():
        raise SystemExit(f"Binary missing: {binary}")

    stub = STUB.replace("__NAME__", name).replace("__VERSION__", version)
    if not stub.endswith("\n"):
        stub += "\n"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(app_dir, arcname=name)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with output.open("wb") as fh:
        fh.write(stub.encode("utf-8"))
        fh.write(MARKER.encode("utf-8"))
        fh.write(buf.getvalue())
    output.chmod(0o755)
    return output


def make_app_bundle(app_dir: Path, output: Path, name: str, version: str) -> Path:
    if output.exists():
        shutil.rmtree(output)
    macos = output / "Contents" / "MacOS"
    resources = output / "Contents" / "Resources" / "runtime"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)
    shutil.copytree(app_dir, resources, dirs_exist_ok=True)

    _install_macos_launcher(macos, name)

    resources = output / "Contents" / "Resources"
    icns = Path(__file__).resolve().parents[1] / "assets" / "PeerFold.icns"
    icon_file = None
    if icns.is_file():
        shutil.copy2(icns, resources / "PeerFold.icns")
        icon_file = "PeerFold"

    plist = {
        "CFBundleExecutable": "peerfold",
        "CFBundleIdentifier": "io.peerfold.app",
        "CFBundleName": "PeerFold",
        "CFBundleDisplayName": "PeerFold",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        **_macos_bundle_plist_extras(),
    }
    if icon_file:
        plist["CFBundleIconFile"] = icon_file
    with (output / "Contents" / "Info.plist").open("wb") as fh:
        plistlib.dump(plist, fh)
    return output


def make_dmg(app_dir: Path, output: Path, name: str, version: str, *, volume: str = "PeerFold") -> Path:
    if shutil.which("hdiutil") is None:
        raise SystemExit("hdiutil not found (macOS only)")
    staging = output.parent / "_dmg_staging"
    if staging.exists():
        shutil.rmtree(staging)
    make_app_bundle(app_dir, staging / "PeerFold.app", name, version)
    apps_link = staging / "Applications"
    apps_link.symlink_to("/Applications")
    if output.exists():
        output.unlink()
    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            volume,
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(output),
        ],
        check=True,
    )
    shutil.rmtree(staging)
    return output


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("app_dir", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--sfx", type=Path)
    ap.add_argument("--dmg", type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = read_version(root)
    if args.sfx:
        make_sfx(args.app_dir, args.sfx, args.name, version)
        print(f"Self-extracting: {args.sfx}")
    if args.dmg:
        make_dmg(args.app_dir, args.dmg, args.name, version)
        print(f"Disk image: {args.dmg}")
