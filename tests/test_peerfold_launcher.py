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
    assert mod.version_key(latest) >= mod.version_key(mod.PEERFOLD_VERSION)


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


def test_installed_version_reads_metadata(monkeypatch, tmp_path):
    mod = load_launcher()
    py = tmp_path / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("# stub", encoding="utf-8")
    py.chmod(0o755)

    def fake_run(cmd, **kwargs):
        if len(cmd) >= 3 and cmd[0] == str(py) and cmd[1] == "-c":
            if "importlib.metadata" in cmd[2]:
                class Result:
                    returncode = 0
                    stdout = "0.1.44\n"
                    stderr = ""
                return Result()
            class Result:
                returncode = 1
                stdout = ""
                stderr = ""
            return Result()
        class Result:
            returncode = 1
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "user_data_dir", lambda: tmp_path / "data")
    assert mod.installed_version(py) == "0.1.44"


def test_installed_version_falls_back_to_cli(monkeypatch, tmp_path):
    mod = load_launcher()
    py = tmp_path / "bin" / "python"
    peerfold = py.parent / "peerfold"
    py.parent.mkdir(parents=True)
    py.write_text("# stub", encoding="utf-8")
    peerfold.write_text("# stub", encoding="utf-8")
    py.chmod(0o755)
    peerfold.chmod(0o755)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == [str(peerfold), "--version"]:
            class Result:
                returncode = 0
                stdout = "peerfold 0.1.45\n"
                stderr = ""
            return Result()
        class Result:
            returncode = 1
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mod, "user_data_dir", lambda: tmp_path / "data")
    assert mod.installed_version(py) == "0.1.45"


def test_venv_dir_versioned(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_VENV", raising=False)
    monkeypatch.delenv("PEERFOLD_LOCAL", raising=False)
    monkeypatch.setattr(mod, "local_peerfold_repo", lambda: None)
    assert mod.venv_dir() == mod.user_data_dir() / "venvs" / f"{mod.PEERFOLD_VERSION}-py{mod.PYTHON_VERSION}"


def test_venv_dir_accepts_pin(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_VENV", raising=False)
    monkeypatch.delenv("PEERFOLD_LOCAL", raising=False)
    monkeypatch.setattr(mod, "local_peerfold_repo", lambda: None)
    assert mod.venv_dir(pin="0.1.44") == mod.user_data_dir() / "venvs" / f"0.1.44-py{mod.PYTHON_VERSION}"


def test_uv_cache_dir_default(monkeypatch):
    mod = load_launcher()
    monkeypatch.delenv("PEERFOLD_CACHE", raising=False)
    monkeypatch.delenv("PEERFOLD_DATA", raising=False)
    assert mod.uv_cache_dir() == mod.user_data_dir() / "cache"


def test_venv_is_built_on_the_pinned_interpreter(tmp_path, monkeypatch):
    """uv must be told which interpreter to use, never left to find one.

    Its discovery order puts a free-threaded build first when the machine has
    one, and PyMuPDF cannot be built against a free-threaded interpreter, so a
    venv created without --python is the one failure mode that stops PeerFold
    from installing at all.
    """
    mod = load_launcher()
    py = tmp_path / "venv" / "bin" / "python"
    monkeypatch.setattr(mod, "ensure_uv", lambda: tmp_path / "uv")
    monkeypatch.setattr(mod, "venv_dir", lambda *, pin=None: tmp_path / "venv")
    monkeypatch.setattr(
        mod, "venv_paths", lambda *, pin=None: (py, py.parent / "peerfold")
    )
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        py.parent.mkdir(parents=True, exist_ok=True)
        py.write_text("", encoding="utf-8")

    monkeypatch.setattr(mod, "_run", fake_run)

    assert mod.ensure_venv_python() == py
    cmd = commands[0]
    assert "--python" in cmd, f"uv was left to choose an interpreter: {cmd}"
    assert cmd[cmd.index("--python") + 1] == mod.PYTHON_VERSION
    assert not mod.PYTHON_VERSION.endswith("t"), "that requests a free-threaded build"
