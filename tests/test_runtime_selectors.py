import os
import subprocess

import pytest

from arnold_dw.core.runtime import binaries, selectors

ZOO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo", 19 s


# ---------------------------------------------------------------------------
# Offline: evaluate selectors with yt-dlp's real format engine on synthetic formats
# ---------------------------------------------------------------------------


def _video(fid, height, vcodec, ext="mp4", tbr=None):
    return {
        "format_id": fid, "url": f"https://example.invalid/{fid}", "ext": ext, "protocol": "https",
        "height": height, "width": height * 16 // 9, "vcodec": vcodec, "acodec": "none",
        "tbr": tbr or height, "fps": 30,
    }


def _audio(fid, acodec, ext, abr):
    return {
        "format_id": fid, "url": f"https://example.invalid/{fid}", "ext": ext, "protocol": "https",
        "vcodec": "none", "acodec": acodec, "abr": abr, "tbr": abr,
    }


def _muxed(fid, height, vcodec, acodec, ext="mp4"):
    return {
        "format_id": fid, "url": f"https://example.invalid/{fid}", "ext": ext, "protocol": "https",
        "height": height, "width": height * 16 // 9, "vcodec": vcodec, "acodec": acodec, "tbr": height,
    }


YOUTUBE_LIKE = [
    _muxed("18", 360, "avc1.42001E", "mp4a.40.2"),
    _audio("140", "mp4a.40.2", "m4a", 129),
    _audio("251", "opus", "webm", 160),
    _video("134", 360, "avc1.4d401e"),
    _video("243", 360, "vp09.00.21.08", ext="webm"),
    _video("136", 720, "avc1.4d401f"),
    _video("247", 720, "vp09.00.31.08", ext="webm"),
    _video("398", 720, "av01.0.05M.08", tbr=900),
    _video("137", 1080, "avc1.640028"),
    _video("248", 1080, "vp09.00.40.08", ext="webm", tbr=2500),
    _video("399", 1080, "av01.0.08M.08", tbr=2600),
    _video("401", 2160, "av01.0.12M.08", tbr=9000),
]


def _select(fmt, formats, **params):
    import yt_dlp

    info = {
        "id": "x", "title": "t", "extractor": "generic", "extractor_key": "Generic",
        "webpage_url": "https://example.invalid/x", "formats": [dict(f) for f in formats],
    }
    opts = {"quiet": True, "no_warnings": True, "simulate": True, "format": fmt, "ffmpeg_location": binaries.ffmpeg_path(), **params}
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.process_ie_result(info, download=False)
    return result.get("format_id")


@pytest.mark.parametrize(
    ("max_height", "expected"),
    [(360, "134+140"), (720, "136+140"), (1080, "137+140"), (2160, "137+140"), (None, "137+140")],
)
def test_compat_picks_h264_aac(max_height, expected):
    assert _select(selectors.video_selector(max_height, "compat"), YOUTUBE_LIKE) == expected


@pytest.mark.parametrize(
    ("max_height", "expected_video"),
    [(360, {"134", "243"}), (720, {"398"}), (1080, {"399"}), (2160, {"401"}), (None, {"401"})],
)
def test_quality_picks_best_video(max_height, expected_video):
    picked = _select(selectors.video_selector(max_height, "quality"), YOUTUBE_LIKE)
    video, audio = picked.split("+")
    assert video in expected_video
    assert audio in {"251", "140"}


def test_compat_keeps_aac_when_site_has_no_h264():
    formats = [_audio("a-aac", "mp4a.40.2", "m4a", 128), _audio("a-opus", "opus", "webm", 160), _video("v-vp9", 720, "vp9", "webm")]
    assert _select(selectors.video_selector(1080), formats) == "v-vp9+a-aac"


def test_compat_accepts_generic_codec_names():
    formats = [_muxed("hd", 720, "h264", "aac"), _muxed("webm", 1080, "vp8", "vorbis", ext="webm")]
    assert _select(selectors.video_selector(1080), formats) == "hd"


