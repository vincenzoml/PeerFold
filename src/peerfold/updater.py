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

from peerfold.core import UPDATE_REPO, _github_ssl_context, version_newer

UPDATE_BASE = f"https://github.com/{UPDATE_REPO}/releases/latest/download"
PACKAGE = "peerfold-review"


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
        importlib.metadata.version(PACKAGE)
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


def _peerfold_data_dir() -> Path:
    override = os.environ.get("PEERFOLD_DATA", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if base:
            return Path(base) / "PeerFold"
        return Path.home() / "AppData" / "Local" / "PeerFold"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "peerfold"
    return Path.home() / ".local" / "share" / "peerfold"


def _uv_tool() -> Path | None:
    tools = _peerfold_data_dir() / "tools"
    uv = tools / ("Scripts/uv.exe" if sys.platform == "win32" else "bin/uv")
    return uv if uv.is_file() else None


def _launcher_script() -> Path | None:
    raw = os.environ.get("PEERFOLD_LAUNCHER", "").strip()
    if not raw:
        return None
    script = Path(raw).expanduser().resolve()
    return script if script.is_file() else None


def _latest_install_version() -> str:
    from peerfold.core import fetch_latest_release_version

    latest = fetch_latest_release_version()
    if not latest:
        raise RuntimeError("Could not determine the latest PeerFold version.")
    return latest


def _command_error(proc: subprocess.CompletedProcess[str]) -> str:
    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        return "Update install failed."
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR:") or "error" in line.lower():
            return line
    return lines[-1]


def _run_package_install(py: Path, version: str) -> str:
    spec = f"{PACKAGE}=={version}"
    uv = _uv_tool()
    if uv is not None:
        env = os.environ.copy()
        env["UV_CACHE_DIR"] = str(_peerfold_data_dir() / "cache")
        proc = subprocess.run(
            [str(uv), "pip", "install", "-q", "--upgrade", spec, "--python", str(py)],
            capture_output=True,
            text=True,
            env=env,
        )
    else:
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "--upgrade", spec],
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(_command_error(proc))
    installed = importlib.metadata.version(PACKAGE)
    if version_newer(version, installed):
        raise RuntimeError(f"Installed {PACKAGE} {installed}, expected {version}.")
    return installed


def _install_via_launcher(script: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(script), "--update"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        raise RuntimeError(_command_error(proc))
    latest = _latest_install_version()
    return {
        "ok": True,
        "message": (
            f"Updated to PeerFold {latest}. Quit and reopen PeerFold to use the new version."
        ),
        "relaunch": False,
        "version": latest,
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
    script = _launcher_script()
    if script is not None:
        return _install_via_launcher(script)

    latest = _latest_install_version()
    installed = _run_package_install(Path(sys.executable), latest)
    return {
        "ok": True,
        "message": (
            f"Installed {PACKAGE} {installed}. Quit and reopen PeerFold to use the new version."
        ),
        "relaunch": False,
        "version": installed,
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
