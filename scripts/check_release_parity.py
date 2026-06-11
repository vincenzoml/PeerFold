#!/usr/bin/env python3
"""Compare GitHub release tags with PyPI published versions."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

PYPI_JSON = "https://pypi.org/pypi/peerfold-review/json"
GITHUB_RELEASES = "https://api.github.com/repos/vincenzoml/PeerFold/releases?per_page=100"


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


def pypi_release_versions() -> set[str]:
    data = _fetch_json(PYPI_JSON)
    return {v for v in data.get("releases", {}) if re.fullmatch(r"\d+\.\d+\.\d+", v)}


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-pypi",
        metavar="VERSION",
        help="Exit 1 unless VERSION is already on PyPI",
    )
    args = parser.parse_args()

    gh = github_release_versions()
    pypi = pypi_release_versions()
    missing = sorted(
        (v for v in gh if v not in pypi),
        key=version_key,
    )
    extra = sorted(
        (v for v in pypi if v not in set(gh)),
        key=version_key,
    )

    if args.require_pypi:
        if args.require_pypi not in pypi:
            print(f"PyPI does not have peerfold-review {args.require_pypi}", file=sys.stderr)
            raise SystemExit(1)
        print(f"PyPI has peerfold-review {args.require_pypi}")
        return

    if missing:
        print("GitHub releases missing on PyPI:", ", ".join(missing), file=sys.stderr)
    if extra:
        print("PyPI versions without GitHub release:", ", ".join(extra), file=sys.stderr)
    if missing or extra:
        raise SystemExit(1)
    print(f"GitHub and PyPI aligned ({len(gh)} releases)")


if __name__ == "__main__":
    main()