def test_cap_falls_back_to_smallest_step_above():
    formats = [_muxed("only-hd", 1080, "avc1.64001F", "mp4a.40.2")]
    assert _select(selectors.video_selector(360), formats) == "only-hd"


def test_quality_skips_codecs_that_do_not_fit_mp4():
    formats = [
        _video("v8", 1080, "vp8", "webm", tbr=5000),
        _video("v9", 720, "vp9", "webm"),
        _audio("a-vorbis", "vorbis", "webm", 192),
        _audio("a-opus", "opus", "webm", 160),
    ]
    assert _select(selectors.video_selector(None, "quality"), formats) == "v9+a-opus"


@pytest.mark.parametrize(("codec", "expected"), [("mp3", "251"), ("m4a", "140"), ("opus", "251")])
def test_audio_selector_avoids_reencoding(codec, expected):
    assert _select(selectors.audio_selector(codec), YOUTUBE_LIKE) == expected


def test_audio_selector_falls_back_to_muxed_file():
    assert _select(selectors.audio_selector("m4a"), [_muxed("only", 360, "h264", "aac")]) == "only"


# ---------------------------------------------------------------------------
# Offline: option shapes
# ---------------------------------------------------------------------------


def test_invalid_arguments():
    with pytest.raises(ValueError):
        selectors.video_selector(720, "best")
    with pytest.raises(ValueError):
        selectors.video_selector(0)
    with pytest.raises(ValueError):
        selectors.audio_postprocessors("flac")
    with pytest.raises(ValueError):
        selectors.audio_postprocessors("mp3", 1000)
    with pytest.raises(ValueError):
        selectors.audio_selector("wav")


def test_audio_postprocessors():
    assert selectors.audio_postprocessors("m4a", "256") == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "256"}
    ]


def test_plain_downloads_match_current_app_behaviour():
    video = selectors.video_download_options(720)
    assert video == {"format": selectors.video_selector(720), "merge_output_format": "mp4", "postprocessors": []}
    audio = selectors.audio_download_options("mp3", 192)
    assert audio["format"] == "ba/b"
    assert audio["postprocessors"] == selectors.audio_postprocessors("mp3", 192)
    assert "writethumbnail" not in audio


