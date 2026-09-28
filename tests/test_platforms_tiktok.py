import json
import os
import threading

import pytest
import requests

from arnold_dw.core.platforms import tiktok
from arnold_dw.core.platforms.errors import DownloadCancelled, ErrorCode, PlatformError
from arnold_dw.core.platforms.models import DownloadOptions, MediaAsset, MediaItem, MediaKind, Platform
from tests.test_platforms_ytdlp import pick

# Mirrors the real `yt-dlp -F` output for a 2026 TikTok video (ids shortened).
TIKTOK_FORMATS = [
    {"format_id": "audio", "ext": "mp3", "vcodec": "none", "acodec": "mp3"},
    {"format_id": "download", "vcodec": "h264", "acodec": "aac", "format_note": "Download video, watermarked",
     "preference": -2},
    {"format_id": "bytevc1_540p-0", "vcodec": "h265", "acodec": "aac", "width": 576, "height": 1024, "tbr": 625},
    {"format_id": "h264_720p-0", "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "tbr": 1741},
    {"format_id": "bytevc1_720p-0", "vcodec": "h265", "acodec": "aac", "width": 720, "height": 1280, "tbr": 749},
    {"format_id": "bytevc1_1080p-0", "vcodec": "h265", "acodec": "aac", "width": 1080, "height": 1920, "tbr": 1139},
    {"format_id": "bytevc2_1080p-0", "vcodec": "bytevc2", "acodec": "aac", "width": 1080, "height": 1920,
     "tbr": 900, "preference": -100},
]


def _video_opts(**kw):
    return tiktok._video_download_options(DownloadOptions(output_dir="out", **kw))


def test_video_picks_watermark_free_h264():
    assert pick(TIKTOK_FORMATS, _video_opts()) == "h264_720p-0"
    assert pick(TIKTOK_FORMATS, _video_opts(max_height=1080)) == "h264_720p-0"


def test_video_never_picks_watermarked_or_bytevc2_when_clean_exists():
    clean_h265_only = [f for f in TIKTOK_FORMATS if not f["format_id"].startswith("h264")]
    chosen = pick(clean_h265_only, _video_opts())
    assert chosen.startswith("bytevc1_1080p")


def test_video_falls_back_to_watermarked_as_last_resort():
    only_download = [f for f in TIKTOK_FORMATS if f["format_id"] in ("download", "audio")]
    assert pick(only_download, _video_opts()) == "download"


def test_audio_is_taken_from_the_video_not_the_music_track():
    opts = _video_opts(mode=MediaKind.AUDIO)
    assert pick(TIKTOK_FORMATS, opts) == "h264_720p-0"
    assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_is_watermark_free():
    by_id = {f["format_id"]: f for f in TIKTOK_FORMATS}
    assert tiktok.is_watermark_free(by_id["h264_720p-0"])
    assert not tiktok.is_watermark_free(by_id["download"])
    assert not tiktok.is_watermark_free(by_id["audio"])
    assert not tiktok.is_watermark_free(by_id["bytevc2_1080p-0"])


def test_video_item_from_info():
    info = {
        "id": "7689568478570843422", "title": "the throwback\nsounds  #fyp",
        "webpage_url": "https://www.tiktok.com/@tiktok/video/7689568478570843422", "uploader": "tiktok",
        "track": "original sound", "artist": "TikTok", "duration": 52, "formats": TIKTOK_FORMATS,
        "extractor_key": "TikTok",
    }
    item = tiktok.video_item_from_info(info)
    assert item.platform is Platform.TIKTOK and item.kind is MediaKind.VIDEO
    assert item.title == "the throwback sounds #fyp"
    assert item.heights == [720]  # only rungs we will deliver as H.264
    assert item.extra["watermark_free"] is True
    assert item.extra["music_title"] == "original sound" and item.extra["username"] == "tiktok"


def test_video_item_without_clean_formats():
    info = {"id": "1", "formats": [f for f in TIKTOK_FORMATS if f["format_id"] in ("download", "audio")]}
    assert tiktok.video_item_from_info(info).extra["watermark_free"] is False


def test_photo_post_seen_through_video_url_is_audio_only():
    info = {"id": "1", "formats": [TIKTOK_FORMATS[0]]}
    assert tiktok.video_item_from_info(info).kind is MediaKind.AUDIO


def _img(n):
    return f"https://p16-common-sign.tiktokcdn.com/tos-maliva-i-photomode-us/{n}~tplv-photomode-image.jpeg?x-expires=1"


EMBED_VIDEO_DATA = {
    "itemInfos": {"id": "7680195684426927373", "text": "In 19th-century\nEngland ...",
                  "covers": [_img("cover")], "video": {"urls": []}},
    "authorInfos": {"uniqueId": "natgeo", "nickName": "National Geographic"},
    "musicInfos": {"musicName": "Dark Mystery", "authorName": "Eitan Epstein Music",
                   "playUrl": ["https://sf16-ies-music-sg.tiktokcdn.com/obj/tos-alisg-ve-2774/abc"]},
    "imagePostInfo": {"displayImages": [
        {"height": 1350, "width": 1080, "urlList": [_img(1), _img("1b")]},
        {"height": 1350, "width": 1080, "urlList": [_img(2)]},
        {"height": 1350, "width": 1080, "urlList": []},
    ]},
}


def _embed_html(video_data, video_id="7680195684426927373"):
    state = {"source": {"data": {f"/embed/v2/{video_id}": {"videoData": video_data, "code": 200}}}}
    return f'<html><script id="__FRONTITY_CONNECT_STATE__" type="application/json">{json.dumps(state)}</script>'


def test_slideshow_from_embed():
    item = tiktok.slideshow_from_embed(EMBED_VIDEO_DATA, "7680195684426927373")
    assert item.kind is MediaKind.SLIDESHOW and item.platform is Platform.TIKTOK
    assert item.url == "https://www.tiktok.com/@natgeo/photo/7680195684426927373"
    images = [a for a in item.assets if a.kind is MediaKind.IMAGE]
    assert [a.url for a in images] == [_img(1), _img(2)]  # entry without URLs skipped, first mirror used
    assert images[0].width == 1080 and images[0].ext == "jpg"
    music = [a for a in item.assets if a.kind is MediaKind.AUDIO]
    assert len(music) == 1 and item.has_audio
    assert item.title == "In 19th-century England ..."
    assert item.uploader == "National Geographic"
    assert item.extra == {"image_count": 2, "watermark_free": True, "username": "natgeo",
                          "music_title": "Dark Mystery", "music_author": "Eitan Epstein Music"}
    assert item.thumbnail_url == _img("cover")


def test_slideshow_from_embed_without_images():
    assert tiktok.slideshow_from_embed({"itemInfos": {}, "imagePostInfo": {"displayImages": []}}, "1") is None
    assert tiktok.slideshow_from_embed({}, "1") is None


def test_slideshow_from_item_struct():
    struct = {
        "desc": "BBC caption", "author": {"uniqueId": "bbcnews", "nickname": "BBC News"},
        "music": {"title": "News", "authorName": "Takashi", "playUrl": "https://music/x"},
        "video": {"cover": _img("c")},
        "imagePost": {"images": [{"imageURL": {"urlList": [_img(1)]}, "imageWidth": 1080, "imageHeight": 1440}]},
    }
    item = tiktok.slideshow_from_item_struct(struct, "7689539430922620182")
    assert item.kind is MediaKind.SLIDESHOW
    assert [a.kind for a in item.assets] == [MediaKind.IMAGE, MediaKind.AUDIO]
    assert item.assets[0].height == 1440
    assert item.extra["username"] == "bbcnews" and item.title == "BBC caption"
    assert tiktok.slideshow_from_item_struct({}, "1") is None


def test_slideshow_without_music_or_caption():
    data = {"imagePostInfo": {"displayImages": [{"urlList": [_img(1)]}]}}
    item = tiktok.slideshow_from_embed(data, "42")
    assert item.has_audio is False
    assert item.title == "TikTok 42"
    assert item.url == "https://www.tiktok.com/@/photo/42"


class FakeResponse:
    def __init__(self, status=200, text="", content=b"", content_type="application/octet-stream"):
        self.status_code = status
        self.text = text
        self._content = content
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(content))}
        self.ok = status < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), 4):
            yield self._content[i:i + 4]

    def close(self):
        pass


