from peerfold.ui import headless_environment, ssh_session, webview_unavailable_help


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


def test_webview_help_ssh_port_forward(monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.1 54321 198.51.100.2 22")
    msg = webview_unavailable_help(url="http://127.0.0.1:8765/")
    assert "ssh -L 8765" in msg
