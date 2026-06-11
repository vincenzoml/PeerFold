#!/usr/bin/env python3
"""Compare GitHub release tags with PyPI published versions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PYPI_JSON = "https://pypi.org/pypi/peerfold-review/json"
GITHUB_RELEASES = "https://api.github.com/repos/vincenzoml/PeerFold/releases?per_page=100"
ROOT = Path(__file__).resolve().parents[1]


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def github_release_versions() -> list[str]:
    data = _fetch_json(GITHUB_RELEASES)
    versions: list[str] = []
    for release in data:
        tag = str(release.get("tag_name", "")).lstrip("v")
        if re.fullmatch(r"\d+\.\d+\.\d+", tag):
            versions.append(tag)
    return versions


def read_init_version_for_tag(tag: str) -> str | None:
    tag_name = tag if tag.startswith("v") else f"v{tag}"
    result = subprocess.run(
        ["git", "show", f"{tag_name}:src/peerfold/__init__.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', result.stdout)
    return match.group(1) if match else None


def publishable_github_versions() -> list[str]:
    versions: list[str] = []
    for version in github_release_versions():
        package_version = read_init_version_for_tag(version)
        if package_version is None or package_version != version:
            continue
        versions.append(version)
    return versions


def pypi_has_version(version: str) -> bool:
    url = f"https://pypi.org/pypi/peerfold-review/{version}/json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError:
        return False


def pypi_release_versions(extra_candidates: list[str] | None = None) -> set[str]:
    data = _fetch_json(PYPI_JSON)
    versions = {v for v in data.get("releases", {}) if re.fullmatch(r"\d+\.\d+\.\d+", v)}
    latest = str(data.get("info", {}).get("version", ""))
    if re.fullmatch(r"\d+\.\d+\.\d+", latest):
        versions.add(latest)
    for version in extra_candidates or []:
        if version in versions:
            continue
        if pypi_has_version(version):
            versions.add(version)
    return versions


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-pypi",
        metavar="VERSION",
        help="Exit 1 unless VERSION is already on PyPI",
    )
    parser.add_argument(
        "--retry-seconds",
        type=int,
        default=0,
        help="Retry until parity holds or timeout (for post-upload checks)",
    )
    args = parser.parse_args()

    deadline = time.time() + max(args.retry_seconds, 0)
    while True:
        gh = publishable_github_versions()
        pypi = pypi_release_versions(gh)
        missing = sorted(
            (v for v in gh if v not in pypi),
            key=version_key,
        )
        extra = sorted(
            (v for v in pypi if v not in set(gh)),
            key=version_key,
        )

        if args.require_pypi:
            if args.require_pypi in pypi:
                print(f"PyPI has peerfold-review {args.require_pypi}")
                return
            if time.time() >= deadline:
                print(
                    f"PyPI does not have peerfold-review {args.require_pypi}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            time.sleep(5)
            continue

        if not missing and not extra:
            print(f"GitHub and PyPI aligned ({len(gh)} releases)")
            return
        if time.time() >= deadline:
            if missing:
                print("GitHub releases missing on PyPI:", ", ".join(missing), file=sys.stderr)
            if extra:
                print("PyPI versions without GitHub release:", ", ".join(extra), file=sys.stderr)
            raise SystemExit(1)
        time.sleep(5)


if __name__ == "__main__":
    main()