class FakeSession:
    def __init__(self, routes):
        self.routes = routes  # url -> FakeResponse or list of FakeResponse (consumed in order)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        route = self.routes[url]
        if isinstance(route, list):
            return route.pop(0)
        return route


def test_fetch_embed_retries_interstitial(monkeypatch):
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    url = tiktok.EMBED_URL.format(id="7680195684426927373")
    session = FakeSession({url: [FakeResponse(text="<html>challenge</html>"),
                                 FakeResponse(text=_embed_html(EMBED_VIDEO_DATA))]})
    data = tiktok._fetch_embed_video_data("7680195684426927373", session)
    assert data["authorInfos"]["uniqueId"] == "natgeo"
    assert len(session.calls) == 2


def test_fetch_embed_gives_up(monkeypatch):
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    url = tiktok.EMBED_URL.format(id="1")
    session = FakeSession({url: FakeResponse(text="<html>challenge</html>")})
    assert tiktok._fetch_embed_video_data("1", session) is None
    assert len(session.calls) == tiktok._EMBED_ATTEMPTS


def test_resolve_photo_uses_embed(monkeypatch):
    url = tiktok.EMBED_URL.format(id="7680195684426927373")
    session = FakeSession({url: FakeResponse(text=_embed_html(EMBED_VIDEO_DATA))})
    monkeypatch.setattr(tiktok, "_fetch_item_struct", lambda *a: pytest.fail("fallback must not run"))
    item = tiktok.resolve_photo("7680195684426927373", "natgeo", session=session)
    assert item.extra["image_count"] == 2


