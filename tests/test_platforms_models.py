import json
import threading

import pytest

from arnold_dw.core.platforms.errors import ErrorCode, PlatformError
from arnold_dw.core.platforms.models import (
    Collection,
    DownloadOptions,
    EntryPager,
    MediaAsset,
    MediaItem,
    MediaKind,
    Platform,
    Progress,
    result_from_dict,
)


def _item(**kw):
    base = dict(
        id="abc",
        url="https://www.youtube.com/watch?v=abc",
        title="Başlık",
        platform=Platform.YOUTUBE,
        kind=MediaKind.VIDEO,
        uploader="u",
        duration=12.5,
        thumbnail_url="https://img/1.jpg",
        heights=[1080, 720],
        has_audio=True,
        extractor="Youtube",
        assets=[MediaAsset("https://img/1.jpg", MediaKind.IMAGE, 1080, 1350, "jpg"),
                MediaAsset("https://a/m", MediaKind.AUDIO, ext="m4a")],
        extra={"username": "u", "image_count": 1},
    )
    base.update(kw)
    return MediaItem(**base)


def test_media_item_json_roundtrip():
    item = _item()
    data = json.loads(json.dumps(item.to_dict()))
    assert data["type"] == "media"
    assert data["platform"] == "youtube" and data["kind"] == "video"
    back = result_from_dict(data)
    assert back == item
    assert isinstance(back.platform, Platform) and isinstance(back.assets[1].kind, MediaKind)


def test_media_item_from_dict_is_tolerant():
    item = MediaItem.from_dict({"id": "x", "url": "u", "platform": "future_site", "kind": "hologram",
                                "unknown_field": 1, "heights": ["720"]})
    assert item.platform is Platform.GENERIC
    assert item.kind is MediaKind.VIDEO
    assert item.heights == [720]
    assert item.assets == [] and item.extra == {}


def test_max_height():
    assert _item().max_height == 1080
    assert _item(heights=[]).max_height == 0


def test_collection_roundtrip_drops_pager():
    pager = EntryPager(iter([]), lambda e: None)
    col = Collection(id="PL1", url="https://www.youtube.com/playlist?list=PL1", title="Liste",
                     platform=Platform.YOUTUBE_PLAYLIST, count=2, entries=[_item(), _item(id="def")],
                     extractor="YoutubeTab", _pager=pager)
    data = json.loads(json.dumps(col.to_dict()))
    assert data["type"] == "collection" and "_pager" not in data
    back = result_from_dict(data)
    assert isinstance(back, Collection)
    assert back.entries == col.entries
    assert back.title == "Liste" and back.platform is Platform.YOUTUBE_PLAYLIST
    assert back.has_more is False


def _converter(raw):
    if raw is None:
        return None
    return MediaItem(id=str(raw), url=f"https://e/{raw}", title=str(raw))


def test_entry_pager_pages_lazily():
    pulled = []

    def source():
        for i in range(7):
            pulled.append(i)
            yield i

    col = Collection(id="c", url="u", _pager=EntryPager(source(), _converter))
    assert pulled == []  # nothing fetched until asked
    assert [e.id for e in col.load_more(3)] == ["0", "1", "2"]
    assert pulled == [0, 1, 2]
    assert col.has_more
    col.load_more(3)
    assert col.has_more
    assert [e.id for e in col.load_more(3)] == ["6"]
    assert not col.has_more
    assert col.load_more(3) == []
    assert len(col.entries) == 7


def test_entry_pager_skips_unconvertible_entries():
    pager = EntryPager([1, None, 2, None, 3], _converter)
    assert [e.id for e in pager.next_page(2)] == ["1", "2"]
    assert [e.id for e in pager.next_page(5)] == ["3"]
    assert pager.exhausted


def test_entry_pager_honours_cancel():
    ev = threading.Event()
    ev.set()
    pager = EntryPager(range(10), _converter)
    assert pager.next_page(5, ev) == []
    assert not pager.exhausted


def test_entry_pager_error_mid_page_keeps_partial_results():
    def source():
        yield 1
        yield 2
        raise OSError("Connection reset by peer")

    pager = EntryPager(source(), _converter)
    assert [e.id for e in pager.next_page(5)] == ["1", "2"]
    assert pager.exhausted


def test_entry_pager_error_before_any_entry_raises_platform_error():
    def source():
        raise RuntimeError("HTTP Error 429: Too Many Requests")
        yield  # pragma: no cover

    pager = EntryPager(source(), _converter)
    with pytest.raises(PlatformError) as err:
        pager.next_page(5)
    assert err.value.code is ErrorCode.RATE_LIMITED


def test_entry_pager_close_releases_keepalive():
    class Holder:
        closed = False

        def close(self):
            self.closed = True

    holder = Holder()
    pager = EntryPager(range(3), _converter, keepalive=holder)
    pager.close()
    assert holder.closed and pager.exhausted


def test_download_options_roundtrip():
    opts = DownloadOptions(output_dir="C:/İndirilenler", mode=MediaKind.AUDIO, max_height=720,
                           audio_format="m4a", playlist_items="1,3")
    back = DownloadOptions.from_dict(json.loads(json.dumps(opts.to_dict())))
    assert back == opts
    assert DownloadOptions.from_dict({"output_dir": "x", "mode": "bogus"}).mode is MediaKind.VIDEO


def test_progress_fraction():
    assert Progress("downloading", 50, 200).fraction == 0.25
    assert Progress("downloading", 50, None).fraction == 0.0
    assert Progress("downloading", 500, 200).fraction == 1.0
    assert Progress("finished").fraction == 1.0
