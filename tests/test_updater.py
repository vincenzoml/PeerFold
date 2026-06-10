import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from peerfold.updater import (
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
    assert download_url().endswith("/peerfold-macos.dmg") or download_url() is None


def test_install_mode_frozen():
    with patch.object(sys, "frozen", True, create=True):
        assert install_mode() == "bundle"


def test_install_support_shape():
    support = install_support()
    assert "mode" in support
    assert "download_url" in support
    assert "can_install" in support


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
