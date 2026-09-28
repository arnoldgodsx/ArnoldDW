import os
import threading
from types import SimpleNamespace

import instaloader
import pytest
from fakes import FakeResponse

from arnold_dw.core import instagram
from arnold_dw.core.errors import (
    DownloadCancelled,
    InstagramCookieError,
    InstagramRateLimited,
    InstagramSessionRequired,
)


@pytest.fixture(autouse=True)
def _reset_cooldown(monkeypatch):
    # The rate-limit cooldown is a module-level clock; keep tests from leaking into each other.
    monkeypatch.setattr(instagram, "_cooldown_until", 0.0)


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


def _node(is_video, display, video=None):
    return SimpleNamespace(is_video=is_video, display_url=display, video_url=video)


def test_post_media_single_photo_and_video():
    photo = SimpleNamespace(typename="GraphImage", is_video=False, url="p.jpg", video_url=None)
    assert instagram.post_media(photo) == [
        {"index": 1, "is_video": False, "engine": "instaloader", "url": "p.jpg", "thumbnail_url": "p.jpg"},
    ]
    video = SimpleNamespace(typename="GraphVideo", is_video=True, url="thumb.jpg", video_url="v.mp4")
    assert instagram.post_media(video) == [
        {"index": 1, "is_video": True, "engine": "instaloader", "url": "v.mp4", "thumbnail_url": "thumb.jpg"},
    ]


def test_post_media_carousel():
    post = SimpleNamespace(
        typename="GraphSidecar",
        get_sidecar_nodes=lambda: [_node(False, "a.jpg"), _node(True, "b.jpg", "b.mp4")],
    )
    assert instagram.post_media(post) == [
        {"index": 1, "is_video": False, "engine": "instaloader", "url": "a.jpg", "thumbnail_url": "a.jpg"},
        {"index": 2, "is_video": True, "engine": "instaloader", "url": "b.mp4", "thumbnail_url": "b.jpg"},
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


def test_download_profile_pic_only_needs_no_browser(tmp_path, serve):
    serve(FakeResponse([b"x"]))
    profile = instagram.ProfileInfo(username="u", profile_pic_url="pic")
    progress = []
    count = instagram.download_profile(
        profile, [instagram.CATEGORY_PROFILE_PIC], str(tmp_path), threading.Event(),
        lambda *a: progress.append(a),
    )
    assert count == 1
    assert os.listdir(tmp_path) == ["instagram_u_profil.jpg"]
    assert progress == [(instagram.STAGE_PROFILE_PIC, None, None)]


def test_download_profile_bulk_categories_require_a_browser_session(tmp_path):
    profile = instagram.ProfileInfo(username="u")
    with pytest.raises(InstagramSessionRequired):
        instagram.download_profile(profile, [instagram.CATEGORY_POSTS], str(tmp_path), threading.Event())


def test_download_profile_bulk_categories_use_ytdlp_per_category(tmp_path, monkeypatch):
    profile = instagram.ProfileInfo(username="u")
    calls = []

    def fake_collection(url, folder, cancel_event, on_progress, browser, stage):
        calls.append((url, browser, stage))
        return 2

    monkeypatch.setattr(instagram, "_download_collection_via_ytdlp", fake_collection)
    count = instagram.download_profile(
        profile, [instagram.CATEGORY_POSTS, instagram.CATEGORY_REELS], str(tmp_path), threading.Event(),
        browser="firefox",
    )
    assert count == 4
    assert calls == [
        ("https://www.instagram.com/u/", "firefox", instagram.STAGE_POST),
        ("https://www.instagram.com/u/reels/", "firefox", instagram.STAGE_REEL),
    ]


def test_download_profile_private_is_never_attempted(tmp_path):
    profile = instagram.ProfileInfo(username="u", is_private=True, profile_pic_url="pic")
    with pytest.raises(Exception, match="private"):
        instagram.download_profile(profile, [instagram.CATEGORY_PROFILE_PIC], str(tmp_path), threading.Event())
    assert os.listdir(tmp_path) == []


# --------------------------------------------------------------------------
# Method selection: reel/video -> yt-dlp, photo/carousel -> instaloader, no
# fallback (and no second method) on a rate-limit response.
# --------------------------------------------------------------------------


class _FakeYDL:
    def __init__(self, info=None, exc=None):
        self._info = info
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=False):
        if self._exc is not None:
            raise self._exc
        return self._info


def _patch_ytdlp(monkeypatch, *, info=None, exc=None):
    monkeypatch.setattr(instagram.yt_dlp, "YoutubeDL", lambda opts: _FakeYDL(info=info, exc=exc))


def _forbid_instaloader_post(monkeypatch):
    def boom(context, shortcode):
        raise AssertionError("instaloader must not be used when yt-dlp already resolved the reel")

    monkeypatch.setattr(instaloader.Post, "from_shortcode", staticmethod(boom))


REEL_URL = "https://www.instagram.com/reel/DJf0_RmSd-T/"


def test_resolve_reel_uses_ytdlp_and_not_instaloader(monkeypatch):
    _forbid_instaloader_post(monkeypatch)
    # `channel` is the @handle; `uploader`/`uploader_id` are a display name and a numeric id.
    info = {"id": "DJf0_RmSd-T", "channel": "insta360", "uploader": "Insta360", "uploader_id": "3434487056",
            "webpage_url": REEL_URL, "thumbnail": "t.jpg"}
    _patch_ytdlp(monkeypatch, info=info)

    preview = instagram.resolve(REEL_URL)
    assert isinstance(preview.post, instagram.PostRef)
    assert preview.post.owner_username == "insta360"
    assert preview.post.shortcode == "DJf0_RmSd-T"
    assert preview.media == [{
        "index": 1, "is_video": True, "engine": "ytdlp", "url": REEL_URL, "thumbnail_url": "t.jpg",
    }]


