import pytest

from arnold_dw.config import ENGINE_CHANNELS, VIDEO_MODES
from arnold_dw.ui.screens import settings as s


def test_every_mode_and_channel_has_a_label():
    assert set(s.VIDEO_MODE_LABELS) == set(VIDEO_MODES) == set(s.VIDEO_MODE_HINTS)
    assert set(s.CHANNEL_LABELS) == set(ENGINE_CHANNELS)


@pytest.mark.parametrize("key", VIDEO_MODES)
def test_label_round_trip(key):
    assert s.label_to_key(s.VIDEO_MODE_LABELS, s.VIDEO_MODE_LABELS[key], "x") == key


def test_unknown_label_gives_default():
    assert s.label_to_key(s.CHANNEL_LABELS, "???", "stable") == "stable"


def test_cover_status():
    assert s.cover_status(True, True) == (True, None)
    enabled, note = s.cover_status(True, False)
    assert enabled and "ffprobe" in note and "MP3" in note
    enabled, note = s.cover_status(False, False)
    assert not enabled and "ffmpeg" in note


def test_engine_summary():
    assert s.engine_summary("2026.8.19", "bundled") == "yt-dlp 2026.8.19 · uygulamayla gelen sürüm"
    assert s.engine_summary("2026.9.30", "engine") == "yt-dlp 2026.9.30 · güncellenmiş sürüm"
    assert "bilinmiyor" in s.engine_summary(None, "bundled")


def test_tool_line():
    assert s.tool_line("ffmpeg", "7.1", True) == ("ffmpeg: 7.1", True)
    assert s.tool_line("ffprobe", None, True) == ("ffprobe: bulundu", True)
    assert s.tool_line("ffprobe", None, False, "MP4'e kapak eklenemez") == (
        "ffprobe: bulunamadı — MP4'e kapak eklenemez", False)


def test_install_progress_text():
    assert s.install_progress_text(0, 0).startswith("İndiriliyor")
    text = s.install_progress_text(1024 * 1024, 3 * 1024 * 1024)
    assert "/" in text
