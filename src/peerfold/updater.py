"""Schedule safe, cross-platform PeerFold updates after the app exits."""

from __future__ import annotations

import importlib.metadata
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from peerfold.core import UPDATE_REPO

UPDATE_BASE = f"https://github.com/{UPDATE_REPO}/releases/latest/download"
INSTALL_BASE = "https://vincenzoml.github.io/PeerFold"
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
    return f"{UPDATE_BASE}/{asset}" if asset else None


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
    return "pip"


def install_support() -> dict[str, Any]:
    mode = install_mode()
    asset = platform_asset_name()
    url = download_url()
    return {
        "mode": mode,
        "asset": asset,
        "download_url": url,
        "can_install": mode in {"bundle", "pip"} and url is not None,
    }


def _launcher_script() -> Path | None:
    raw = os.environ.get("PEERFOLD_LAUNCHER", "").strip()
    if not raw:
        return None
    script = Path(raw).expanduser().resolve()
    return script if script.is_file() else None


def _restart_args() -> list[str]:
    return [arg for arg in sys.argv[1:] if arg != "--update"]


def _posix_update_command(mode: str) -> list[str]:
    parent_wait = f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done"
    args = shlex.join(_restart_args())

    if mode == "bundle":
        install = f"curl -fsSL {shlex.quote(f'{INSTALL_BASE}/install.sh')} | bash"
        if sys.platform == "darwin":
            app_args = f" --args {args}" if args else ""
            restart = (
                'if [ -d /Applications/PeerFold.app ]; then '
                f'exec open -n /Applications/PeerFold.app{app_args}; '
                f'else exec open -n "$HOME/Applications/PeerFold.app"{app_args}; fi'
            )
        else:
            restart = (
                'exec "${PEERFOLD_BIN_DIR:-$HOME/.local/bin}/peerfold"'
                + (f" {args}" if args else "")
            )
    elif mode == "pip":
        launcher = _launcher_script()
        if launcher is not None:
            command = shlex.join([sys.executable, str(launcher)])
            install = f"{command} --update"
            restart = f"exec {command}" + (f" {args}" if args else "")
        else:
            py = shlex.quote(sys.executable)
            install = f"{py} -m pip install --upgrade {PACKAGE}"
            restart = (
                f"exec {py} -c {shlex.quote('from peerfold.cli import main; main()')}"
                + (f" {args}" if args else "")
            )
    else:
        raise RuntimeError("This installation cannot update itself.")

    return ["/bin/sh", "-c", f"{parent_wait}; {install}; {restart}"]


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_update_command(mode: str) -> list[str]:
    parent_wait = (
        f"$parent = Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
        f"if ($parent) {{ Wait-Process -Id {os.getpid()} }}"
    )
    args = ", ".join(_ps_quote(arg) for arg in _restart_args())

    if mode == "bundle":
        install = f"irm {_ps_quote(f'{INSTALL_BASE}/install.ps1')} | iex"
        restart = (
            "$exe = Join-Path $env:LOCALAPPDATA 'Programs\\PeerFold\\peerfold.exe'; "
            f"Start-Process -FilePath $exe -ArgumentList @({args})"
        )
    elif mode == "pip":
        py = _ps_quote(sys.executable)
        launcher = _launcher_script()
        if launcher is not None:
            script = _ps_quote(str(launcher))
            install = f"& {py} {script} --update"
            restart = f"Start-Process -FilePath {py} -ArgumentList @({script}, {args})"
        else:
            install = f"& {py} -m pip install --upgrade {PACKAGE}"
            restart_args = ["-c", "from peerfold.cli import main; main()", *_restart_args()]
            restart = (
                f"Start-Process -FilePath {py} -ArgumentList @"
                f"({', '.join(_ps_quote(arg) for arg in restart_args)})"
            )
    else:
        raise RuntimeError("This installation cannot update itself.")

    script = "$ErrorActionPreference = 'Stop'; " + parent_wait + "; " + install + "; " + restart
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def _update_worker_command(mode: str) -> list[str]:
    if sys.platform == "win32":
        return _windows_update_command(mode)
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        return _posix_update_command(mode)
    raise RuntimeError("In-app updates are not supported on this platform.")


def _spawn_update_worker(command: list[str]) -> None:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def install_latest_update() -> dict[str, Any]:
    support = install_support()
    mode = support["mode"]
    if not support["can_install"]:
        raise RuntimeError("Updates must be installed from the GitHub release page for this build.")
    _spawn_update_worker(_update_worker_command(mode))
    return {
        "ok": True,
        "message": "PeerFold will close, install the update, and reopen.",
        "relaunch": True,
        "version": None,
    }


def relaunch_after_update() -> None:
    """Exit the GUI; the detached updater relaunches the replacement."""
    if sys.platform == "darwin":
        try:
            import AppKit

            AppKit.NSApplication.sharedApplication().terminate_(None)
            return
        except Exception:
            pass
    try:
        import webview

        for window in tuple(webview.windows):
            window.destroy()
    except Exception:
        os._exit(0)
