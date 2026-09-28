import os
import threading

import pytest
import yt_dlp

from arnold_dw.core import youtube
from arnold_dw.core.errors import DownloadCancelled


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "http://youtube.com/watch?v=jNQXAC9IVRw&t=5",
    "youtube.com/watch?v=jNQXAC9IVRw",
    "https://m.youtube.com/watch?v=jNQXAC9IVRw",
    "https://music.youtube.com/watch?v=jNQXAC9IVRw",
    "https://youtu.be/jNQXAC9IVRw",
    "https://www.youtube.com/shorts/abc_DEF-123",
    "https://www.youtube.com/embed/jNQXAC9IVRw",
    "https://www.youtube.com/live/abc123",
    "HTTPS://WWW.YOUTUBE.COM/WATCH?V=jNQXAC9IVRw",
])
def test_is_youtube_url_accepts(url):
    assert youtube.is_youtube_url(url)


@pytest.mark.parametrize("url", [
    "",
    None,
    "hello",
    "https://vimeo.com/123",
    "https://www.youtube.com/",
    "https://www.youtube.com/@channel",
    "https://www.instagram.com/p/abc/",
    "look at https://youtu.be/jNQXAC9IVRw",
])
def test_is_youtube_url_rejects(url):
    assert not youtube.is_youtube_url(url)


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path, monkeypatch):
    # download() reads the saved settings; never touch the real user profile.
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def test_build_download_options(tmp_path):
    opts = youtube.build_download_options("MP3", "320 kbps", str(tmp_path))
    assert opts["noplaylist"] is True
    assert opts["windowsfilenames"] is True
    assert opts["outtmpl"] == os.path.join(str(tmp_path), "%(title).150B [%(id)s].%(ext)s")
    extract = [pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio"]
    assert extract[0]["preferredquality"] == "320"
    assert isinstance(opts["logger"], youtube.YtDlpLogger)


def test_build_download_options_uses_discovered_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        youtube.binaries,
        "ytdlp_runtime_options",
        lambda: {"ffmpeg_location": "bin/ffmpeg.exe", "js_runtimes": {"deno": {"path": "bin/deno.exe"}}},
    )

    opts = youtube.build_download_options("MP4", "720p", str(tmp_path))

    assert opts["ffmpeg_location"] == "bin/ffmpeg.exe"
    assert opts["js_runtimes"] == {"deno": {"path": "bin/deno.exe"}}


def test_fetch_preview_uses_discovered_runtime(monkeypatch):
    runtime_options = {"js_runtimes": {"deno": {"path": "bin/deno.exe"}}}
    monkeypatch.setattr(youtube.binaries, "ytdlp_runtime_options", lambda: runtime_options)
    monkeypatch.setattr(youtube.http, "fetch_image", lambda *_args, **_kwargs: None)
    seen = {}

    class PreviewYDL:
        def __init__(self, opts):
            seen.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def extract_info(self, _url, download):
            assert download is False
            return {"id": "video", "thumbnail": None}

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", PreviewYDL)

    preview = youtube.fetch_preview("https://youtube.com/watch?v=video")

    assert preview.info["id"] == "video"
    assert seen["js_runtimes"] == runtime_options["js_runtimes"]


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL; `script(opts, ydl)` plays the hook sequence."""

    script = None

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def download(self, urls):
        FakeYDL.script(self.opts)


@pytest.fixture
def fake_ydl(monkeypatch):
    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def _progress(opts, **d):
    for hook in opts["progress_hooks"]:
        hook(d)


def _pp(opts, status):
    for hook in opts["postprocessor_hooks"]:
        hook({"status": status, "postprocessor": "Merger"})


def test_download_reports_progress_then_processing(tmp_path, fake_ydl):
    def script(opts):
        _progress(opts, status="downloading", total_bytes=200, downloaded_bytes=50, speed=1000, eta=3,
                  tmpfilename="v.part", filename="v")
        _progress(opts, status="downloading", total_bytes_estimate=200, downloaded_bytes=200)
        _progress(opts, status="finished", filename="v")
        _progress(opts, status="downloading", downloaded_bytes=10)  # unknown total (audio part)
        _pp(opts, "started")
        _pp(opts, "finished")
        _pp(opts, "started")  # a second post-processor must not re-announce processing

    fake_ydl.script = script
    progress, processing = [], []
    youtube.download("u", "MP4", "720p", str(tmp_path / "out"), threading.Event(),
                     on_progress=lambda *a: progress.append(a),
                     on_processing=lambda: processing.append(True))
    assert progress == [(0.25, 50, 1000, 3), (1.0, 200, None, None), (None, 10, None, None)]
    assert processing == [True]
    assert os.path.isdir(tmp_path / "out")


def test_download_cancel_raises_and_removes_partial_files(tmp_path, fake_ydl):
    cancel = threading.Event()
    part = tmp_path / "Title [id].f137.mp4.part"
    done_stream = tmp_path / "Title [id].f137.mp4"
    frag = tmp_path / "Title [id].f137.mp4.part-Frag3"
    unrelated = tmp_path / "keep.mp4"
    for p in (part, done_stream, frag, unrelated):
        p.write_bytes(b"x")

    def script(opts):
        _progress(opts, status="downloading", downloaded_bytes=1, total_bytes=2,
                  tmpfilename=str(part), filename=str(done_stream))
        cancel.set()
        _progress(opts, status="downloading", downloaded_bytes=2, total_bytes=2)

    fake_ydl.script = script
    with pytest.raises(DownloadCancelled):
        youtube.download("u", "MP4", "720p", str(tmp_path), cancel)
    assert not part.exists()
    assert not done_stream.exists()
    assert not frag.exists()
    assert unrelated.exists()


def test_download_error_propagates_when_not_cancelled(tmp_path, fake_ydl):
    def script(opts):
        raise yt_dlp.utils.DownloadError("ERROR: Video unavailable")

    fake_ydl.script = script
    with pytest.raises(yt_dlp.utils.DownloadError):
        youtube.download("u", "MP3", "192 kbps", str(tmp_path), threading.Event())


def test_cancel_during_processing_is_not_reported_as_cancelled(tmp_path, fake_ydl):
    cancel = threading.Event()

    def script(opts):
        _pp(opts, "started")
        cancel.set()
        raise yt_dlp.utils.PostProcessingError("ffmpeg died")

    fake_ydl.script = script
    with pytest.raises(yt_dlp.utils.PostProcessingError):
        youtube.download("u", "MP3", "192 kbps", str(tmp_path), cancel)


@pytest.mark.network
@pytest.mark.smoke
def test_real_preview_me_at_the_zoo():
    preview = youtube.fetch_preview("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert preview.info["id"] == "jNQXAC9IVRw"
    assert preview.info["duration"] == 19
    assert preview.thumbnail is not None
