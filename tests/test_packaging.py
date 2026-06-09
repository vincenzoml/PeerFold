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
