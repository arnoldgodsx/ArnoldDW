"""Platform runners: option building, YouTube result mapping, Instagram re-resolve + file collection."""

import threading

import pytest

from arnold_dw.core import formats, instagram, jobs, runners, youtube
from arnold_dw.core.jobs import DownloadJob


class FakeContext:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.reports = []
        self.processing_calls = 0

    def progress(self, **kw):
        self.reports.append(kw)

    def processing(self, stage="İşleniyor"):
        self.processing_calls += 1

    def check_cancelled(self):
        pass


@pytest.mark.parametrize("fmt, quality, label", [
    ("MP4", "720p", "720p"), ("MP4", "4K", "4K"), ("MP4", "bogus", "1080p"),
    ("MP3", "320 kbps", "320kbps"), ("MP3", "128 kbps", "128kbps"),
])
def test_filename_label_distinguishes_qualities(fmt, quality, label):
    assert formats.filename_label(fmt, quality) == label


def test_run_youtube_passes_options_and_maps_the_result(monkeypatch):
    seen = {}

    def fake_download(url, fmt, quality, folder, cancel_event, on_progress, on_processing):
        seen.update(url=url, fmt=fmt, quality=quality, folder=folder)
        on_progress(0.5, 100, 20, 5)
        on_processing()
        return youtube.DownloadResult(path="C:\\dl\\T [id] 720p.mp4", already_existed=True)

    monkeypatch.setattr(youtube, "download", fake_download)
    job = DownloadJob(platform=runners.PLATFORM_YOUTUBE, url="https://youtu.be/x", title="T",
                      download_dir="C:\\dl", options=runners.youtube_options("MP4", "720p"))
    ctx = FakeContext()
    result = runners.run_youtube(job, ctx)
    assert seen == {"url": "https://youtu.be/x", "fmt": "MP4", "quality": "720p", "folder": "C:\\dl"}
    assert ctx.reports[0]["fraction"] == 0.5 and ctx.processing_calls == 1
    assert result.files == ["C:\\dl\\T [id] 720p.mp4"] and result.already_existed


def _post_preview():
    media = [{"index": i, "is_video": False} for i in (1, 2, 3)]
    return instagram.PostPreview(loader=None, post="POST", media=media, thumbnails=[None] * 3)


def test_run_instagram_post_downloads_selected_items_and_collects_files(monkeypatch):
    calls = {}

    def fake_download_post(post, items, folder, cancel_event, on_progress, on_file=None):
        calls["items"] = [i["index"] for i in items]
        on_progress("item", 1, 2)
        on_file("a.jpg", True)
        on_file("b.jpg", False)

    monkeypatch.setattr(instagram, "download_post", fake_download_post)
    job = DownloadJob(platform=runners.PLATFORM_INSTAGRAM, url="u", title="t", download_dir="d",
                      options=runners.instagram_post_options("ABC", {3, 1}), context=_post_preview())
    ctx = FakeContext()
    result = runners.run_instagram(job, ctx)
    assert calls["items"] == [1, 3]
    assert result.files == ["a.jpg", "b.jpg"] and result.already_existed is False
    assert ctx.reports[0]["fraction"] == 0


def test_run_instagram_resolves_again_without_context_and_flags_existing_files(monkeypatch):
    resolved = []

    def fake_resolve(value):
        resolved.append(value)
        return _post_preview()

    monkeypatch.setattr(instagram, "resolve", fake_resolve)
    monkeypatch.setattr(instagram, "download_post",
                        lambda post, items, folder, cancel, progress, on_file=None: on_file("a.jpg", False))
    job = DownloadJob(platform=runners.PLATFORM_INSTAGRAM, url="u", title="t", download_dir="d",
                      options=runners.instagram_post_options("ABC", []))
    result = runners.run_instagram(job, FakeContext())
    assert resolved == [instagram.post_url("ABC")]
    assert result.files == ["a.jpg"] and result.already_existed is True


def test_run_instagram_profile(monkeypatch):
    preview = instagram.ProfilePreview(loader=None, profile="PROFILE", avatar=None)
    seen = {}

    def fake_download_profile(profile, categories, folder, cancel_event, on_progress, on_file=None,
                              *, browser=None):
        seen.update(profile=profile, categories=categories, browser=browser)

    monkeypatch.setattr(instagram, "download_profile", fake_download_profile)
    job = DownloadJob(platform=runners.PLATFORM_INSTAGRAM, url="u", title="t", download_dir="d",
                      options=runners.instagram_profile_options("user", ["posts", "reels"]), context=preview)
    result = runners.run_instagram(job, FakeContext())
    assert seen == {"profile": "PROFILE", "categories": ["posts", "reels"], "browser": None}
    assert result.files == [] and result.already_existed is False


def test_run_instagram_profile_passes_the_opted_in_browser(monkeypatch):
    preview = instagram.ProfilePreview(loader=None, profile="PROFILE", avatar=None)
    seen = {}

    def fake_download_profile(profile, categories, folder, cancel_event, on_progress, on_file=None,
                              *, browser=None):
        seen["browser"] = browser

    monkeypatch.setattr(instagram, "download_profile", fake_download_profile)
    job = DownloadJob(platform=runners.PLATFORM_INSTAGRAM, url="u", title="t", download_dir="d",
                      options=runners.instagram_profile_options("user", ["posts"], browser="firefox"),
                      context=preview)
    runners.run_instagram(job, FakeContext())
    assert seen["browser"] == "firefox"


def test_default_runners_cover_both_platforms():
    registry = runners.default_runners()
    assert set(registry) == {runners.PLATFORM_YOUTUBE, runners.PLATFORM_INSTAGRAM}
    assert all(isinstance(r, jobs.Runner) for r in registry.values())
