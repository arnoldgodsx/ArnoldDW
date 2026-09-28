"""check_for_update(raise_errors=True) and detection of a broken engine at runtime."""

import os

import pytest
import requests
from test_runtime_updater import FakePyPI

from arnold_dw.core.runtime import ytdlp_updater as up


@pytest.fixture
def pypi():
    return FakePyPI()


@pytest.fixture
def manager(tmp_path, pypi):
    return up.EngineManager(tmp_path / "engine", session=pypi, bundled_version="2026.08.19")


def test_raise_errors_reports_offline_as_update_error(manager):
    class Offline:
        def get(self, *a, **k):
            raise requests.ConnectionError("offline")

    manager._session = Offline()
    with pytest.raises(up.UpdateError) as err:
        manager.check_for_update(raise_errors=True)
    assert "denetlenemedi" in err.value.user_message
    assert manager.last_check() is None  # a failed check is not a check


def test_raise_errors_still_returns_none_when_up_to_date(manager, pypi):
    pypi.add_release("2026.8.19")
    assert manager.check_for_update(raise_errors=True) is None
    assert manager.last_check() is not None


def test_raise_errors_returns_update(manager, pypi):
    pypi.add_release("2026.9.1")
    assert manager.check_for_update("stable", raise_errors=True).version == "2026.9.1"


# ---------------------------------------------------------------------------
# engine_failure_reason
# ---------------------------------------------------------------------------

ENGINE_FILE = os.path.join("C:\\", "AppData", "engine", "2026.9.1", "yt_dlp", "extractor", "youtube.py")
APP_FILE = os.path.join("C:\\", "src", "arnold_dw", "core", "youtube.py")


def _raise_from(filename, exc_expr):
    """An exception whose innermost frame lives in `filename`."""
    code = compile(f"raise {exc_expr}", filename, "exec")
    try:
        exec(code, {})
    except BaseException as exc:  # noqa: BLE001 - returned for inspection
        return exc
    raise AssertionError("did not raise")


@pytest.mark.parametrize("expr", [
    "ImportError('cannot import name jsinterp')",
    "ModuleNotFoundError('No module named yt_dlp.foo')",
    "AttributeError(\"module 'yt_dlp.utils' has no attribute 'x'\")",
])
def test_import_and_attribute_errors_inside_engine_count(expr):
    reason = up.engine_failure_reason(_raise_from(ENGINE_FILE, expr))
    assert reason and reason.split(":")[0] in {"ImportError", "ModuleNotFoundError", "AttributeError"}


def test_errors_outside_engine_do_not_count():
    assert up.engine_failure_reason(_raise_from(APP_FILE, "AttributeError('our bug')")) is None


def test_other_exception_types_do_not_count():
    assert up.engine_failure_reason(_raise_from(ENGINE_FILE, "ValueError('Video unavailable')")) is None
    assert up.engine_failure_reason(None) is None


def test_wrapped_by_yt_dlp_download_error():
    inner = _raise_from(ENGINE_FILE, "ImportError('boom')")

    class DownloadError(Exception):
        def __init__(self, msg, exc_info):
            super().__init__(msg)
            self.exc_info = exc_info

    outer = DownloadError("ERROR: boom", (type(inner), inner, inner.__traceback__))
    assert up.engine_failure_reason(outer) == "ImportError: boom"


def test_chained_cause_is_followed():
    inner = _raise_from(ENGINE_FILE, "AttributeError('gone')")
    try:
        raise RuntimeError("wrapper") from inner
    except RuntimeError as outer:
        assert up.engine_failure_reason(outer) == "AttributeError: gone"


def test_report_failure_marks_engine_only_for_engine_errors(monkeypatch):
    marked = []

    class Manager:
        def mark_active_broken(self, reason):
            marked.append(reason)
            return True

    monkeypatch.setattr(up, "default_manager", lambda: Manager())
    assert up.report_failure(_raise_from(APP_FILE, "AttributeError('x')")) is False
    assert up.report_failure(_raise_from(ENGINE_FILE, "ImportError('y')")) is True
    assert marked == ["ImportError: y"]


def test_report_failure_never_raises(monkeypatch):
    def broken():
        raise OSError("disk")

    monkeypatch.setattr(up, "default_manager", broken)
    assert up.report_failure(_raise_from(ENGINE_FILE, "ImportError('y')")) is False
