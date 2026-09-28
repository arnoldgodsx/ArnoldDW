import threading
from types import SimpleNamespace

import pytest

from arnold_dw.core.runtime import autocheck
from arnold_dw.core.runtime.autocheck import CHECK_INTERVAL, BackgroundCheck, should_check

NOW = 1_759_000_000.0


@pytest.mark.parametrize("auto,last,expected", [
    (False, 0.0, False),
    (False, NOW - 10 * CHECK_INTERVAL, False),
    (True, 0.0, True),
    (True, NOW - CHECK_INTERVAL, True),
    (True, NOW - CHECK_INTERVAL + 60, False),
    (True, NOW - 5, False),
    (True, NOW + 3600, True),  # clock went back: don't wait until the future
])
def test_should_check(auto, last, expected):
    assert should_check(auto, last, NOW) is expected


def _settings(**kw):
    base = dict(engine_auto_check=True, engine_channel="stable", last_engine_check=0.0)
    base.update(kw)
    return SimpleNamespace(**base)


def _run(checker, settings, saves):
    """Start with no delay and wait for the timer thread."""
    before = set(threading.enumerate())
    scheduled = checker.start(settings, lambda: saves.append(settings.last_engine_check), delay=0)
    for t in set(threading.enumerate()) - before:
        t.join(5)
    return scheduled


def test_found_update_is_remembered_and_time_saved():
    calls = []
    info = SimpleNamespace(version="2026.9.30", current="2026.8.19")

    def check(channel, raise_errors):
        calls.append((channel, raise_errors))
        return info

    checker = BackgroundCheck(check=check, clock=lambda: NOW)
    saves = []
    settings = _settings(engine_channel="nightly")
    assert _run(checker, settings, saves)
    assert calls == [("nightly", True)]
    assert checker.result is info and not checker.pending
    assert checker.notice() == autocheck.NOTICE_TEXT
    assert settings.last_engine_check == NOW and saves == [NOW]
    checker.clear()
    assert checker.notice() is None


def test_up_to_date_shows_no_notice_but_records_time():
    checker = BackgroundCheck(check=lambda channel, raise_errors: None, clock=lambda: NOW)
    saves = []
    assert _run(checker, _settings(), saves)
    assert checker.notice() is None and saves == [NOW]


def test_failed_check_is_not_recorded():
    def check(channel, raise_errors):
        raise OSError("offline")

    checker = BackgroundCheck(check=check, clock=lambda: NOW)
    saves = []
    settings = _settings()
    assert _run(checker, settings, saves)
    assert settings.last_engine_check == 0.0 and saves == []
    assert checker.notice() is None and not checker.pending


def test_not_due_or_disabled_does_nothing():
    def check(channel, raise_errors):
        raise AssertionError("must not run")

    recent = BackgroundCheck(check=check, clock=lambda: NOW)
    assert not recent.start(_settings(last_engine_check=NOW - 60), lambda: None, delay=0)
    off = BackgroundCheck(check=check, clock=lambda: NOW)
    assert not off.start(_settings(engine_auto_check=False), lambda: None, delay=0)
    assert not off.pending


def test_start_is_idempotent():
    calls = []
    checker = BackgroundCheck(check=lambda c, raise_errors: calls.append(c), clock=lambda: NOW)
    saves = []
    assert _run(checker, _settings(), saves)
    assert not _run(checker, _settings(), saves)
    assert calls == ["stable"]
