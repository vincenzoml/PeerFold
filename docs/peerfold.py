#!/usr/bin/env python3
"""Repo-local PeerFold launcher: pinned venv + explicit updates.

Usage:
    ./peerfold.py manuscript.pdf --reviewer AB
    ./peerfold.py paper.pdf --web          # over SSH
    ./peerfold.py --update                 # upgrade PyPI pin (commit after)

Drop this file in your project root (copy or curl). PeerFold uses one shared
package cache under your home (~/.local/share/peerfold/cache) and keeps a
small venv per pinned version there — no project-local installs, no repeat
downloads when you switch between papers on the same pin.

Local dev: set PEERFOLD_LOCAL=/path/to/PeerFold checkout, or put that path in
.peerfold-local (gitignored) for editable installs with unpublished fixes.
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

ROOT = Path(__file__).resolve().parent
PACKAGE = "peerfold-review"
PEERFOLD_VERSION = "0.1.27"
PYPI_JSON = f"https://pypi.org/pypi/{PACKAGE}/json"


def user_data_dir() -> Path:
    override = os.environ.get("PEERFOLD_DATA", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if base:
            return Path(base) / "PeerFold"
        return Path.home() / "AppData" / "Local" / "PeerFold"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "peerfold"
    return Path.home() / ".local" / "share" / "peerfold"


def uv_cache_dir() -> Path:
    override = os.environ.get("PEERFOLD_CACHE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "cache"


def venv_dir() -> Path:
    override = os.environ.get("PEERFOLD_VENV", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if local_peerfold_repo() is not None:
        return user_data_dir() / "venvs" / "dev"
    return user_data_dir() / "venvs" / PEERFOLD_VERSION


def _win32() -> bool:
    return sys.platform == "win32"


def tools_paths() -> tuple[Path, Path]:
    tools = user_data_dir() / "tools"
    if _win32():
        return tools / "Scripts" / "python.exe", tools / "Scripts" / "uv.exe"
    return tools / "bin" / "python", tools / "bin" / "uv"


def venv_paths() -> tuple[Path, Path]:
    venv = venv_dir()
    if _win32():
        return venv / "Scripts" / "python.exe", venv / "Scripts" / "peerfold.exe"
    return venv / "bin" / "python", venv / "bin" / "peerfold"


def uv_env() -> dict[str, str]:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(uv_cache_dir())
    return env


def ensure_uv() -> Path:
    py, uv = tools_paths()
    if uv.is_file():
        return uv
    tools = py.parent.parent
    tools.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(tools)], check=True)
    subprocess.run(
        [str(py), "-m", "pip", "install", "-U", "pip", "uv"],
        check=True,
    )
    if not uv.is_file():
        raise SystemExit("Could not bootstrap uv for PeerFold")
    return uv


def _valid_local_repo(path: Path) -> Path | None:
    path = path.expanduser().resolve()
    if (path / "pyproject.toml").is_file() and (path / "src" / "peerfold" / "__init__.py").is_file():
        return path
    return None


def local_peerfold_repo() -> Path | None:
    raw = os.environ.get("PEERFOLD_LOCAL", "").strip()
    if raw:
        return _valid_local_repo(Path(raw))
    sidecar = ROOT / ".peerfold-local"
    if sidecar.is_file():
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                found = _valid_local_repo(Path(line))
                if found:
                    return found
    if (ROOT / "src" / "peerfold" / "__init__.py").is_file() and (ROOT / "pyproject.toml").is_file():
        return ROOT
    return None


def ensure_venv_python() -> Path:
    py, _ = venv_paths()
    if py.is_file():
        return py
    venv = venv_dir()
    venv.parent.mkdir(parents=True, exist_ok=True)
    uv = ensure_uv()
    subprocess.run([str(uv), "venv", str(venv)], check=True, env=uv_env())
    py, _ = venv_paths()
    if not py.is_file():
        raise SystemExit(f"Could not create PeerFold venv at {venv}")
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


def uv_pip_install(py: Path, *args: str) -> None:
    uv = ensure_uv()
    subprocess.run(
        [str(uv), "pip", "install", *args, "--python", str(py)],
        check=True,
        env=uv_env(),
    )


def install_package(py: Path) -> None:
    dev = local_peerfold_repo()
    if dev is not None:
        uv_pip_install(py, "-e", str(dev))
        return
    if installed_version(py) == PEERFOLD_VERSION:
        return
    uv_pip_install(py, f"{PACKAGE}=={PEERFOLD_VERSION}")


def upgrade_to_latest(py: Path) -> str:
    dev = local_peerfold_repo()
    if dev is not None:
        uv_pip_install(py, "-e", str(dev))
        return local_repo_version(dev)
    latest = latest_pypi_version()
    uv_pip_install(py, "--upgrade", f"{PACKAGE}=={latest}")
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
                "commit peerfold.py so co-authors stay in sync."
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
