import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def read_init_version() -> str:
    text = (REPO / "src" / "peerfold" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match
    return match.group(1)


def test_check_versions_passes_after_wheel_build(tmp_path):
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "-o", str(tmp_path)],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    for old in dist.glob("peerfold_review-*.whl"):
        old.unlink()
    for wheel in tmp_path.glob("*.whl"):
        wheel.replace(dist / wheel.name)
    subprocess.run(
        [sys.executable, "scripts/check_versions.py"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )


def test_launcher_pin_matches_package():
    package = read_init_version()
    for rel in ("peerfold.py", "docs/peerfold.py"):
        text = (REPO / rel).read_text(encoding="utf-8")
        match = re.search(r'^PEERFOLD_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
        assert match, rel
        assert match.group(1) == package
