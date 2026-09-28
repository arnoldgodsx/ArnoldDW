import os
import shutil

import pytest

from arnold_dw.core.platforms import generic
from arnold_dw.core.platforms.errors import ErrorCode, PlatformError
from arnold_dw.core.platforms.models import Collection, DownloadOptions, MediaItem, MediaKind, Platform
from arnold_dw.core.platforms.router import analyze

# One real, publicly reachable link per verified site (checked 2026-09-27/28 from TR).
LIVE_LINKS = {
    "X (Twitter)": "https://x.com/SpaceX/status/2080826996490199070",
    "Reddit": "https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/",
    "SoundCloud": "https://soundcloud.com/the80m/the-following",
    "Twitch (klip)": "https://clips.twitch.tv/FaintLightGullWholeWheat",
    "Dailymotion": "https://www.dailymotion.com/video/x5kesuj",
}


def test_every_supported_site_has_a_live_link():
    assert {s.name for s in generic.SUPPORTED_SITES} == set(LIVE_LINKS)


@pytest.mark.parametrize("site", generic.SUPPORTED_SITES, ids=lambda s: s.name)
def test_supported_site_links_route_to_generic(site):
    det = analyze(LIVE_LINKS[site.name])
    assert det.platform is Platform.GENERIC
    assert det.extractor in site.extractors
    assert generic.is_verified(det.extractor)


def test_is_verified():
    assert generic.is_verified("Twitter")
    assert not generic.is_verified("Vimeo")
    assert not generic.is_verified("Facebook")
    assert not generic.is_verified(None)


class FakeYDL:
    def __init__(self, processed=None, exc=None):
        self.processed = processed
        self.exc = exc
        self.closed = False

    def process_ie_result(self, info, download=False):
        if self.exc:
            raise self.exc
        return self.processed

    def close(self):
        self.closed = True


