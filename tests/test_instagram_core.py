import os
import threading
from types import SimpleNamespace

import pytest
from fakes import FakeResponse

from arnold_dw.core import instagram
from arnold_dw.core.errors import DownloadCancelled


@pytest.mark.parametrize("value, expected", [
    ("https://www.instagram.com/p/CEY-sSQng08/", ("post", "CEY-sSQng08")),
    ("https://instagram.com/reel/DJf0_RmSd-T/?igsh=abc", ("post", "DJf0_RmSd-T")),
    ("instagram.com/reels/C49EgTpPR0P", ("post", "C49EgTpPR0P")),
    ("https://www.instagram.com/tv/B_x1/", ("post", "B_x1")),
    ("https://www.instagram.com/natgeo/", ("profile", "natgeo")),
    ("https://www.instagram.com/nat.geo_1?hl=tr", ("profile", "nat.geo_1")),
    ("@natgeo", ("profile", "natgeo")),
    ("  natgeo  ", ("profile", "natgeo")),
    ("natgeo/", ("profile", "natgeo")),
])
def test_parse_input(value, expected):
    assert instagram.parse_input(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "@", "bad name", "ünal", "https://example.com/x y", None])
def test_parse_input_rejects(value):
    with pytest.raises(ValueError):
        instagram.parse_input(value)


@pytest.mark.network
def test_live_public_profile_metadata():
    profile = instagram.fetch_public_profile(instagram.new_loader(), "natgeo")
    assert profile.username == "natgeo"


def _node(is_video, display, video=None):
    return SimpleNamespace(is_video=is_video, display_url=display, video_url=video)


def test_post_media_single_photo_and_video():
    photo = SimpleNamespace(typename="GraphImage", is_video=False, url="p.jpg", video_url=None)
    assert instagram.post_media(photo) == [
        {"index": 1, "is_video": False, "url": "p.jpg", "thumbnail_url": "p.jpg"},
    ]
    video = SimpleNamespace(typename="GraphVideo", is_video=True, url="thumb.jpg", video_url="v.mp4")
    assert instagram.post_media(video) == [
        {"index": 1, "is_video": True, "url": "v.mp4", "thumbnail_url": "thumb.jpg"},
    ]


def test_post_media_carousel():
    post = SimpleNamespace(
        typename="GraphSidecar",
        get_sidecar_nodes=lambda: [_node(False, "a.jpg"), _node(True, "b.jpg", "b.mp4")],
    )
    assert instagram.post_media(post) == [
        {"index": 1, "is_video": False, "url": "a.jpg", "thumbnail_url": "a.jpg"},
        {"index": 2, "is_video": True, "url": "b.mp4", "thumbnail_url": "b.jpg"},
    ]


def test_profile_cache_is_bounded_lru_and_case_insensitive():
    cache = instagram.ProfileCache(maxsize=2)
    cache.put("Alpha", "a")
    cache.put("beta", "b")
    assert cache.get("ALPHA") == "a"          # touch alpha -> beta becomes oldest
    cache.put("gamma", "g")
    assert len(cache) == 2
    assert cache.get("beta") is None
    assert cache.get("alpha") == "a"
    assert cache.get("gamma") == "g"


@pytest.fixture
def serve(monkeypatch):
    def install(response):
        monkeypatch.setattr(instagram.requests, "get", lambda url, **kw: response)
    return install


ITEM = {"index": 1, "is_video": True, "url": "https://cdn/x.mp4"}


def test_download_media_writes_file_atomically(tmp_path, serve):
    serve(FakeResponse([b"abc", b"def"]))
    assert instagram.download_media(ITEM, str(tmp_path), "clip", threading.Event()) is True
    assert (tmp_path / "clip.mp4").read_bytes() == b"abcdef"
    assert os.listdir(tmp_path) == ["clip.mp4"]


def test_download_media_skips_existing(tmp_path, serve):
    (tmp_path / "clip.mp4").write_bytes(b"old")
    serve(FakeResponse([b"new"]))
    assert instagram.download_media(ITEM, str(tmp_path), "clip", threading.Event()) is False
    assert (tmp_path / "clip.mp4").read_bytes() == b"old"


def test_network_failure_leaves_no_truncated_file(tmp_path, serve):
    serve(FakeResponse([b"abc", b"def", b"ghi"], fail_after=2))
    with pytest.raises(Exception, match="IncompleteRead"):
        instagram.download_media(ITEM, str(tmp_path), "clip", threading.Event())
    assert os.listdir(tmp_path) == []
    # ...so a retry really downloads instead of skipping a half file
    serve(FakeResponse([b"full"]))
    assert instagram.download_media(ITEM, str(tmp_path), "clip", threading.Event()) is True
    assert (tmp_path / "clip.mp4").read_bytes() == b"full"


def test_cancel_mid_stream_removes_partial_file(tmp_path, serve):
    cancel = threading.Event()

    class CancellingResponse(FakeResponse):
        def iter_content(self, chunk_size=1):
            yield b"abc"
            cancel.set()
            yield b"def"

    serve(CancellingResponse())
    with pytest.raises(DownloadCancelled):
        instagram.download_media(ITEM, str(tmp_path), "clip", cancel)
    assert os.listdir(tmp_path) == []


def test_download_media_already_cancelled(tmp_path, serve):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        instagram.download_media(ITEM, str(tmp_path), "clip", cancel)


def test_download_post_reports_progress_and_names_files(tmp_path, serve):
    serve(FakeResponse([b"x"]))
    post = SimpleNamespace(owner_username="user", shortcode="SC")
    items = [
        {"index": 1, "is_video": False, "url": "a"},
        {"index": 3, "is_video": True, "url": "b"},
    ]
    progress = []
    count = instagram.download_post(post, items, str(tmp_path / "dl"), threading.Event(),
                                    lambda *a: progress.append(a))
    assert count == 2
    assert sorted(os.listdir(tmp_path / "dl")) == ["instagram_user_SC_01.jpg", "instagram_user_SC_03.mp4"]
    assert progress == [(instagram.STAGE_POST_ITEM, 1, 2), (instagram.STAGE_POST_ITEM, 2, 2)]


def test_download_profile_categories_and_dedup(tmp_path, serve):
    serve(FakeResponse([b"x"]))

    def post(shortcode, is_video, typename):
        return SimpleNamespace(
            shortcode=shortcode, owner_username="u", is_video=is_video, typename=typename,
            url=f"{shortcode}.jpg", video_url=f"{shortcode}.mp4" if is_video else None,
        )

    posts = [post("P1", False, "GraphImage"), post("V1", True, "GraphVideo")]
    profile = SimpleNamespace(username="u", profile_pic_url="pic", get_posts=lambda: iter(posts))
    progress = []
    count = instagram.download_profile(
        profile, [instagram.CATEGORY_PROFILE_PIC, instagram.CATEGORY_POSTS, instagram.CATEGORY_REELS],
        str(tmp_path), threading.Event(), lambda *a: progress.append(a),
    )
    assert count == 3
    assert sorted(os.listdir(tmp_path)) == [
        "instagram_u_P1_01.jpg", "instagram_u_V1_01.mp4", "instagram_u_profil.jpg",
    ]
    assert progress == [
        (instagram.STAGE_PROFILE_PIC, None, None),
        (instagram.STAGE_POST, 1, None),
        (instagram.STAGE_REEL, 1, None),
    ]