def test_resolve_photo_falls_back_to_page_json(monkeypatch):
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    url = tiktok.EMBED_URL.format(id="9")
    session = FakeSession({url: FakeResponse(text="<html>nothing</html>")})
    struct = {"imagePost": {"images": [{"imageURL": {"urlList": [_img(1)]}}]}, "author": {"uniqueId": "u"}}
    monkeypatch.setattr(tiktok, "_fetch_item_struct", lambda vid, user: struct)
    item = tiktok.resolve_photo("9", "u", session=session)
    assert item.kind is MediaKind.SLIDESHOW and len(item.assets) == 1


def test_resolve_photo_no_images_anywhere(monkeypatch):
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    url = tiktok.EMBED_URL.format(id="9")
    session = FakeSession({url: FakeResponse(text="<html>nothing</html>")})
    monkeypatch.setattr(tiktok, "_fetch_item_struct", lambda vid, user: {"video": {}})
    with pytest.raises(PlatformError) as err:
        tiktok.resolve_photo("9", session=session)
    assert err.value.code is ErrorCode.NO_MEDIA


def test_resolve_rejects_non_tiktok_links():
    with pytest.raises(PlatformError) as err:
        tiktok.resolve("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert err.value.code is ErrorCode.INVALID_LINK


def _slideshow(urls=("https://img/1", "https://img/2"), music="https://music/1"):
    assets = [MediaAsset(u, MediaKind.IMAGE, ext="jpg") for u in urls]
    if music:
        assets.append(MediaAsset(music, MediaKind.AUDIO, ext="m4a"))
    return MediaItem(id="768", url="https://www.tiktok.com/@nat.geo/photo/768", platform=Platform.TIKTOK,
                     kind=MediaKind.SLIDESHOW, assets=assets, extra={"username": "nat.geo"})


def _asset_routes():
    return {
        "https://img/1": FakeResponse(content=b"JPEG-ONE", content_type="image/jpeg"),
        "https://img/2": FakeResponse(content=b"WEBP-TWO", content_type="image/webp"),
        "https://music/1": FakeResponse(content=b"M4A-MUSIC", content_type="audio/mp4"),
    }


def test_download_slideshow_saves_images_and_music(tmp_path):
    session = FakeSession(_asset_routes())
    events = []
    paths = tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path)),
                                      session=session, progress=events.append)
    names = [os.path.basename(p) for p in paths]
    assert names == ["tiktok_nat.geo_768_01.jpg", "tiktok_nat.geo_768_02.webp", "tiktok_nat.geo_768_music.m4a"]
    assert (tmp_path / "tiktok_nat.geo_768_02.webp").read_bytes() == b"WEBP-TWO"
    assert events[-1].stage == "finished"
    assert {e.count for e in events} == {3}
    assert not [p for p in os.listdir(tmp_path) if p.endswith(".part")]


def test_download_slideshow_without_music_option(tmp_path):
    session = FakeSession(_asset_routes())
    opts = DownloadOptions(output_dir=str(tmp_path), include_slideshow_audio=False)
    paths = tiktok.download_slideshow(_slideshow(), opts, session=session)
    assert len(paths) == 2 and "https://music/1" not in session.calls


