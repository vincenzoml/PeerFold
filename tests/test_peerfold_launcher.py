import importlib.util
import re
from pathlib import Path


def load_launcher():
    path = Path(__file__).resolve().parents[1] / "peerfold.py"
    spec = importlib.util.spec_from_file_location("peerfold_launcher", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_pinned_version_constant():
    mod = load_launcher()
    assert mod.PEERFOLD_VERSION
    assert mod.PEERFOLD_VERSION.count(".") >= 2


def test_pop_flag():
    mod = load_launcher()
    args = ["--update", "paper.pdf", "--web"]
    assert mod.pop_flag(args, "--update") is True
    assert args == ["paper.pdf", "--web"]
    assert mod.pop_flag(args, "--update") is False


def test_write_pinned_version(tmp_path):
    mod = load_launcher()
    script = tmp_path / "peerfold.py"
    script.write_text('PEERFOLD_VERSION = "0.1.14"\n', encoding="utf-8")
    mod.write_pinned_version(script, "0.1.15")
    assert 'PEERFOLD_VERSION = "0.1.15"' in script.read_text(encoding="utf-8")


def test_latest_pypi_version():
    mod = load_launcher()
    latest = mod.latest_pypi_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", latest)


def test_peerfold_launcher_matches_docs_copy():
    root = Path(__file__).resolve().parents[1]
    assert (root / "peerfold.py").read_text(encoding="utf-8") == (
        root / "docs" / "peerfold.py"
    ).read_text(encoding="utf-8")


def test_user_data_dir_default(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_DATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    path = mod.user_data_dir()
    assert path == Path.home() / ".local" / "share" / "peerfold"


def test_venv_dir_versioned(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_VENV", raising=False)
    monkeypatch.delenv("PEERFOLD_LOCAL", raising=False)
    monkeypatch.setattr(mod, "local_peerfold_repo", lambda: None)
    assert mod.venv_dir() == mod.user_data_dir() / "venvs" / mod.PEERFOLD_VERSION


def test_uv_cache_dir_default(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_CACHE", raising=False)
    monkeypatch.delenv("PEERFOLD_DATA", raising=False)
    assert mod.uv_cache_dir() == mod.user_data_dir() / "cache"

