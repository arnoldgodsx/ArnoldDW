import json
import os

import pytest

from arnold_dw import config, paths
from arnold_dw.config import SCHEMA_VERSION, Settings, load_settings, save_settings


@pytest.fixture
def cfg(tmp_path):
    return str(tmp_path / "Arnold DW" / "config.json")


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_missing_file_gives_defaults(cfg):
    settings = load_settings(cfg)
    assert settings == Settings()
    assert settings.download_dir == paths.default_download_dir()


def test_reads_legacy_format_without_schema(cfg):
    _write(cfg, json.dumps({"download_dir": "D:\\Videolar"}))
    assert load_settings(cfg).download_dir == "D:\\Videolar"


def test_reads_current_format(cfg):
    _write(cfg, json.dumps({"schema": 1, "download_dir": "E:\\İndirilenler"}))
    assert load_settings(cfg).download_dir == "E:\\İndirilenler"


@pytest.mark.parametrize("content", [
    "",
    "{not json",
    "\x00\x01\x02",
    "[1, 2, 3]",
    "null",
    '"just a string"',
])
def test_corrupt_or_unexpected_file_gives_defaults(cfg, content):
    _write(cfg, content)
    assert load_settings(cfg) == Settings()


@pytest.mark.parametrize("value", [None, "", "   ", 42, ["C:\\"], {"a": 1}, True])
def test_invalid_download_dir_falls_back_to_default(cfg, value):
    _write(cfg, json.dumps({"schema": 1, "download_dir": value}))
    assert load_settings(cfg).download_dir == paths.default_download_dir()


def test_unknown_keys_and_future_schema_are_tolerated(cfg):
    _write(cfg, json.dumps({"schema": 99, "download_dir": "D:\\x", "brand_new_option": True}))
    assert load_settings(cfg).download_dir == "D:\\x"


def test_non_integer_schema_is_treated_as_legacy(cfg):
    _write(cfg, json.dumps({"schema": "1", "download_dir": "D:\\x"}))
    assert load_settings(cfg).download_dir == "D:\\x"


def test_save_writes_schema_and_round_trips(cfg):
    assert save_settings(Settings(download_dir="D:\\Medya"), cfg)
    with open(cfg, encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"schema": SCHEMA_VERSION, "download_dir": "D:\\Medya", "max_concurrent": 2}
    assert load_settings(cfg).download_dir == "D:\\Medya"


def test_save_creates_missing_directory(tmp_path):
    path = str(tmp_path / "a" / "b" / "config.json")
    assert save_settings(Settings(download_dir="X:\\"), path)
    assert os.path.isfile(path)


def test_save_is_atomic_and_leaves_no_temp_files(cfg):
    save_settings(Settings(download_dir="D:\\one"), cfg)
    save_settings(Settings(download_dir="D:\\two"), cfg)
    assert os.listdir(os.path.dirname(cfg)) == ["config.json"]
    assert load_settings(cfg).download_dir == "D:\\two"


def test_failed_save_keeps_previous_file_intact(cfg, monkeypatch):
    save_settings(Settings(download_dir="D:\\old"), cfg)

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(config.os, "replace", boom)
    assert save_settings(Settings(download_dir="D:\\new"), cfg) is False
    monkeypatch.undo()

    assert load_settings(cfg).download_dir == "D:\\old"
    assert os.listdir(os.path.dirname(cfg)) == ["config.json"]


def test_save_to_unwritable_location_returns_false(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a dir")
    assert save_settings(Settings(), str(blocker / "config.json")) is False


def test_default_path_follows_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.config_path() == os.path.join(str(tmp_path), "Arnold DW", "config.json")
    assert save_settings(Settings(download_dir="D:\\env"))
    assert load_settings().download_dir == "D:\\env"
