"""Register PeerFold as a PDF handler with the host OS."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MACOS_PDF_DOCUMENT_TYPE: dict[str, object] = {
    "CFBundleTypeName": "PDF Document",
    "CFBundleTypeRole": "Editor",
    "CFBundleTypeExtensions": ["pdf"],
    "CFBundleTypeMIMETypes": ["application/pdf"],
    "LSItemContentTypes": ["com.adobe.pdf"],
    "LSHandlerRank": "Alternate",
}


def macos_bundle_plist_extras() -> dict[str, object]:
    return {"CFBundleDocumentTypes": [MACOS_PDF_DOCUMENT_TYPE]}


def _linux_desktop_entry(exec_path: Path) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=PeerFold",
            "GenericName=PDF Review",
            "Comment=Review PDFs with standard highlight annotations",
            f"Exec={exec_path} %f",
            "Terminal=false",
            "MimeType=application/pdf;",
            "Categories=Office;Viewer;",
            "",
        ]
    )


def _macos_app_candidates() -> list[Path]:
    home = Path.home()
    names = ("PeerFold.app",)
    roots = (Path("/Applications"), home / "Applications")
    return [root / name for root in roots for name in names if (root / name).is_dir()]


def register_pdf_handler(*, exec_path: Path | None = None) -> str:
    """Register PeerFold for PDF open-with menus. Returns a short status message."""
    if sys.platform == "darwin":
        return _register_macos()
    if sys.platform == "win32":
        return _register_windows(exec_path or Path(sys.executable))
    if sys.platform.startswith("linux"):
        return _register_linux(exec_path or _linux_peerfold_binary())
    raise RuntimeError(f"PDF handler registration is not supported on {sys.platform}")


def _linux_peerfold_binary() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    import shutil

    found = shutil.which("peerfold")
    if found:
        return Path(found).resolve()
    return Path(sys.executable).resolve()


def _register_macos() -> str:
    apps = _macos_app_candidates()
    if not apps:
        raise RuntimeError(
            "PeerFold.app not found in /Applications or ~/Applications. "
            "Install the macOS app bundle first."
        )
    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
        "LaunchServices.framework/Support/lsregister"
    )
    if not lsregister.is_file():
        raise RuntimeError("lsregister not found — is this macOS?")
    for app in apps:
        subprocess.run([str(lsregister), "-f", "-R", "-trusted", str(app)], check=True)
    locations = ", ".join(str(app) for app in apps)
    return f"Registered {locations} for PDF open-with."


def _register_linux(exec_path: Path) -> str:
    exec_path = exec_path.resolve()
    if not exec_path.is_file():
        raise RuntimeError(f"PeerFold executable not found: {exec_path}")
    desktop_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = desktop_dir / "peerfold.desktop"
    desktop_path.write_text(_linux_desktop_entry(exec_path), encoding="utf-8")
    desktop_path.chmod(0o644)
    update_db = subprocess.run(
        ["update-desktop-database", str(desktop_dir)],
        capture_output=True,
        text=True,
    )
    if update_db.returncode != 0:
        return f"Wrote {desktop_path}. Log out and back in if PeerFold is missing from Open With."
    return f"Registered {desktop_path} for PDF open-with."


def _register_windows(exec_path: Path) -> str:
    import winreg

    exec_path = exec_path.resolve()
    if not exec_path.is_file():
        raise RuntimeError(f"PeerFold executable not found: {exec_path}")
    exe_name = exec_path.name
    command = f'"{exec_path}" "%1"'
    app_key = rf"Software\Classes\Applications\{exe_name}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, app_key) as app:
        winreg.SetValueEx(app, "FriendlyAppName", 0, winreg.REG_SZ, "PeerFold")
        with winreg.CreateKey(app, r"shell\open\command") as open_cmd:
            winreg.SetValueEx(open_cmd, None, 0, winreg.REG_SZ, command)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithList") as ow:
        winreg.SetValueEx(ow, exe_name, 0, winreg.REG_SZ, "")
    return f"Registered {exec_path} for PDF open-with."
