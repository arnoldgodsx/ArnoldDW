import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from arnold_dw import i18n


@pytest.fixture(autouse=True)
def reset_language():
    i18n.set_language("tr")
    yield
    i18n.set_language("tr")


def test_translation_and_format_parameters():
    i18n.set_language("en")
    assert i18n.t("youtube.progress.remaining", time="2 min") == "Remaining: 2 min"


def test_missing_key_falls_back_to_turkish_then_key(caplog):
    assert i18n.t("common.download") == "İndir"
    caplog.set_level(logging.WARNING, logger="arnold_dw.i18n")
    assert i18n.t("unknown.translation.key") == "unknown.translation.key"
    assert i18n.t("unknown.translation.key") == "unknown.translation.key"
    assert sum("Missing translation key" in record.message for record in caplog.records) == 1


def test_missing_format_parameter_never_raises():
    i18n.set_language("en")
    assert i18n.t("youtube.progress.remaining") == "Remaining: {time}"


@pytest.mark.parametrize(("count", "expected"), [(1, "Downloaded 1 file"), (4, "Downloaded 4 files")])
def test_english_plural_forms(count, expected):
    i18n.set_language("en")
    assert i18n.t("download.count", count=count) == expected


def test_catalog_turkish_fallback_for_missing_english_key(monkeypatch):
    monkeypatch.setattr(i18n, "_catalog", lambda code: {"only.tr": "Türkçe"} if code == "tr" else {})
    i18n.set_language("en")
    assert i18n.t("only.tr") == "Türkçe"


@pytest.mark.parametrize(("language_id", "expected"), [(0x041F, "tr"), (0x0409, "en")])
def test_windows_ui_language_detection(monkeypatch, language_id, expected):
    api = SimpleNamespace(GetUserDefaultUILanguage=lambda: language_id)
    monkeypatch.setattr(i18n.ctypes, "windll", SimpleNamespace(kernel32=api), raising=False)
    monkeypatch.setattr(i18n, "_LANGUAGE", None)
    assert i18n.current_language() == expected


def test_set_language_normalizes_locale_and_rejects_unknown():
    i18n.set_language("EN-us")
    assert i18n.current_language() == "en"
    with pytest.raises(ValueError):
        i18n.set_language("fr")


def test_checker_catalog_consistency_and_phase_three_report():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "tools/i18n_check.py", "--catalog-only"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "keys and placeholders match" in result.stdout

    report = subprocess.run(
        [sys.executable, "tools/i18n_check.py"], cwd=root, capture_output=True, encoding="utf-8", check=False
    )
    assert report.returncode == 0, report.stdout + report.stderr
    assert "UI literals to migrate" in report.stdout
    assert "arnold_dw/core/errors.py" in report.stdout


def test_catalog_files_are_valid_json():
    root = Path(__file__).resolve().parents[1]
    for language in i18n.available_languages():
        with (root / "arnold_dw" / "i18n" / f"{language}.json").open(encoding="utf-8") as stream:
            assert isinstance(json.load(stream), dict)
