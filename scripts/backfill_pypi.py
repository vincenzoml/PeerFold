#!/usr/bin/env python3
"""Publish GitHub release tags that are missing from PyPI."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_init_version_at(root: Path) -> str:
    text = (root / "src" / "peerfold" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit(f"Could not read __version__ under {root}")
    return match.group(1)


def ensure_pyproject_version(root: Path, version: str) -> None:
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    if 'dynamic = ["version"]' in text:
        return
    new_text, count = re.subn(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f"Could not set pyproject.toml version in {root}")
    path.write_text(new_text, encoding="utf-8")


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)


def publish_tag(tag: str) -> None:
    version = tag.lstrip("v")
    work = ROOT / ".release-upload" / tag
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    run(["git", "worktree", "add", "--detach", str(work), tag])
    try:
        pkg_version = read_init_version_at(work)
        if pkg_version != version:
            raise SystemExit(f"{tag}: tag {version} != package {pkg_version}")
        ensure_pyproject_version(work, pkg_version)
        dist = work / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "build", "twine"], cwd=work)
        run([sys.executable, "-m", "build"], cwd=work)
        run([sys.executable, "-m", "twine", "upload", "dist/*"], cwd=work)
    finally:
        run(["git", "worktree", "remove", "--force", str(work)])


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from check_release_parity import publishable_github_versions, pypi_release_versions, version_key

    missing = sorted(
        (v for v in publishable_github_versions() if v not in pypi_release_versions()),
        key=version_key,
    )
    if not missing:
        print("GitHub and PyPI already aligned")
        return
    for version in missing:
        publish_tag(f"v{version}")
    print("Backfill complete:", ", ".join(missing))


if __name__ == "__main__":
    main()
