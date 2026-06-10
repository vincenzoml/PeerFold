#!/usr/bin/env python3
"""Repo-local PeerFold launcher: pinned venv + explicit updates.

Usage:
    python3 scripts/peerfold.py review-builds/paper.pdf --reviewer AB
    python3 scripts/peerfold.py paper.pdf --web          # over SSH
    python3 scripts/peerfold.py --update                 # upgrade PyPI pin (commit after)

Creates .venv-peerfold/ (gitignored). Normal runs install the pinned version below
so every co-author gets the same PeerFold. Run --update when you want a newer release.

Local dev: set PEERFOLD_LOCAL=/path/to/PeerFold checkout, or put that path in
scripts/.peerfold-local (gitignored) for editable installs with unpublished fixes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
VENV = ROOT / ".venv-peerfold"
PACKAGE = "peerfold-review"
PEERFOLD_VERSION = "0.1.26"
PYPI_JSON = f"https://pypi.org/pypi/{PACKAGE}/json"


def venv_paths() -> tuple[Path, Path]:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe", VENV / "Scripts" / "peerfold.exe"
    return VENV / "bin" / "python", VENV / "bin" / "peerfold"


def _valid_local_repo(path: Path) -> Path | None:
    path = path.expanduser().resolve()
    if (path / "pyproject.toml").is_file() and (path / "src" / "peerfold" / "__init__.py").is_file():
        return path
    return None


def local_peerfold_repo() -> Path | None:
    raw = os.environ.get("PEERFOLD_LOCAL", "").strip()
    if raw:
        return _valid_local_repo(Path(raw))
    sidecar = SCRIPT_DIR / ".peerfold-local"
    if sidecar.is_file():
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                found = _valid_local_repo(Path(line))
                if found:
                    return found
    auto = SCRIPT_DIR.parent
    if (auto / "src" / "peerfold" / "__init__.py").is_file() and (auto / "pyproject.toml").is_file():
        return auto
    return None


def ensure_venv_python() -> Path:
    py, _ = venv_paths()
    if not py.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    return py


def installed_version(py: Path) -> str | None:
    result = subprocess.run(
        [str(py), "-m", "pip", "show", PACKAGE],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def local_repo_version(repo: Path) -> str:
    text = (repo / "src" / "peerfold" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit(f"Could not read version from {repo}")
    return match.group(1)


def latest_pypi_version() -> str:
    try:
        with urlopen(PYPI_JSON, timeout=15) as resp:
            return json.load(resp)["info"]["version"]
    except URLError as exc:
        raise SystemExit(f"Could not reach PyPI for {PACKAGE}: {exc}") from exc


def install_package(py: Path) -> None:
    subprocess.run([str(py), "-m", "pip", "install", "-U", "pip"], check=True)
    dev = local_peerfold_repo()
    if dev is not None:
        subprocess.run([str(py), "-m", "pip", "install", "-e", str(dev)], check=True)
        return
    subprocess.run(
        [str(py), "-m", "pip", "install", f"{PACKAGE}=={PEERFOLD_VERSION}"],
        check=True,
    )


def upgrade_to_latest(py: Path) -> str:
    subprocess.run([str(py), "-m", "pip", "install", "-U", "pip"], check=True)
    dev = local_peerfold_repo()
    if dev is not None:
        subprocess.run([str(py), "-m", "pip", "install", "-e", str(dev)], check=True)
        return local_repo_version(dev)
    latest = latest_pypi_version()
    subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", f"{PACKAGE}=={latest}"],
        check=True,
    )
    installed = installed_version(py)
    if installed != latest:
        raise SystemExit(
            f"Installed {PACKAGE} {installed or '?'}, expected PyPI latest {latest}"
        )
    return latest


def write_pinned_version(script: Path, version: str) -> None:
    text = script.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^(PEERFOLD_VERSION\s*=\s*")[^"]+(")',
        rf'\g<1>{version}\2',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("Could not update PEERFOLD_VERSION in this script")
    script.write_text(new_text, encoding="utf-8")


def pop_flag(argv: list[str], flag: str) -> bool:
    if flag not in argv:
        return False
    argv.remove(flag)
    return True


def main() -> None:
    args = list(sys.argv[1:])
    do_update = pop_flag(args, "--update")

    py = ensure_venv_python()
    script = Path(__file__).resolve()
    dev = local_peerfold_repo()

    if do_update:
        latest = upgrade_to_latest(py)
        if dev is None and latest != PEERFOLD_VERSION:
            write_pinned_version(script, latest)
            print(
                f"Updated {PACKAGE} {PEERFOLD_VERSION} → {latest} — "
                "commit scripts/peerfold.py so co-authors stay in sync."
            )
        elif dev is not None:
            print(f"Local dev install: {dev} ({latest})")
        else:
            print(f"{PACKAGE} {latest} — already the latest on PyPI (pin unchanged).")
        if not args:
            raise SystemExit(0)

    install_package(py)
    _, peerfold = venv_paths()
    if not peerfold.is_file():
        raise SystemExit(f"peerfold not found after installing {PACKAGE}")

    if dev is not None and os.environ.get("PEERFOLD_QUIET") != "1":
        print(f"PeerFold {installed_version(py) or '?'} (editable ← {dev})", file=sys.stderr)

    result = subprocess.run([str(peerfold), *args])
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
