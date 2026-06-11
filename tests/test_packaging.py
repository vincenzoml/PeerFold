import plistlib
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_wheel_includes_static_files(tmp_path):
    out = tmp_path / "dist"
    out.mkdir()
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "-o", str(out)],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    wheel = next(out.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "peerfold/static/index.html" in names
    assert "peerfold/static/app.js" in names
    assert "peerfold/static/app.css" in names
    assert any(name.endswith("peerfold/static/icon-512.png") for name in names)


def test_make_app_bundle_includes_icon(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    from package_release import make_app_bundle, read_version

    app_dir = tmp_path / "peerfold-macos"
    app_dir.mkdir()
    (app_dir / "peerfold-macos").write_bytes(b"")
    bundle = tmp_path / "PeerFold.app"
    make_app_bundle(app_dir, bundle, "peerfold-macos", read_version(REPO))

    plist = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert plist.get("CFBundleName") == "PeerFold"
    assert plist.get("CFBundleDisplayName") == "PeerFold"
    assert plist.get("CFBundleIconFile") == "PeerFold"
    icns = bundle / "Contents" / "Resources" / "PeerFold.icns"
    assert icns.is_file()
    assert icns.stat().st_size > 1000
