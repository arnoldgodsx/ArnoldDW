import json

import pytest

from arnold_dw.config import Settings, load_settings, save_settings


@pytest.fixture
def cfg(tmp_path):
    return str(tmp_path / "config.json")


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_old_config_gets_engine_defaults(cfg):
    _write(cfg, {"schema": 1, "download_dir": "D:\\Videolar"})
    s = load_settings(cfg)
    assert s.download_dir == "D:\\Videolar"
    assert s.video_mode == "compat"
    assert s.embed_metadata is True
    assert s.embed_thumbnail is True
    assert s.engine_channel == "stable"
    assert s.engine_auto_check is True
    assert s.last_engine_check == 0.0


def test_legacy_schema0_file_still_loads(cfg):
    _write(cfg, {"download_dir": "D:\\X"})
    s = load_settings(cfg)
    assert s.download_dir == "D:\\X" and s.video_mode == "compat"


def test_engine_fields_round_trip(cfg):
    s = Settings(download_dir="C:\\d", video_mode="quality", embed_metadata=False,
                 embed_thumbnail=False, engine_channel="nightly", engine_auto_check=False,
                 last_engine_check=1759000000.5)
    assert save_settings(s, cfg)
    assert load_settings(cfg) == s


@pytest.mark.parametrize("key,value", [
    ("video_mode", "4k-please"),
    ("video_mode", ""),
    ("video_mode", 1),
    ("engine_channel", "beta"),
    ("engine_channel", None),
    ("embed_metadata", "yes"),
    ("embed_thumbnail", 1),
    ("engine_auto_check", 0),
    ("last_engine_check", "yesterday"),
    ("last_engine_check", True),
])
def test_invalid_values_fall_back_to_defaults(cfg, key, value):
    _write(cfg, {"schema": 1, key: value})
    assert getattr(load_settings(cfg), key) == getattr(Settings(), key)


def test_integer_timestamp_accepted(cfg):
    _write(cfg, {"schema": 1, "last_engine_check": 1759000000})
    assert load_settings(cfg).last_engine_check == 1759000000