def test_embedding_order_and_flags():
    opts = selectors.audio_download_options("mp3", 192, embed_metadata=True, embed_thumbnail=True)
    assert opts["writethumbnail"] is True
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert keys == ["FFmpegThumbnailsConvertor", "FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
    only_meta = selectors.video_download_options(480, embed_metadata=True)
    assert [pp["key"] for pp in only_meta["postprocessors"]] == ["FFmpegMetadata"]
    assert "writethumbnail" not in only_meta


@pytest.mark.parametrize(
    ("ext", "ffprobe", "ok"),
    [("mp3", False, True), ("mp3", True, True), ("m4a", False, False), ("m4a", True, True),
     ("mp4", False, False), ("mp4", True, True), ("opus", True, False), ("webm", True, False)],
)
def test_cover_supported(ext, ffprobe, ok):
    assert selectors.cover_supported(ext, ffprobe) is ok


def test_cover_dropped_without_ffprobe_for_mp4_family():
    for opts in (selectors.video_download_options(720, embed_metadata=True, embed_thumbnail=True, ffprobe=False),
                 selectors.audio_download_options("m4a", 128, embed_metadata=True, embed_thumbnail=True, ffprobe=False)):
        assert "writethumbnail" not in opts
        assert "EmbedThumbnail" not in [pp["key"] for pp in opts["postprocessors"]]
        assert "FFmpegMetadata" in [pp["key"] for pp in opts["postprocessors"]]
    kept = selectors.video_download_options(720, embed_thumbnail=True, ffprobe=True)
    assert kept["writethumbnail"] is True
    assert [pp["key"] for pp in kept["postprocessors"]] == ["FFmpegThumbnailsConvertor", "EmbedThumbnail"]


@pytest.mark.parametrize(
    ("ext", "expected"),
    [
        ("mp4", [("EmbedThumbnail", None), ("FFmpegMetadata", True)]),
        ("m4a", [("FFmpegMetadata", False), ("EmbedThumbnail", None)]),
        ("mp3", [("FFmpegMetadata", True), ("EmbedThumbnail", None)]),
    ],
)
def test_embed_order_per_format(ext, expected):
    steps = selectors.embed_postprocessors(ext, metadata=True, thumbnail=True)
    assert [(pp["key"], pp.get("add_chapters")) for pp in steps] == expected


def test_embed_single_steps():
    assert selectors.embed_postprocessors("mp4", metadata=True, thumbnail=False)[0]["add_chapters"] is True
    assert selectors.embed_postprocessors("m4a", metadata=True, thumbnail=False)[0]["add_chapters"] is True
    assert [pp["key"] for pp in selectors.embed_postprocessors("m4a", False, True)] == ["EmbedThumbnail"]
    assert selectors.embed_postprocessors("mp3", False, False) == []


def test_cover_autodetects_ffprobe(monkeypatch):
    monkeypatch.setattr(binaries, "ffprobe_path", lambda: None)
    assert "writethumbnail" not in selectors.video_download_options(720, embed_thumbnail=True)
    monkeypatch.setattr(binaries, "ffprobe_path", lambda: "C:/x/ffprobe.exe")
    assert selectors.video_download_options(720, embed_thumbnail=True)["writethumbnail"] is True


def test_opus_skips_cover_but_keeps_metadata():
    opts = selectors.audio_download_options("opus", 128, embed_metadata=True, embed_thumbnail=True, ffprobe=True)
    assert "writethumbnail" not in opts
    assert [pp["key"] for pp in opts["postprocessors"]] == ["FFmpegExtractAudio", "FFmpegMetadata"]


def test_postprocessor_keys_exist_in_yt_dlp():
    from yt_dlp.postprocessor import get_postprocessor

    opts = selectors.audio_download_options("mp3", 128, embed_metadata=True, embed_thumbnail=True)
    for pp in opts["postprocessors"]:
        assert get_postprocessor(pp["key"])


def test_options_are_accepted_by_yt_dlp():
    import yt_dlp

    for opts in (
        selectors.video_download_options(1080, "quality", embed_metadata=True, embed_thumbnail=True),
        selectors.audio_download_options("m4a", 160, embed_metadata=True, embed_thumbnail=True),
    ):
        with yt_dlp.YoutubeDL({"quiet": True, **opts}) as ydl:
            assert ydl.build_format_selector(opts["format"])


# ---------------------------------------------------------------------------
# Network: real YouTube video
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def zoo_info():
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, **binaries.ytdlp_runtime_options()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(ZOO_URL, download=False)


def _resolve(info, fmt):
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "format": fmt, **binaries.ytdlp_runtime_options()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        selector = ydl.build_format_selector(fmt)
        ctx = {"formats": info["formats"], "has_merged_format": True, "incomplete_formats": False}
        chosen = next(iter(selector(ctx)), None)
    assert chosen is not None, f"nothing selected for {fmt}"
    return chosen.get("requested_formats") or [chosen]


@pytest.mark.network
@pytest.mark.parametrize("max_height", [144, 240, 360])
def test_network_compat_selects_h264_and_aac(zoo_info, max_height):
    parts = _resolve(zoo_info, selectors.video_selector(max_height, "compat"))
    vcodecs = [p["vcodec"] for p in parts if p.get("vcodec") not in (None, "none")]
    acodecs = [p["acodec"] for p in parts if p.get("acodec") not in (None, "none")]
    assert vcodecs and all(v.startswith("avc1") for v in vcodecs), parts
    assert acodecs and all(a.startswith("mp4a") for a in acodecs), parts
    heights = [p["height"] for p in parts if p.get("height")]
    best_h264 = max(f["height"] for f in zoo_info["formats"]
                    if (f.get("vcodec") or "").startswith("avc1") and f.get("height") and f["height"] <= max_height)
    assert max(heights) == best_h264


@pytest.mark.network
def test_network_quality_selects_highest_resolution(zoo_info):
    parts = _resolve(zoo_info, selectors.video_selector(None, "quality"))
    top = max(f["height"] for f in zoo_info["formats"] if f.get("height"))
    assert max(p.get("height") or 0 for p in parts) == top
    audio = [p for p in parts if p.get("acodec") not in (None, "none")]
    assert audio, parts


@pytest.mark.network
@pytest.mark.parametrize(("codec", "prefix"), [("m4a", "mp4a"), ("opus", "opus")])
def test_network_audio_selector(zoo_info, codec, prefix):
    parts = _resolve(zoo_info, selectors.audio_selector(codec))
    assert parts[0]["acodec"].startswith(prefix)


def _ffmpeg_report(path):
    """ffmpeg's own view of a file (tags + streams); stands in for ffprobe, which is not shipped."""
    proc = subprocess.run([binaries.ffmpeg_path(), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stderr


def _download(tmp_path, opts):
    import yt_dlp

    base = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
        "outtmpl": str(tmp_path / "%(id)s.%(ext)s"), **binaries.ytdlp_runtime_options(),
    }
    with yt_dlp.YoutubeDL({**base, **opts}) as ydl:
        ydl.download([ZOO_URL])


def _assert_tagged(report, cover, chapters=True):
    assert "Me at the zoo" in report, report
    assert ("attached pic" in report) is cover, report
    assert ("Chapter #" in report) is chapters, report  # the zoo video has 3 chapters


def test_no_gpl_tagging_library_is_used():
    """The app must not ship mutagen (GPL); yt-dlp then embeds covers through ffmpeg."""
    import yt_dlp.dependencies

    assert yt_dlp.dependencies.mutagen is None


@pytest.fixture(params=["default", "with-ffprobe"])
def ffmpeg_setup(request, monkeypatch):
    """``default``: whatever binaries finds (the dev bin/ has no ffprobe).
    ``with-ffprobe``: ffmpeg + ffprobe from ARNOLD_DW_TEST_FFMPEG_DIR, like a build that ships both."""
    if request.param == "with-ffprobe":
        folder = os.environ.get("ARNOLD_DW_TEST_FFMPEG_DIR")
        if not folder:
            pytest.skip("set ARNOLD_DW_TEST_FFMPEG_DIR to a folder with ffmpeg.exe + ffprobe.exe")
        monkeypatch.setattr(binaries, "ffmpeg_path", lambda: os.path.join(folder, "ffmpeg.exe"))
        monkeypatch.setattr(binaries, "ffprobe_path", lambda: os.path.join(folder, "ffprobe.exe"))
    return binaries.ffprobe_path() is not None


@pytest.mark.network
@pytest.mark.parametrize("codec", ["mp3", "m4a", "opus"])
def test_network_audio_download_with_tags(tmp_path, ffmpeg_setup, codec):
    _download(tmp_path, selectors.audio_download_options(codec, 128, embed_metadata=True, embed_thumbnail=True))
    audio = tmp_path / f"jNQXAC9IVRw.{codec}"
    assert audio.is_file() and audio.stat().st_size > 50_000
    assert sorted(os.listdir(tmp_path)) == [audio.name], "no leftover thumbnail / source files"
    cover = selectors.cover_supported(codec, ffmpeg_setup)
    _assert_tagged(_ffmpeg_report(audio), cover, chapters=not (codec == "m4a" and cover))


@pytest.mark.network
def test_network_compat_video_download_with_tags(tmp_path, ffmpeg_setup):
    _download(tmp_path, selectors.video_download_options(240, embed_metadata=True, embed_thumbnail=True))
    video = tmp_path / "jNQXAC9IVRw.mp4"
    assert video.is_file() and video.stat().st_size > 50_000
    assert sorted(os.listdir(tmp_path)) == [video.name]
    report = _ffmpeg_report(video)
    _assert_tagged(report, selectors.cover_supported("mp4", ffmpeg_setup))
    assert "Video: h264" in report and "Audio: aac" in report, report
