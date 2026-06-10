import plistlib
import subprocess
import sys
from pathlib import Path

from peerfold.handlers import (
    MACOS_PDF_DOCUMENT_TYPE,
    _linux_desktop_entry,
    macos_bundle_plist_extras,
)


def test_macos_bundle_plist_declares_pdf():
    extras = macos_bundle_plist_extras()
    assert "CFBundleDocumentTypes" in extras
    doc = extras["CFBundleDocumentTypes"][0]
    assert doc == MACOS_PDF_DOCUMENT_TYPE
    assert "pdf" in doc["CFBundleTypeExtensions"]
    assert "com.adobe.pdf" in doc["LSItemContentTypes"]
    assert doc["LSHandlerRank"] == "Alternate"


def test_linux_desktop_entry_uses_exec_and_mime():
    entry = _linux_desktop_entry(Path("/usr/local/bin/peerfold"))
    assert "Exec=/usr/local/bin/peerfold %f" in entry
    assert "MimeType=application/pdf;" in entry


def test_package_release_plist_includes_pdf_support(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from package_release import make_app_bundle

    app_dir = tmp_path / "peerfold-macos"
    app_dir.mkdir()
    (app_dir / "peerfold-macos").write_text("#!/bin/sh\n", encoding="utf-8")
    (app_dir / "peerfold-macos").chmod(0o755)
    bundle = make_app_bundle(app_dir, tmp_path / "PeerFold.app", "peerfold-macos", "9.9.9")
    with (bundle / "Contents" / "Info.plist").open("rb") as fh:
        plist = plistlib.load(fh)
    assert plist["CFBundleDocumentTypes"][0]["CFBundleTypeExtensions"] == ["pdf"]
    assert plist["LSSupportsOpeningDocumentsInPlace"] is True
    launcher = bundle / "Contents" / "MacOS" / "peerfold"
    if sys.platform == "darwin":
        assert b"Mach-O" in subprocess.check_output(["file", str(launcher)])
