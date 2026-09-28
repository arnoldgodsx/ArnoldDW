from arnold_dw.core import winnotify


def test_notify_skips_when_app_is_foreground(monkeypatch):
    called = []
    monkeypatch.setattr(winnotify, "_is_app_foreground", lambda: True)
    monkeypatch.setattr(winnotify._notifier, "show", lambda *args: called.append(args))

    assert winnotify.notify("title", "body") is False
    assert called == []


def test_notify_shows_in_background_and_passes_callback(monkeypatch):
    def callback():
        pass

    seen = []
    monkeypatch.setattr(winnotify, "_is_app_foreground", lambda: False)
    monkeypatch.setattr(winnotify._notifier, "show",
                        lambda *args: seen.append(args) or True)

    assert winnotify.notify("title", "body", callback) is True
    assert seen == [("title", "body", callback)]


def test_notify_never_raises_on_native_api_error(monkeypatch):
    monkeypatch.setattr(winnotify, "_is_app_foreground", lambda: False)
    monkeypatch.setattr(winnotify._notifier, "show", lambda *args: (_ for _ in ()).throw(RuntimeError()))

    assert winnotify.notify("title", "body") is False
