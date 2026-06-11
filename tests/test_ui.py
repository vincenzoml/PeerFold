import sys

from peerfold.ui import (
    ApplicationMenuApi,
    PeerFoldApi,
    _set_macos_dock_name,
    build_application_menu,
    headless_environment,
    run_on_main_thread,
    show_about_dialog,
    show_update_check_dialog,
    ssh_session,
    webview_unavailable_help,
)


class _MenuHost:
    def open_via_dialog(self):
        pass

    def open_empty_window(self):
        pass

    def open_document_path(self, path):
        pass

    def api_for_active_window(self):
        return None


def test_set_macos_dock_name_noop_off_darwin(monkeypatch):
    monkeypatch.setattr("peerfold.ui.sys.platform", "linux")
    _set_macos_dock_name()


def test_ssh_session(monkeypatch):
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    assert not ssh_session()
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.1 54321 198.51.100.2 22")
    assert ssh_session()


def test_headless_on_ssh(monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.1 54321 198.51.100.2 22")
    assert headless_environment()


def test_webview_help_mentions_web_flag():
    msg = webview_unavailable_help(url="http://127.0.0.1:8765/")
    assert "--web" in msg


def test_build_application_menu_has_file_and_help(monkeypatch, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr("peerfold.ui.list_recent_paths", lambda: [pdf.resolve()])

    menu = build_application_menu(ApplicationMenuApi(_MenuHost()))
    titles = [item.title for item in menu]
    assert "File" in titles
    assert "Help" in titles
    app_menu = next(item for item in menu if item.title == "__app__")
    app_titles = [item.title for item in app_menu.items if hasattr(item, "title")]
    assert "About PeerFold" in app_titles
    file_menu = next(item for item in menu if item.title == "File")
    sub_titles = [item.title for item in file_menu.items if hasattr(item, "title")]
    assert "Open Recent" in sub_titles
    assert "New Window" in sub_titles
    assert "Duplicate Window" in sub_titles
    assert "Export Comments as Markdown…" in sub_titles
    recent_menu = next(item for item in file_menu.items if getattr(item, "title", None) == "Open Recent")
    recent_titles = [item.title for item in recent_menu.items if hasattr(item, "title")]
    assert "Clear Menu" in recent_titles
    if sys.platform != "darwin":
        assert "Edit" in titles
        assert "View" in titles
        assert "Window" in titles


def test_webview_help_ssh_port_forward(monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.1 54321 198.51.100.2 22")
    msg = webview_unavailable_help(url="http://127.0.0.1:8765/")
    assert "ssh -L 8765" in msg


def test_run_on_main_thread_runs_inline_on_main():
    ran = []
    run_on_main_thread(lambda: ran.append(True))
    assert ran == [True]


def test_show_update_check_dialog_up_to_date(monkeypatch):
    shown = []
    monkeypatch.setattr(
        "peerfold.ui.show_native_message",
        lambda title, body: shown.append((title, body)),
    )
    show_update_check_dialog(
        {"current": "1.0.0", "latest": "1.0.0", "update_available": False, "check_ok": True}
    )
    assert shown
    assert "up to date" in shown[0][1]


def test_application_menu_check_for_updates_shows_native_dialog(monkeypatch):
    shown = []
    monkeypatch.setattr(
        "peerfold.ui.show_update_check_dialog",
        lambda info: shown.append(info),
    )
    monkeypatch.setattr(
        "peerfold.core.update_check_payload",
        lambda: {"current": "1.0.0", "check_ok": True, "update_available": False},
    )
    api = ApplicationMenuApi(_MenuHost())
    api.check_for_updates()
    assert shown


def test_remove_recent_file(monkeypatch, tmp_path):
    removed = []

    class _Host:
        def open_via_dialog(self):
            pass

        def open_empty_window(self):
            pass

        def open_document_path(self, path):
            pass

        def duplicate_active_window(self):
            pass

        def api_for_active_window(self):
            return None

    monkeypatch.setattr(
        "peerfold.ui.remove_recent_file",
        lambda path: removed.append(path) or [],
    )
    api = ApplicationMenuApi(_Host())
    api._remove_recent_on_main(str(tmp_path / "gone.pdf"))
    assert removed


def test_open_recent_spawns_new_window(monkeypatch, tmp_path):
    pdf = tmp_path / "recent.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    opened = []

    class _Host:
        def open_document(self, pdf_path):
            opened.append(pdf_path)

    api = ApplicationMenuApi(_Host())
    api._open_recent_on_main(str(pdf))
    assert opened == [pdf.resolve()]


def test_show_about_dialog_does_not_raise(monkeypatch):
    monkeypatch.setattr("peerfold.ui._osascript_about", lambda *args: None)
    monkeypatch.setattr(
        "peerfold.ui.show_native_message",
        lambda title, body: None,
    )
    show_about_dialog()


def test_show_about_dialog_includes_links(monkeypatch):
    from peerfold.links import REPOSITORY, WEBSITE

    captured = []
    monkeypatch.setattr(
        "peerfold.ui._osascript_about",
        lambda version, website, repository: captured.append((version, website, repository)),
    )
    monkeypatch.setattr(
        "peerfold.ui.show_native_message",
        lambda title, body: captured.append(("message", title, body)),
    )
    monkeypatch.setattr("peerfold.ui.sys.platform", "linux")

    show_about_dialog()
    assert captured
    if captured[0][0] == "message":
        body = captured[0][2]
        assert WEBSITE in body
        assert REPOSITORY in body
    else:
        _version, website, repository = captured[0]
        assert website == WEBSITE
        assert repository == REPOSITORY
