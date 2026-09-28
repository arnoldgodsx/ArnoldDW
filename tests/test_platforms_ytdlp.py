"""Offline tests for the shared yt-dlp helpers, incl. running our format specs through yt-dlp's real selector."""

import os

import pytest
import yt_dlp
from yt_dlp.utils import FormatSorter

from arnold_dw.core.platforms import _ytdlp
from arnold_dw.core.platforms.models import DownloadOptions, MediaKind, Platform


class _Silent:
    def debug(self, msg):
        pass

    info = warning = error = debug


def pick(formats, ydl_opts):
    """Format id(s) yt-dlp would choose for ``formats`` with our ``format``/``format_sort`` options."""
    ydl = yt_dlp.YoutubeDL({"quiet": True, "logger": _Silent(), "format_sort": ydl_opts.get("format_sort") or []})
    fmts = []
    for f in formats:
        f = {"ext": "mp4", "protocol": "https", "url": f"https://cdn.example/{f['format_id']}", **f}
        FormatSorter._fill_sorting_fields(f)
        fmts.append(f)
    ydl.sort_formats({"formats": fmts})
    chosen = ydl._select_formats(fmts, ydl.build_format_selector(ydl_opts["format"]))
    assert chosen, "nothing selected"
    first = chosen[0]
    return "+".join(f["format_id"] for f in first.get("requested_formats") or [first])


YOUTUBE_LIKE = [
    {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "ext": "m4a"},
    {"format_id": "251", "vcodec": "none", "acodec": "opus", "abr": 135, "ext": "webm"},
    {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "width": 1920, "height": 1080, "tbr": 4000},
    {"format_id": "248", "vcodec": "vp9", "acodec": "none", "width": 1920, "height": 1080, "tbr": 2600, "ext": "webm"},
    {"format_id": "313", "vcodec": "vp9", "acodec": "none", "width": 3840, "height": 2160, "tbr": 16000,
     "ext": "webm"},
    {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "width": 1280, "height": 720, "tbr": 2200},
    {"format_id": "247", "vcodec": "vp9", "acodec": "none", "width": 1280, "height": 720, "tbr": 1500, "ext": "webm"},
    {"format_id": "135", "vcodec": "avc1.4d401f", "acodec": "none", "width": 854, "height": 480, "tbr": 1100},
    {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "width": 640, "height": 360, "tbr": 600},
]


def _opts(**kw):
    return _ytdlp.download_options(DownloadOptions(output_dir="out", **kw))


def test_video_prefers_h264_aac_at_top_rung():
    assert pick(YOUTUBE_LIKE, _opts(max_height=1080)) == "137+140"


def test_video_cap_picks_rung_at_or_below():
    assert pick(YOUTUBE_LIKE, _opts(max_height=720)) == "136+140"
    assert pick(YOUTUBE_LIKE, _opts(max_height=480)) == "135+140"


def test_video_uncapped_takes_the_sharpest():
    assert pick(YOUTUBE_LIKE, _opts()) == "313+140"


def test_video_cap_below_everything_falls_back_instead_of_failing():
    assert pick(YOUTUBE_LIKE, _opts(max_height=144)) in ("18", "135+140")