def test_resolve_photo_falls_back_to_instaloader_on_no_video(monkeypatch):
    _patch_ytdlp(monkeypatch, exc=Exception("ERROR: There is no video in this post"))
    photo = SimpleNamespace(typename="GraphImage", is_video=False, url="p.jpg", video_url=None,
                            shortcode="BOzn3kDJcp", owner_username="natgeo")
    monkeypatch.setattr(instaloader.Post, "from_shortcode", staticmethod(lambda context, sc: photo))

    preview = instagram.resolve("https://www.instagram.com/p/BOzn3kDJcp/")
    assert preview.post is photo
    assert preview.media[0]["engine"] == "instaloader"


def test_resolve_carousel_no_video_formats_falls_back(monkeypatch):
    _patch_ytdlp(monkeypatch, exc=Exception("ERROR: No video formats found!"))
    post = SimpleNamespace(
        typename="GraphSidecar", shortcode="CEYsSQng08", owner_username="x",
        get_sidecar_nodes=lambda: [_node(False, "a.jpg"), _node(True, "b.jpg", "b.mp4")],
    )
    monkeypatch.setattr(instaloader.Post, "from_shortcode", staticmethod(lambda context, sc: post))

    preview = instagram.resolve("https://www.instagram.com/p/CEYsSQng08/")
    assert len(preview.media) == 2
    assert all(item["engine"] == "instaloader" for item in preview.media)


def test_resolve_rate_limited_does_not_fall_back_to_instaloader(monkeypatch):
    _forbid_instaloader_post(monkeypatch)
    _patch_ytdlp(monkeypatch, exc=Exception("HTTP Error 429: Too Many Requests"))

    with pytest.raises(InstagramRateLimited):
        instagram.resolve("https://www.instagram.com/reel/ABC123/")
    assert instagram._cooldown_remaining() > 0


def test_cooldown_blocks_a_quick_retry_without_any_network_call(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("no network call should happen while cooling down")

    monkeypatch.setattr(instagram.yt_dlp, "YoutubeDL", boom)
    monkeypatch.setattr(instaloader.Post, "from_shortcode", staticmethod(boom))
    instagram._start_cooldown(120)

    with pytest.raises(InstagramRateLimited):
        instagram.resolve("https://www.instagram.com/reel/ABC123/")


def test_new_loader_user_agent_is_not_googlebot():
    loader = instagram.new_loader()
    assert "googlebot" not in loader.context.user_agent.lower()


# --------------------------------------------------------------------------
# Browser-cookie error classification (Chrome App-Bound/DPAPI vs. other browsers).
# --------------------------------------------------------------------------


def test_guard_cookie_error_classifies_chrome_dpapi_failure():
    captured = ["Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927"]
    with pytest.raises(InstagramCookieError) as excinfo:
        instagram._guard_cookie_error("chrome", captured, Exception("failed to load cookies"))
    assert excinfo.value.browser == "chrome"


def test_guard_cookie_error_classifies_missing_browser_database():
    exc = FileNotFoundError('could not find firefox cookies database in "C:/Users/x/AppData"')
    with pytest.raises(InstagramCookieError) as excinfo:
        instagram._guard_cookie_error("firefox", [], exc)
    assert excinfo.value.browser == "firefox"


def test_guard_cookie_error_leaves_rate_limit_alone():
    with pytest.raises(InstagramRateLimited):
        instagram._guard_cookie_error("edge", [], Exception("429 Too Many Requests"))


def test_guard_cookie_error_reraises_unrelated_errors():
    exc = Exception("some other extractor failure")
    with pytest.raises(Exception, match="some other extractor failure"):
        instagram._guard_cookie_error("brave", [], exc)


# --------------------------------------------------------------------------
# Profile resolve: anonymous metadata only, nothing fetched for a private
# profile (not even the picture).
# --------------------------------------------------------------------------


def _fake_profile(**overrides):
    attrs = {"username": "natgeo", "full_name": "Nat Geo", "is_private": False, "profile_pic_url": "pic.jpg"}
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def test_resolve_profile_public_fetches_avatar(monkeypatch):
    monkeypatch.setattr(instaloader.Profile, "from_username", staticmethod(lambda ctx, u: _fake_profile()))
    monkeypatch.setattr(instagram.http, "fetch_image", lambda url, timeout=15: f"image:{url}")

    preview = instagram.resolve("natgeo")
    assert isinstance(preview.profile, instagram.ProfileInfo)
    assert preview.profile.username == "natgeo"
    assert preview.profile.is_private is False
    assert preview.avatar == "image:pic.jpg"


def test_resolve_profile_private_fetches_nothing(monkeypatch):
    monkeypatch.setattr(instaloader.Profile, "from_username",
                        staticmethod(lambda ctx, u: _fake_profile(is_private=True)))

    def boom(url, timeout=15):
        raise AssertionError("must not fetch anything for a private profile")

    monkeypatch.setattr(instagram.http, "fetch_image", boom)
    preview = instagram.resolve("natgeo")
    assert preview.profile.is_private is True
    assert preview.avatar is None


def test_resolve_profile_rate_limited(monkeypatch):
    def boom(ctx, u):
        raise instaloader.exceptions.TooManyRequestsException("429 Too Many Requests")

    monkeypatch.setattr(instaloader.Profile, "from_username", staticmethod(boom))
    with pytest.raises(InstagramRateLimited):
        instagram.resolve("natgeo")
