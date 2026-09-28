import os

import pytest

from arnold_dw.core.runtime import restart


def test_frozen_command_reuses_exe_and_args():
    cmd = restart.relaunch_command("C:\\App\\ArnoldDW.exe", ["C:\\App\\ArnoldDW.exe", "--x"], frozen=True)
    assert cmd == ["C:\\App\\ArnoldDW.exe", "--x"]


def test_source_command_runs_the_script_again():
    cmd = restart.relaunch_command("C:\\py\\python.exe", ["app.py"], frozen=False)
    assert cmd == ["C:\\py\\python.exe", os.path.abspath("app.py")]


def test_env_drops_pyinstaller_bootstrap_state():
    env = restart.relaunch_env({"PATH": "p", "_MEIPASS2": "x", "_PYI_APPLICATION_HOME_DIR": "y"})
    assert env == {"PATH": "p", "PYINSTALLER_RESET_ENVIRONMENT": "1"}


@pytest.fixture
def clean_flag():
    restart.cancel()
    yield
    restart.cancel()


def test_relaunch_only_when_requested(monkeypatch, clean_flag):
    launched = []
    monkeypatch.setattr(restart, "relaunch", lambda: launched.append(1) or True)
    assert restart.relaunch_if_requested() is False
    restart.request()
    assert restart.requested()
    assert restart.relaunch_if_requested() is True
    assert launched == [1]


def test_relaunch_failure_never_raises(monkeypatch, clean_flag):
    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(restart.subprocess, "Popen", boom)
    restart.request()
    assert restart.relaunch_if_requested() is False
