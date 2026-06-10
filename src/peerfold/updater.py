"""Download and install PeerFold updates from GitHub releases."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from peerfold.core import UPDATE_REPO, _github_ssl_context, app_version, version_newer

UPDATE_BASE = f"https://github.com/{UPDATE_REPO}/releases/latest/download"


def platform_asset_name() -> str | None:
    if sys.platform == "darwin":
        return "peerfold-macos.dmg"
    if sys.platform.startswith("linux"):
        return "peerfold-linux"
    if sys.platform == "win32":
        return "peerfold-win.exe"
    return None


def download_url() -> str | None:
    asset = platform_asset_name()
    if asset is None:
        return None
    return f"{UPDATE_BASE}/{asset}"


def macos_app_bundle() -> Path | None:
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    exe = Path(sys.executable).resolve()
    if exe.parent.name != "MacOS" or exe.parent.parent.name != "Contents":
        return None
    app = exe.parent.parent.parent
    return app if app.suffix == ".app" and app.is_dir() else None


def install_mode() -> str:
    if getattr(sys, "frozen", False):
        return "bundle"
    try:
        importlib.metadata.version("peerfold-review")
    except importlib.metadata.PackageNotFoundError:
        return "script"
    else:
        return "pip"


def install_support() -> dict[str, Any]:
    mode = install_mode()
    asset = platform_asset_name()
    url = download_url()
    can_install = mode in {"bundle", "pip"} and url is not None
    if mode == "bundle" and sys.platform == "win32":
        can_install = False
    if mode == "bundle" and sys.platform == "darwin" and macos_app_bundle() is None:
        can_install = False
    return {
        "mode": mode,
        "asset": asset,
        "download_url": url,
        "can_install": can_install,
    }


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urlopen(url, timeout=120, context=_github_ssl_context())
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(req, out)
    finally:
        req.close()


def _macos_install_destination() -> Path:
    bundle = macos_app_bundle()
    if bundle is not None:
        return bundle
    for candidate in (Path("/Applications/PeerFold.app"), Path.home() / "Applications/PeerFold.app"):
        if candidate.parent.is_dir():
            return candidate
    return Path.home() / "Applications/PeerFold.app"


def _install_macos_bundle(url: str) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="peerfold-update-"))
    dmg = tmp / "peerfold.dmg"
    mount = tmp / "mount"
    mount.mkdir()
    try:
        _download(url, dmg)
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-quiet", "-mountpoint", str(mount), str(dmg)],
            check=True,
        )
        source = mount / "PeerFold.app"
        if not source.is_dir():
            raise RuntimeError("PeerFold.app not found in the update disk image.")
        dest = _macos_install_destination()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(["ditto", str(source), str(dest)], check=True)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dest)], check=False)
        lsregister = Path(
            "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
            "LaunchServices.framework/Support/lsregister"
        )
        if lsregister.is_file():
            subprocess.run([str(lsregister), "-f", "-trusted", str(dest)], check=False)
        subprocess.Popen(["open", "-n", str(dest)])
        return {
            "ok": True,
            "message": f"PeerFold updated in {dest}. Restarting…",
            "relaunch": True,
            "version": None,
        }
    finally:
        subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def _install_linux_bundle(url: str) -> dict[str, Any]:
    dest = Path(sys.executable).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="peerfold-update-"))
    downloaded = tmp / "peerfold-linux"
    try:
        _download(url, downloaded)
        downloaded.chmod(0o755)
        backup = dest.with_suffix(dest.suffix + ".bak")
        if dest.exists():
            shutil.copy2(dest, backup)
        shutil.copy2(downloaded, dest)
        dest.chmod(0o755)
        return {
            "ok": True,
            "message": f"PeerFold updated at {dest}. Quit and reopen PeerFold to use the new version.",
            "relaunch": False,
            "version": None,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _install_pip_package() -> dict[str, Any]:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "peerfold-review"],
        check=True,
    )
    latest = importlib.metadata.version("peerfold-review")
    return {
        "ok": True,
        "message": f"Installed peerfold-review {latest}. Quit and reopen PeerFold to use the new version.",
        "relaunch": False,
        "version": latest,
    }


def install_latest_update() -> dict[str, Any]:
    support = install_support()
    mode = support["mode"]
    url = support.get("download_url")
    if mode == "bundle":
        if sys.platform == "darwin":
            if not url:
                raise RuntimeError("No macOS update download is available.")
            return _install_macos_bundle(url)
        if sys.platform.startswith("linux"):
            if not url:
                raise RuntimeError("No Linux update download is available.")
            return _install_linux_bundle(url)
        raise RuntimeError("In-app updates are not supported on this platform.")
    if mode == "pip":
        return _install_pip_package()
    raise RuntimeError("Updates must be installed from the GitHub release page for this build.")


def relaunch_after_update() -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit

        AppKit.NSApplication.sharedApplication().terminate_(None)
    except Exception:
        os._exit(0)
