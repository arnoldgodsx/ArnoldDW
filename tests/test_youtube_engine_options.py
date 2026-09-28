"""How core.youtube merges discovered tools, the format selectors and the user's settings."""

import json
import os

import pytest

from arnold_dw.core import youtube
from arnold_dw.core.runtime import selectors
from arnold_dw.core.youtube import DownloadPrefs

RUNTIME = {
    "remote_components": ["ejs:github"],
    "ffmpeg_location": "C:\\bin\\ffmpeg.exe",
    "js_runtimes": {"deno": {"path": "C:\\bin\\deno.exe"}},
}
NO_FFMPEG = {"remote_components": ["ejs:github"]}


def keys(opts):
    return [pp["key"] for pp in opts.get("postprocessors", [])]


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return tmp_path / "appdata"


def test_preview_gets_js_runtime_and_quiet_flags():
    opts = youtube.build_preview_options(RUNTIME)
    assert opts["js_runtimes"] == RUNTIME["js_runtimes"]
    assert opts["remote_components"] == ["ejs:github"]
    assert opts["skip_download"] is True and opts["noplaylist"] is True


def test_preview_uses_discovered_runtime_by_default(monkeypatch):
    monkeypatch.setattr(youtube.binaries, "ytdlp_runtime_options", lambda: dict(RUNTIME))
    assert youtube.build_preview_options()["js_runtimes"] == RUNTIME["js_runtimes"]


def test_compat_mp4_uses_h264_selector_and_runtime(tmp_path):
    prefs = DownloadPrefs("compat", embed_metadata=False, embed_thumbnail=False)
    opts = youtube.build_download_options("MP4", "720p", str(tmp_path), prefs, RUNTIME)
    assert opts["format"] == selectors.video_selector(720, "compat")
    assert opts["merge_output_format"] == "mp4"
    assert opts["ffmpeg_location"] == RUNTIME["ffmpeg_location"]
    assert opts["js_runtimes"] == RUNTIME["js_runtimes"]
    assert keys(opts) == []


def test_quality_mode_and_unknown_quality_label(tmp_path):
    prefs = DownloadPrefs("quality", False, False)
    opts = youtube.build_download_options("MP4", "bogus", str(tmp_path), prefs, RUNTIME)
    assert opts["format"] == selectors.video_selector(1080, "quality")


def test_invalid_mode_falls_back_to_compat(tmp_path):
    opts = youtube.build_download_options("MP4", "480p", str(tmp_path), DownloadPrefs("??", False, False), RUNTIME)
    assert opts["format"] == selectors.video_selector(480, "compat")


def test_mp4_embeds_follow_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(selectors, "_resolve_cover", lambda ext, wanted, ffprobe: wanted)
    opts = youtube.build_download_options("MP4", "1080p", str(tmp_path), DownloadPrefs("compat", True, True), RUNTIME)
    assert opts["writethumbnail"] is True
    assert keys(opts) == ["FFmpegThumbnailsConvertor", "EmbedThumbnail", "FFmpegMetadata"]


def test_mp3_bitrate_and_tags(tmp_path):
    opts = youtube.build_download_options("MP3", "128 kbps", str(tmp_path), DownloadPrefs("compat", True, True), RUNTIME)
    assert keys(opts) == ["FFmpegThumbnailsConvertor", "FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
    extract = opts["postprocessors"][1]
    assert extract["preferredcodec"] == "mp3" and extract["preferredquality"] == "128"


def test_no_tagging_without_ffmpeg(tmp_path):
    opts = youtube.build_download_options("MP3", "192 kbps", str(tmp_path), DownloadPrefs("compat", True, True), NO_FFMPEG)
    assert keys(opts) == ["FFmpegExtractAudio"]
    assert "writethumbnail" not in opts and "ffmpeg_location" not in opts


def test_saved_settings_are_used_when_no_prefs_given(tmp_path, appdata):
    os.makedirs(appdata / "Arnold DW")
    with open(appdata / "Arnold DW" / "config.json", "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "video_mode": "quality", "embed_metadata": False, "embed_thumbnail": False}, f)
    assert youtube.current_prefs() == DownloadPrefs("quality", False, False)
    opts = youtube.build_download_options("MP4", "1440p", str(tmp_path), runtime=RUNTIME)
    assert opts["format"] == selectors.video_selector(1440, "quality")
    assert keys(opts) == []


def test_defaults_without_config_file():
    assert youtube.current_prefs() == DownloadPrefs("compat", True, True)


def test_download_reports_engine_failures(tmp_path, monkeypatch):
    reported = []
    monkeypatch.setattr(youtube.ytdlp_updater, "report_failure", reported.append)

    class BrokenYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            raise ImportError("engine is broken")

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", BrokenYDL)
    import threading

    with pytest.raises(ImportError):
        youtube.download("u", "MP4", "720p", str(tmp_path), threading.Event())
    assert len(reported) == 1 and isinstance(reported[0], ImportError)
