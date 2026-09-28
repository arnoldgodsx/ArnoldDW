import json
import threading

import pytest

from arnold_dw.core.platforms import youtube_playlist as yp
from arnold_dw.core.platforms.errors import ErrorCode, PlatformError
from arnold_dw.core.platforms.models import Collection, MediaKind, Platform

PL = "PL590L5WQmH8fJ54F369BLDSqIwcs-TCfs"


@pytest.mark.parametrize(
    "url,expected",
    [
        (f"https://www.youtube.com/playlist?list={PL}", f"https://www.youtube.com/playlist?list={PL}"),
        (f"https://youtu.be/KIViy7L_lo8?list={PL}", f"https://www.youtube.com/playlist?list={PL}"),
        (f"https://www.youtube.com/watch?v=KIViy7L_lo8&list={PL}&index=2",
         f"https://www.youtube.com/playlist?list={PL}"),
        ("https://www.youtube.com/@NASA", "https://www.youtube.com/@NASA/videos"),
        ("youtube.com/@NASA/shorts", "https://www.youtube.com/@NASA/shorts"),
        ("https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ",
         "https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ/videos"),
    ],
)
def test_listing_url(url, expected):
    assert yp.listing_url(url) == expected


@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=KIViy7L_lo8", "https://vimeo.com/1", "metin"])
def test_listing_url_rejects_non_lists(url):
    with pytest.raises(PlatformError) as err:
        yp.listing_url(url)
    assert err.value.code is ErrorCode.INVALID_LINK


def _entry(i, **kw):
    base = {"_type": "url", "ie_key": "Youtube", "id": f"vid{i:08d}", "url": f"https://www.youtube.com/watch?v=vid{i:08d}",
            "title": f"Video {i}", "duration": 60 + i, "channel": "Kanal", "view_count": i,
            "thumbnails": [{"url": f"https://i.ytimg.com/vi/vid{i:08d}/hq720.jpg", "width": 1280, "height": 720}]}
    base.update(kw)
    return base


def test_entry_to_item():
    item = yp.entry_to_item(_entry(1))
    assert item.platform is Platform.YOUTUBE and item.kind is MediaKind.VIDEO
    assert (item.id, item.title, item.duration, item.uploader) == ("vid00000001", "Video 1", 61, "Kanal")
    assert item.thumbnail_url.endswith("hq720.jpg")
    assert item.extra == {"view_count": 1}
    json.dumps(item.to_dict())


def test_entry_to_item_fallbacks():
    item = yp.entry_to_item({"id": "abcdefghijk", "url": "abcdefghijk"}, default_uploader="NASA")
    assert item.url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert item.title == "abcdefghijk"
    assert item.uploader == "NASA"
    assert item.thumbnail_url == "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"


def test_entry_to_item_marks_shorts():
    item = yp.entry_to_item(_entry(2, url="https://www.youtube.com/shorts/vid00000002"))
    assert item.extra["shorts"] is True


@pytest.mark.parametrize(
    "entry",
    [
        _entry(3, title="[Private video]"),
        _entry(4, title="[Deleted video]"),
        _entry(5, availability="needs_auth"),
        {"_type": "playlist", "id": "UC1", "title": "NASA - Videos"},
        {"title": "no id"},
        None,
    ],
)
def test_entry_to_item_drops_unusable_entries(entry):
    assert yp.entry_to_item(entry) is None


class FakeYDL:
    closed = False

    def close(self):
        self.closed = True


def _patch_extract(monkeypatch, info):
    ydl = FakeYDL()
    seen = {}

    def fake_extract(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return ydl, info

    monkeypatch.setattr(yp, "extract", fake_extract)
    return seen, ydl


def _lazy(n, pulled):
    for i in range(1, n + 1):
        pulled.append(i)
        yield _entry(i)


def test_open_playlist_loads_first_page_only(monkeypatch):
    pulled = []
    info = {"_type": "playlist", "id": "UCLA", "title": "NASA - Videos", "channel": "NASA",
            "extractor_key": "YoutubeTab", "entries": _lazy(120, pulled)}
    seen, _ = _patch_extract(monkeypatch, info)
    col = yp.open_playlist("https://www.youtube.com/@NASA", page_size=50)
    assert seen["url"] == "https://www.youtube.com/@NASA/videos" and seen["kw"]["process"] is False
    assert isinstance(col, Collection)
    assert col.platform is Platform.YOUTUBE_CHANNEL
    assert len(col.entries) == 50 and len(pulled) == 50
    assert col.has_more and col.count is None and col.uploader == "NASA"
    col.load_more(50)
    col.load_more(50)
    assert len(col.entries) == 120 and not col.has_more


def test_open_playlist_small_list(monkeypatch):
    pulled = []
    info = {"_type": "playlist", "id": PL, "title": "Year In Search", "uploader": "Google", "playlist_count": 3,
            "entries": _lazy(3, pulled)}
    _patch_extract(monkeypatch, info)
    col = yp.open_playlist(f"https://www.youtube.com/playlist?list={PL}")
    assert col.platform is Platform.YOUTUBE_PLAYLIST and col.count == 3
    assert [e.title for e in col.entries] == ["Video 1", "Video 2", "Video 3"]
    assert not col.has_more
    json.dumps(col.to_dict())


def test_open_playlist_not_a_playlist(monkeypatch):
    _, ydl = _patch_extract(monkeypatch, {"_type": "video", "id": "x"})
    with pytest.raises(PlatformError) as err:
        yp.open_playlist(f"https://www.youtube.com/playlist?list={PL}")
    assert err.value.code is ErrorCode.NO_MEDIA
    assert ydl.closed


def test_iter_pages(monkeypatch):
    pulled = []
    _patch_extract(monkeypatch, {"_type": "playlist", "id": PL, "entries": _lazy(7, pulled)})
    pages = list(yp.iter_pages(f"https://www.youtube.com/playlist?list={PL}", page_size=3))
    assert [len(p) for p in pages] == [3, 3, 1]


def test_iter_pages_cancel(monkeypatch):
    pulled = []
    _patch_extract(monkeypatch, {"_type": "playlist", "id": PL, "entries": _lazy(100, pulled)})
    ev = threading.Event()
    pages = yp.iter_pages(f"https://www.youtube.com/playlist?list={PL}", page_size=10, cancel_event=ev)
    assert len(next(pages)) == 10
    ev.set()
    assert list(pages) == []
    assert len(pulled) == 10


# --------------------------------------------------------------------------------------------
# Real network (run with --network)
# --------------------------------------------------------------------------------------------


@pytest.mark.network
def test_live_channel_paging():
    col = yp.open_playlist("https://www.youtube.com/@NASA", page_size=50)
    assert len(col.entries) == 50 and col.has_more
    assert all(e.id and e.title and e.thumbnail_url for e in col.entries)
    assert len(col.load_more(50)) == 50


@pytest.mark.network
def test_live_playlist_from_watch_url():
    col = yp.open_playlist(f"https://www.youtube.com/watch?v=KIViy7L_lo8&list={PL}")
    assert col.count and len(col.entries) == min(col.count, 50)
    assert col.entries[0].duration
