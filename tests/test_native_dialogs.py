import threading

from peerfold import native_dialogs


def test_save_text_file_on_main_thread_uses_macos_panel(monkeypatch):
    calls = {"panel": 0, "dialog": 0}

    def fake_panel(default_name, content):
        calls["panel"] += 1
        return {"ok": True, "path": "/tmp/out.md"}

    class Window:
        def create_file_dialog(self, *args, **kwargs):
            calls["dialog"] += 1
            return "/tmp/out.md"

    monkeypatch.setattr(native_dialogs, "_macos_save_panel", fake_panel)
    native_dialogs.save_text_file(Window(), "paper-comments.md", "# hi", "markdown")
    assert calls["panel"] == 1
    assert calls["dialog"] == 0


def test_save_text_file_on_worker_thread_uses_pywebview(monkeypatch, tmp_path):
    calls = {"panel": 0, "dialog": 0}
    target = tmp_path / "paper-comments.txt"
    target.write_text("placeholder", encoding="utf-8")

    def fake_panel(default_name, content):
        calls["panel"] += 1
        return {"ok": True, "path": str(target)}

    class Window:
        def create_file_dialog(self, *args, **kwargs):
            calls["dialog"] += 1
            return str(target)

    monkeypatch.setattr(native_dialogs, "_macos_save_panel", fake_panel)

    def worker() -> dict:
        return native_dialogs.save_text_file(Window(), "paper-comments.txt", "hello", "text")

    result = {}
    thread = threading.Thread(target=lambda: result.update({"value": worker()}))
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert result["value"]["ok"] is True
    assert calls["panel"] == 0
    assert calls["dialog"] == 1
    assert target.read_text(encoding="utf-8") == "hello"