def _patch_extract(monkeypatch, info, ydl):
    seen = {}

    def fake_extract(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return ydl, info

    monkeypatch.setattr(generic, "extract", fake_extract)
    return seen


VIDEO_INFO = {
    "id": "zv89llsvexdz", "title": "That small heart attack.", "extractor_key": "Reddit",
    "webpage_url": "https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/",
    "formats": [{"format_id": "hls-480", "vcodec": "avc1", "acodec": "mp4a", "width": 640, "height": 480}],
    "duration": 12,
}


def test_resolve_single_video(monkeypatch):
    ydl = FakeYDL(processed=VIDEO_INFO)
    seen = _patch_extract(monkeypatch, {"id": "zv89llsvexdz", "_type": "video"}, ydl)
    item = generic.resolve("bak: https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/ !")
    assert seen["url"] == "https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/"
    assert seen["kw"]["process"] is False
    assert isinstance(item, MediaItem)
    assert item.platform is Platform.GENERIC and item.kind is MediaKind.VIDEO and item.heights == [480]
    assert ydl.closed


def test_resolve_audio_site_defaults_to_audio(monkeypatch):
    info = {"id": "1", "title": "Song", "extractor_key": "Soundcloud", "webpage_url": "https://soundcloud.com/a/b",
            "formats": [{"format_id": "hls_mp3", "vcodec": "none", "acodec": "mp3"}]}
    _patch_extract(monkeypatch, {"id": "1"}, FakeYDL(processed=info))
    assert generic.resolve("https://soundcloud.com/a/b").kind is MediaKind.AUDIO


def test_resolve_processing_error_is_mapped(monkeypatch):
    ydl = FakeYDL(exc=RuntimeError("ERROR: [twitter] 1: No video could be found in this tweet"))
    _patch_extract(monkeypatch, {"id": "1"}, ydl)
    with pytest.raises(PlatformError) as err:
        generic.resolve("https://x.com/a/status/1")
    assert err.value.code is ErrorCode.NO_MEDIA
    assert ydl.closed


def test_resolve_rejects_text_without_link():
    with pytest.raises(PlatformError) as err:
        generic.resolve("link yok")
    assert err.value.code is ErrorCode.INVALID_LINK


def test_resolve_multi_video_post_becomes_collection(monkeypatch):
    entries = [
        {"id": "a1", "title": "SpaceX - clip", "url": "https://video.twimg.com/a1.mp4", "extractor_key": "Twitter",
         "formats": [{"format_id": "1", "vcodec": "avc1", "acodec": "mp4a", "height": 2160, "width": 3840}]},
        {"id": "a2", "title": "SpaceX - clip", "url": "https://video.twimg.com/a2.mp4", "extractor_key": "Twitter"},
    ]
    info = {"_type": "playlist", "id": "209", "title": "SpaceX - static fire", "extractor_key": "Twitter",
            "webpage_url": "https://x.com/SpaceX/status/209", "entries": iter(entries)}
    ydl = FakeYDL()
    _patch_extract(monkeypatch, info, ydl)
    col = generic.resolve("https://x.com/SpaceX/status/209")
    assert isinstance(col, Collection)
    assert [e.id for e in col.entries] == ["a1", "a2"]
    assert col.entries[1].extra == {"source_url": "https://x.com/SpaceX/status/209", "playlist_index": 2}
    assert col.entries[0].heights == [2160]
    assert not col.has_more


def test_resolve_flat_playlist_entries(monkeypatch):
    entries = [{"_type": "url", "ie_key": "Soundcloud", "id": str(i), "title": f"Track {i}",
                "url": f"https://soundcloud.com/a/t{i}"} for i in range(1, 76)]
    info = {"_type": "playlist", "id": "set", "title": "Set", "extractor_key": "SoundcloudSet",
            "entries": (e for e in entries), "playlist_count": 75}
    _patch_extract(monkeypatch, info, FakeYDL())
    col = generic.resolve("https://soundcloud.com/a/sets/set", page_size=50)
    assert len(col.entries) == 50 and col.has_more and col.count == 75
    first = col.entries[0]
    assert first.kind is MediaKind.AUDIO and first.url == "https://soundcloud.com/a/t1"
    assert "source_url" not in first.extra
    col.load_more(50)
    assert len(col.entries) == 75 and not col.has_more


def test_resolve_empty_playlist(monkeypatch):
    _patch_extract(monkeypatch, {"_type": "playlist", "id": "x", "entries": iter([])}, FakeYDL())
    with pytest.raises(PlatformError) as err:
        generic.resolve("https://x.com/a/status/1")
    assert err.value.code is ErrorCode.NO_MEDIA


def _capture_download(monkeypatch, result=("C:/out/a.mp4",)):
    seen = {}

    def fake_run(url, opts, **kw):
        seen["url"], seen["opts"], seen["kw"] = url, opts, kw
        return list(result)

    monkeypatch.setattr(generic, "run_download", fake_run)
    return seen


def test_download_url(monkeypatch, tmp_path):
    seen = _capture_download(monkeypatch)
    paths = generic.download("https://clips.twitch.tv/FaintLightGullWholeWheat",
                             DownloadOptions(output_dir=str(tmp_path), max_height=720))
    assert paths == ["C:/out/a.mp4"]
    assert seen["url"] == "https://clips.twitch.tv/FaintLightGullWholeWheat"
    assert seen["opts"]["format_sort"][0] == "res:720"


def test_download_entry_goes_through_parent_post(monkeypatch, tmp_path):
    seen = _capture_download(monkeypatch)
    item = MediaItem(id="a2", url="https://video.twimg.com/a2.mp4",
                     extra={"source_url": "https://x.com/SpaceX/status/209", "playlist_index": 2})
    generic.download(item, DownloadOptions(output_dir=str(tmp_path)))
    assert seen["url"] == "https://x.com/SpaceX/status/209"
    assert seen["opts"]["playlist_items"] == "2" and seen["opts"]["noplaylist"] is False


def test_download_audio_only_source_switches_to_audio(monkeypatch, tmp_path):
    seen = _capture_download(monkeypatch)
    item = MediaItem(id="1", url="https://soundcloud.com/a/b", kind=MediaKind.AUDIO)
    generic.download(item, DownloadOptions(output_dir=str(tmp_path), mode=MediaKind.VIDEO))
    assert seen["opts"]["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_download_nothing_produced(monkeypatch, tmp_path):
    _capture_download(monkeypatch, result=())
    with pytest.raises(PlatformError) as err:
        generic.download("https://clips.twitch.tv/x", DownloadOptions(output_dir=str(tmp_path)))
    assert err.value.code is ErrorCode.NO_MEDIA


# --------------------------------------------------------------------------------------------
# Real network (run with --network)
# --------------------------------------------------------------------------------------------


def _ffmpeg():
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "ffmpeg.exe")
    return local if os.path.exists(local) else shutil.which("ffmpeg")


@pytest.mark.network
@pytest.mark.parametrize("name", sorted(LIVE_LINKS))
def test_live_resolve_supported_sites(name):
    result = generic.resolve(LIVE_LINKS[name])
    assert isinstance(result, MediaItem)
    assert result.title
    assert generic.is_verified(result.extractor)
    expected = MediaKind.AUDIO if name == "SoundCloud" else MediaKind.VIDEO
    assert result.kind is expected


@pytest.mark.network
def test_live_multi_video_tweet():
    col = generic.resolve("https://x.com/SpaceX/status/2093477720638341395")
    assert isinstance(col, Collection) and len(col.entries) == 2


@pytest.mark.network
@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not available")
def test_live_download_twitch_clip(tmp_path):
    item = generic.resolve(LIVE_LINKS["Twitch (klip)"])
    paths = generic.download(item, DownloadOptions(output_dir=str(tmp_path), max_height=360,
                                                   ffmpeg_location=_ffmpeg()))
    assert len(paths) == 1 and paths[0].endswith(".mp4") and os.path.getsize(paths[0]) > 100_000
