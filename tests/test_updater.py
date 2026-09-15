import sys
from pathlib import Path
from unittest.mock import patch

from peerfold.updater import (
    _launcher_script,
    _posix_update_command,
    _windows_update_command,
    download_url,
    install_latest_update,
    install_mode,
    install_support,
    macos_app_bundle,
    platform_asset_name,
)


def test_platform_asset_name_by_os(monkeypatch):
    monkeypatch.setattr("peerfold.updater.sys.platform", "darwin")
    assert platform_asset_name() == "peerfold-macos.dmg"
    monkeypatch.setattr("peerfold.updater.sys.platform", "linux")
    assert platform_asset_name() == "peerfold-linux"
    monkeypatch.setattr("peerfold.updater.sys.platform", "win32")
    assert platform_asset_name() == "peerfold-win.exe"


def test_download_url_uses_latest_release():
    url = download_url()
    if url is not None:
        assert url.endswith(f"/{platform_asset_name()}")


def test_install_mode_frozen():
    with patch.object(sys, "frozen", True, create=True):
        assert install_mode() == "bundle"


def test_install_support_shape():
    support = install_support()
    assert {"mode", "download_url", "can_install"} <= support.keys()


def test_launcher_script_from_env(tmp_path, monkeypatch):
    script = tmp_path / "peerfold.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setenv("PEERFOLD_LAUNCHER", str(script))
    assert _launcher_script() == script.resolve()


def test_macos_app_bundle_from_frozen_executable(tmp_path, monkeypatch):
    app = tmp_path / "PeerFold.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    exe = macos / "peerfold"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("peerfold.updater.sys.executable", str(exe))
    monkeypatch.setattr("peerfold.updater.sys.platform", "darwin")
    with patch.object(sys, "frozen", True, create=True):
        assert macos_app_bundle() == app.resolve()


def test_macos_bundle_update_waits_for_exit_then_installs_and_reopens(monkeypatch):
    monkeypatch.setattr("peerfold.updater.sys.platform", "darwin")
    monkeypatch.setattr("peerfold.updater.os.getpid", lambda: 1234)
    command = _posix_update_command("bundle")
    assert command[:2] == ["/bin/sh", "-c"]
    script = command[-1]
    assert "kill -0 1234" in script
    assert "install.sh" in script
    assert "exec open -n" in script


def test_linux_bundle_update_restarts_with_original_arguments(monkeypatch):
    monkeypatch.setattr("peerfold.updater.sys.platform", "linux")
    monkeypatch.setattr("peerfold.updater.os.getpid", lambda: 1234)
    monkeypatch.setattr("peerfold.updater.sys.argv", ["peerfold", "paper name.pdf", "--reviewer", "AB"])
    script = _posix_update_command("bundle")[-1]
    assert "install.sh" in script
    assert '${PEERFOLD_BIN_DIR:-$HOME/.local/bin}/peerfold' in script
    assert "'paper name.pdf'" in script
    assert "--reviewer AB" in script


def test_pip_update_uses_repo_launcher_then_restarts(monkeypatch, tmp_path):
    script = tmp_path / "peerfold.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setenv("PEERFOLD_LAUNCHER", str(script))
    monkeypatch.setattr("peerfold.updater.sys.platform", "linux")
    command = _posix_update_command("pip")[-1]
    assert f"{script} --update" in command
    assert "exec" in command


def test_windows_bundle_update_waits_then_uses_windows_installer(monkeypatch):
    monkeypatch.setattr("peerfold.updater.os.getpid", lambda: 1234)
    monkeypatch.setattr("peerfold.updater.sys.argv", ["peerfold", "paper.pdf"])
    command = _windows_update_command("bundle")
    assert command[0] == "powershell.exe"
    script = command[-1]
    assert "Wait-Process -Id 1234" in script
    assert "install.ps1" in script
    assert "Start-Process" in script


def test_install_latest_update_queues_worker_and_requests_exit(monkeypatch):
    queued = []
    monkeypatch.setattr(
        "peerfold.updater.install_support",
        lambda: {"mode": "bundle", "can_install": True},
    )
    monkeypatch.setattr("peerfold.updater._update_worker_command", lambda mode: ["worker", mode])
    monkeypatch.setattr("peerfold.updater._spawn_update_worker", queued.append)
    result = install_latest_update()
    assert queued == [["worker", "bundle"]]
    assert result["ok"] and result["relaunch"]