def test_portrait_video_is_capped_by_short_side():
    portrait = [
        {"format_id": "p1080", "vcodec": "h264", "acodec": "aac", "width": 1080, "height": 1920, "tbr": 3000},
        {"format_id": "p720", "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "tbr": 1700},
        {"format_id": "p540", "vcodec": "h264", "acodec": "aac", "width": 576, "height": 1024, "tbr": 900},
    ]
    assert pick(portrait, _opts(max_height=720)) == "p720"
    assert pick(portrait, _opts()) == "p1080"


def test_progressive_only_site_works():
    single = [{"format_id": "hd", "vcodec": "h264", "acodec": "aac", "height": 720, "width": 1280}]
    assert pick(single, _opts(max_height=1080)) == "hd"


def test_audio_mode_prefers_aac_and_extracts():
    opts = _opts(mode=MediaKind.AUDIO, audio_format="mp3", audio_quality="320")
    assert pick(YOUTUBE_LIKE, opts) == "140"
    pp = opts["postprocessors"][0]
    assert pp["key"] == "FFmpegExtractAudio" and pp["preferredcodec"] == "mp3" and pp["preferredquality"] == "320"
    assert "merge_output_format" not in opts


def test_audio_mode_m4a():
    opts = _opts(mode=MediaKind.AUDIO, audio_format="m4a")
    assert opts["postprocessors"][0]["preferredcodec"] == "m4a"


def test_download_options_basics(tmp_path):
    opts = _ytdlp.download_options(DownloadOptions(output_dir=str(tmp_path), ffmpeg_location="C:/ff/ffmpeg.exe"))
    assert opts["merge_output_format"] == "mp4"
    assert opts["ffmpeg_location"] == "C:/ff/ffmpeg.exe"
    assert opts["noplaylist"] is True
    assert opts["outtmpl"].startswith(str(tmp_path))
    assert opts["windowsfilenames"] is True
    listed = _ytdlp.download_options(DownloadOptions(output_dir=str(tmp_path), playlist_items="2"))
    assert listed["noplaylist"] is False and listed["playlist_items"] == "2"


def test_format_sort_keys():
    assert _ytdlp.format_sort(720) == ["res:720", "vcodec:h264", "acodec:aac"]
    assert _ytdlp.format_sort(None)[0] == "res"
    assert _ytdlp.format_sort(720, codec_first=True)[0] == "vcodec:h264"


def test_fit_template_keeps_short_paths_untouched():
    tpl = "%(title).150B [%(id)s].%(ext)s"
    assert _ytdlp.fit_template("C:\\U", tpl) == tpl


def test_fit_template_shrinks_title_for_deep_folders():
    deep = "C:\\" + "\\".join(["klasor" * 3] * 5)
    fitted = _ytdlp.fit_template(deep, "%(title).150B [%(id)s].%(ext)s")
    limit = int(fitted.split("%(title).")[1].split("B")[0])
    assert limit < 150
    assert len(os.path.abspath(deep)) + 1 + limit + _ytdlp._NAME_OVERHEAD <= _ytdlp.WINDOWS_MAX_PATH
    assert _ytdlp.fit_template("C:\\" + "x" * 400, "%(title).150B.%(ext)s") == "%(title).24B.%(ext)s"


def test_fit_template_without_title_limit():
    assert _ytdlp.fit_template("C:\\" + "x" * 300, "%(id)s.%(ext)s") == "%(id)s.%(ext)s"


@pytest.mark.parametrize(
    "fmt,rung",
    [
        ({"width": 1920, "height": 1080}, 1080),
        ({"width": 1080, "height": 1920}, 1080),
        ({"height": 720}, 720),
        ({}, None),
    ],
)
def test_resolution_rung(fmt, rung):
    assert _ytdlp.resolution_rung(fmt) == rung


def test_video_heights_ignores_audio_and_dedupes():
    assert _ytdlp.video_heights(YOUTUBE_LIKE) == [2160, 1080, 720, 480, 360]
    only_h264 = _ytdlp.video_heights(YOUTUBE_LIKE, lambda f: f["vcodec"].startswith("avc1"))
    assert only_h264 == [1080, 720, 480, 360]


def test_media_kind():
    assert _ytdlp.media_kind({"formats": YOUTUBE_LIKE}) is MediaKind.VIDEO
    assert _ytdlp.media_kind({"formats": YOUTUBE_LIKE[:2]}) is MediaKind.AUDIO
    assert _ytdlp.media_kind({"ext": "jpg"}) is MediaKind.IMAGE
    assert _ytdlp.media_kind({"ext": "mp3"}) is MediaKind.AUDIO
    assert _ytdlp.media_kind({}) is MediaKind.VIDEO
    assert _ytdlp.media_kind({}, MediaKind.AUDIO) is MediaKind.AUDIO


def test_best_thumbnail():
    assert _ytdlp.best_thumbnail({"thumbnail": "https://t/best"}) == "https://t/best"
    thumbs = {"thumbnails": [{"url": "https://t/small", "width": 120, "height": 90},
                             {"url": "https://t/big", "width": 1280, "height": 720},
                             {"url": "https://t/pref", "preference": 1, "width": 10, "height": 10}]}
    assert _ytdlp.best_thumbnail(thumbs) == "https://t/pref"
    assert _ytdlp.best_thumbnail({"thumbnails": [{"id": "0"}]}) is None


def test_item_from_info():
    info = {
        "id": "abc", "title": "Başlık", "webpage_url": "https://site/abc", "uploader": "kanal", "duration": 61,
        "extractor_key": "Reddit", "formats": YOUTUBE_LIKE, "thumbnail": "https://t", "view_count": 5,
    }
    item = _ytdlp.item_from_info(info, Platform.GENERIC)
    assert (item.id, item.url, item.title, item.uploader, item.duration) == ("abc", "https://site/abc", "Başlık",
                                                                           "kanal", 61)
    assert item.kind is MediaKind.VIDEO and item.has_audio and item.heights[0] == 2160
    assert item.extractor == "Reddit" and item.extra["view_count"] == 5


def test_item_from_info_video_only_source():
    info = {"id": "v", "formats": [{"format_id": "1", "vcodec": "h264", "acodec": "none", "height": 720}]}
    item = _ytdlp.item_from_info(info, Platform.GENERIC)
    assert item.has_audio is False and item.title == "v"


def test_run_download_rejects_when_already_cancelled(tmp_path):
    import threading

    from arnold_dw.core.platforms.errors import DownloadCancelled

    ev = threading.Event()
    ev.set()
    with pytest.raises(DownloadCancelled):
        _ytdlp.run_download("https://example.com/x.mp4", {"outtmpl": str(tmp_path / "x")}, cancel_event=ev)


def test_collect_paths_handles_playlists():
    info = {"entries": [{"requested_downloads": [{"filepath": "a.mp4"}]}, None,
                        {"requested_downloads": [{"filename": "b.mp4"}]}]}
    assert _ytdlp._collect_paths(info) == ["a.mp4", "b.mp4"]
    assert _ytdlp._collect_paths(None) == []


@pytest.mark.parametrize(
    "name,intermediate",
    [
        ("Video [id].f137.mp4", True),
        ("Video [id].fhls-audio-128000-Audio.mp4", True),
        ("Video [id].mp4", False),
        ("Song [id].flac", False),
    ],
)
def test_intermediate_pattern(name, intermediate):
    assert bool(_ytdlp._INTERMEDIATE_RE.search(name)) is intermediate
