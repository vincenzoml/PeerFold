import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from peerfold.updater import (
    _command_error,
    _install_pip_package,
    _launcher_script,
    download_url,
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
    if url is None:
        return
    assert url.endswith(f"/{platform_asset_name()}")


def test_install_mode_frozen():
    with patch.object(sys, "frozen", True, create=True):
        assert install_mode() == "bundle"


def test_install_support_shape():
    support = install_support()
    assert "mode" in support
    assert "download_url" in support
    assert "can_install" in support


def test_launcher_script_from_env(tmp_path, monkeypatch):
    script = tmp_path / "peerfold.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setenv("PEERFOLD_LAUNCHER", str(script))
    assert _launcher_script() == script.resolve()


def test_command_error_prefers_last_error_line():
    proc = type("Proc", (), {"stdout": "", "stderr": "line one\nERROR: pip broke\n", "returncode": 1})()
    assert _command_error(proc) == "ERROR: pip broke"


def test_install_pip_package_uses_launcher(monkeypatch, tmp_path):
    script = tmp_path / "peerfold.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setenv("PEERFOLD_LAUNCHER", str(script))
    called = []

    def fake_launcher(path):
        called.append(path)
        return {"ok": True, "message": "ok", "relaunch": False, "version": "9.9.9"}

    monkeypatch.setattr("peerfold.updater._install_via_launcher", fake_launcher)
    result = _install_pip_package()
    assert called == [script.resolve()]
    assert result["ok"]


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