def test_download_slideshow_skips_existing_files(tmp_path):
    (tmp_path / "tiktok_nat.geo_768_01.jpg").write_bytes(b"already here")
    session = FakeSession(_asset_routes())
    paths = tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path)), session=session)
    assert "https://img/1" not in session.calls
    assert len(paths) == 3


def test_download_slideshow_reresolves_expired_urls(tmp_path, monkeypatch):
    routes = _asset_routes()
    routes["https://img/1"] = FakeResponse(status=403)
    routes["https://img/1-fresh"] = FakeResponse(content=b"FRESH", content_type="image/jpeg")
    session = FakeSession(routes)
    calls = []

    def fake_resolve(video_id, user, **kw):
        calls.append((video_id, user))
        return _slideshow(urls=("https://img/1-fresh", "https://img/2"))

    monkeypatch.setattr(tiktok, "resolve_photo", fake_resolve)
    paths = tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path)), session=session)
    assert calls == [("768", "nat.geo")]
    assert (tmp_path / "tiktok_nat.geo_768_01.jpg").read_bytes() == b"FRESH"
    assert len(paths) == 3


def test_download_slideshow_gives_up_after_one_refresh(tmp_path, monkeypatch):
    routes = _asset_routes()
    routes["https://img/1"] = FakeResponse(status=403)
    session = FakeSession(routes)
    monkeypatch.setattr(tiktok, "resolve_photo", lambda *a, **k: _slideshow())
    with pytest.raises(PlatformError) as err:
        tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path)), session=session)
    assert err.value.code is ErrorCode.FORBIDDEN


def test_download_slideshow_cancel_leaves_no_partial_files(tmp_path):
    ev = threading.Event()
    session = FakeSession(_asset_routes())

    def progress(p):
        ev.set()  # cancel as soon as the first bytes arrive

    with pytest.raises(DownloadCancelled):
        tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path)), session=session,
                                  cancel_event=ev, progress=progress)
    assert os.listdir(tmp_path) == []


def test_download_slideshow_audio_mode_requires_music(tmp_path):
    with pytest.raises(PlatformError) as err:
        tiktok.download_slideshow(_slideshow(music=None),
                                  DownloadOptions(output_dir=str(tmp_path), mode=MediaKind.AUDIO))
    assert err.value.code is ErrorCode.NO_MEDIA


def test_download_slideshow_audio_mode_converts_music(tmp_path, monkeypatch):
    seen = {}

    def fake_run(url, opts, **kw):
        seen["url"], seen["opts"] = url, opts
        return [str(tmp_path / "x_music.mp3")]

    monkeypatch.setattr(tiktok, "run_download", fake_run)
    tiktok.download_slideshow(_slideshow(), DownloadOptions(output_dir=str(tmp_path), mode=MediaKind.AUDIO))
    assert seen["url"] == "https://music/1"
    assert seen["opts"]["outtmpl"].endswith("tiktok_nat.geo_768_music.%(ext)s")
    assert seen["opts"]["postprocessors"][0]["preferredcodec"] == "mp3"


# --------------------------------------------------------------------------------------------
# Real network (run with --network). Links verified on 2026-09-27/28.
# --------------------------------------------------------------------------------------------

LIVE_VIDEO = "https://www.tiktok.com/@tiktok/video/7689568478570843422"
LIVE_PHOTO = "https://www.tiktok.com/@natgeo/photo/7680195684426927373"
LIVE_PHOTO_VIA_VIDEO_URL = "https://www.tiktok.com/@bbcnews/video/7689539430922620182"


@pytest.mark.network
@pytest.mark.smoke
def test_live_video_resolve():
    item = tiktok.resolve(LIVE_VIDEO)
    assert item.kind is MediaKind.VIDEO
    assert item.extra["watermark_free"] is True
    assert item.heights


@pytest.mark.network
def test_live_photo_resolve():
    item = tiktok.resolve(LIVE_PHOTO)
    assert item.kind is MediaKind.SLIDESHOW
    assert item.extra["image_count"] >= 1


@pytest.mark.network
def test_live_photo_post_behind_video_url():
    item = tiktok.resolve(LIVE_PHOTO_VIA_VIDEO_URL)
    assert item.kind is MediaKind.SLIDESHOW


@pytest.mark.network
def test_live_photo_download(tmp_path):
    item = tiktok.resolve(LIVE_PHOTO)
    paths = tiktok.download_slideshow(item, DownloadOptions(output_dir=str(tmp_path)))
    assert len(paths) == item.extra["image_count"] + 1
    assert all(os.path.getsize(p) > 10_000 for p in paths)
