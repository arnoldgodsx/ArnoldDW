"""Instagram post/profile resolution and media download.

UI-independent: every function runs synchronously in the caller's worker
thread; long operations take a threading.Event for cancellation and report
progress through a callback.

Method selection (CX-3-T08 measurement, see hq/reports/CX-3-T08.md):
  * Reel/video -> yt-dlp, anonymous. Format selection reuses the shared
    ``core/platforms/_ytdlp`` helpers (short-side quality rungs, H.264/AAC
    preference for compatibility).
  * Photo / carousel -> Instaloader, default user agent. yt-dlp raises a
    "no video" error for these; that specific failure (and only that one)
    triggers the Instaloader path. No other yt-dlp error falls back.
  * No Googlebot user agent, no fixed GraphQL ``doc_id``: both were removed.
  * 429 / "Please wait a few minutes" / 401: no fallback chain - stop
    immediately and start a cooldown so a quick retry in the same session
    fails fast instead of hammering Instagram again.
  * Bulk profile listing (posts/reels) is unreliable anonymously and is only
    attempted with the user's own opted-in browser session
    (yt-dlp ``cookiesfrombrowser``). Without a session only the profile
    picture is attempted, and a private profile is never touched at all.
"""

import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import instaloader
import requests
import yt_dlp

from arnold_dw import paths
from arnold_dw.core import filenames, http
from arnold_dw.core.errors import (
    DownloadCancelled,
    InstagramCookieError,
    InstagramRateLimited,
    InstagramSessionRequired,
)
from arnold_dw.core.platforms import _ytdlp

log = logging.getLogger(__name__)

POST_URL_RE = re.compile(
    r"instagram\.com/(?P<kind>p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
INSTAGRAM_PROFILE_RE = re.compile(
    r"instagram\.com/([A-Za-z0-9._]+)",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"[A-Za-z0-9._]+")

REQUEST_TIMEOUT = 15
MEDIA_TIMEOUT = 30
_CHUNK = 256 * 1024

# Browsers yt-dlp can read a Chromium/Firefox cookie jar from (cookiesfrombrowser).
SUPPORTED_BROWSERS = ("firefox", "edge", "chrome", "brave")

# Instagram rate-limits per URL/endpoint, not with one shared "unblock" time (CX-3-T08); this is a
# conservative single cooldown covering the whole module so a quick retry always fails fast instead
# of sending another request.
DEFAULT_COOLDOWN_SECONDS = 5 * 60

# Profile download categories.
CATEGORY_POSTS = "posts"
CATEGORY_REELS = "reels"
CATEGORY_PROFILE_PIC = "profile_pic"

# Progress stages passed to on_progress(stage, index, total).
STAGE_POST_ITEM = "post_item"      # index/total within the selected post media
STAGE_PROFILE_PIC = "profile_pic"
STAGE_POST = "post"                # index = n-th profile post, total None
STAGE_REEL = "reel"                # index = n-th profile video, total None


def parse_input(value):
    """Classify user input: ("post", shortcode) or ("profile", username).

    Raises ValueError when it's neither a post link nor a valid username.
    """
    value = (value or "").strip()
    post_match = POST_URL_RE.search(value)
    if post_match:
        return "post", post_match.group("code")
    profile_match = INSTAGRAM_PROFILE_RE.search(value)
    username = profile_match.group(1) if profile_match else value
    username = username.strip().lstrip("@").strip("/")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Invalid Instagram username")
    return "profile", username


def _post_url(value, shortcode):
    """Rebuild a canonical post URL, keeping the original /p//reel//tv/ prefix when known."""
    match = POST_URL_RE.search(value or "")
    kind = match.group("kind").lower() if match else "p"
    if kind == "reels":
        kind = "reel"
    return f"https://www.instagram.com/{kind}/{shortcode}/"


def new_loader():
    """A plain, honestly-identified Instaloader session (no crawler UA, no login)."""
    return instaloader.Instaloader(
        sleep=False,
        max_connection_attempts=1,
        request_timeout=REQUEST_TIMEOUT,
        iphone_support=False,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )


def post_media(post):
    """Return original media URLs represented by an Instaloader Post."""
    media = []
    if post.typename == "GraphSidecar":
        for index, node in enumerate(post.get_sidecar_nodes(), start=1):
            media.append({
                "index": index,
                "is_video": bool(node.is_video),
                "engine": "instaloader",
                "url": node.video_url if node.is_video else node.display_url,
                "thumbnail_url": node.display_url,
            })
    else:
        media.append({
            "index": 1,
            "is_video": bool(post.is_video),
            "engine": "instaloader",
            "url": post.video_url if post.is_video else post.url,
            "thumbnail_url": post.url,
        })
    return media


@dataclass
class PostRef:
    """Stand-in for an Instaloader Post when a reel/video was resolved through yt-dlp instead."""

    shortcode: str
    owner_username: str


@dataclass
class ProfileInfo:
    """Public profile metadata (no Googlebot scrape, no fixed doc_id - see module docstring)."""

    username: str
    full_name: str = ""
    is_private: bool = False
    profile_pic_url: str = ""


@dataclass
class PostPreview:
    loader: object
    post: object
    media: list
    thumbnails: list  # PIL images (or None), parallel to `media`


@dataclass
class ProfilePreview:
    loader: object
    profile: object
    avatar: object  # PIL image or None


@dataclass
class ProfileCache:
    """Thread-safe LRU of resolved profiles (bounded: each entry holds a session + avatar)."""

    maxsize: int = 16
    _items: OrderedDict = field(default_factory=OrderedDict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, username):
        key = username.lower()
        with self._lock:
            entry = self._items.get(key)
            if entry is not None:
                self._items.move_to_end(key)
            return entry

    def put(self, username, entry):
        key = username.lower()
        with self._lock:
            self._items[key] = entry
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)

    def __len__(self):
        with self._lock:
            return len(self._items)


# --------------------------------------------------------------------------
# Rate limiting: no fallback chain, a simple cooldown blocks a quick retry.
# --------------------------------------------------------------------------

RATE_LIMIT_MARKERS = ("429", "too many requests", "please wait a few minutes")
_NO_VIDEO_MARKERS = ("no video in this post", "no video formats found", "no video could be found",
                      "requested format is not available", "does not contain any video")

_cooldown_lock = threading.Lock()
_cooldown_until = 0.0


def _cooldown_remaining():
    with _cooldown_lock:
        return max(0.0, _cooldown_until - time.monotonic())


def _start_cooldown(seconds=DEFAULT_COOLDOWN_SECONDS):
    global _cooldown_until
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)
    return seconds


def _ensure_not_cooling_down():
    remaining = _cooldown_remaining()
    if remaining > 0:
        raise InstagramRateLimited(remaining)


def _is_rate_limit_text(message):
    low = message.lower()
    return any(marker in low for marker in RATE_LIMIT_MARKERS)


def _is_no_video(exc):
    low = str(exc).lower()
    return any(marker in low for marker in _NO_VIDEO_MARKERS)


def _guard_rate_limit(exc):
    """Re-raise `exc`, upgraded to `InstagramRateLimited` (and a started cooldown) if it looks rate-limited.

    Always raises; never returns.
    """
    if isinstance(exc, (DownloadCancelled, InstagramRateLimited, InstagramCookieError, InstagramSessionRequired)):
        raise exc
    if isinstance(exc, instaloader.exceptions.TooManyRequestsException) or _is_rate_limit_text(str(exc)):
        seconds = _start_cooldown()
        raise InstagramRateLimited(seconds) from exc
    raise exc


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise DownloadCancelled()


def _ffmpeg_location():
    return paths.FFMPEG_PATH if os.path.isfile(paths.FFMPEG_PATH) else None


# --------------------------------------------------------------------------
# Resolve
# --------------------------------------------------------------------------


def resolve(value, cache=None):
    """Resolve a post link or a username/profile link to a preview (blocking, network)."""
    kind, key = parse_input(value)
    if kind == "post":
        return _resolve_post(value, key)
    return _resolve_profile(key, cache)


def _extract_ytdlp_info(url, cancel_event=None):
    _check_cancel(cancel_event)
    opts = _ytdlp.base_options()
    opts.update({"skip_download": True, "noplaylist": True})
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _post_preview_from_ytdlp(info, shortcode):
    # yt-dlp's Instagram extractor gives `channel` as the @handle, `uploader` as its display
    # name (differently capitalized) and `uploader_id` as a numeric account id.
    owner = info.get("channel") or info.get("uploader_id") or info.get("uploader") or "instagram"
    post_ref = PostRef(shortcode=shortcode, owner_username=str(owner))
    thumb_url = _ytdlp.best_thumbnail(info)
    canonical = info.get("webpage_url") or info.get("original_url") or _post_url("", shortcode)
    media = [{
        "index": 1,
        "is_video": True,
        "engine": "ytdlp",
        "url": canonical,
        "thumbnail_url": thumb_url,
    }]
    thumbnails = [http.fetch_image(thumb_url, timeout=REQUEST_TIMEOUT)]
    return PostPreview(loader=None, post=post_ref, media=media, thumbnails=thumbnails)


def _resolve_post_instaloader(shortcode):
    _ensure_not_cooling_down()
    loader = new_loader()
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        media = post_media(post)
    except Exception as exc:
        _guard_rate_limit(exc)
    thumbnails = [http.fetch_image(item["thumbnail_url"], timeout=REQUEST_TIMEOUT) for item in media]
    return PostPreview(loader, post, media, thumbnails)


def _resolve_post(value, shortcode):
    _ensure_not_cooling_down()
    url = _post_url(value, shortcode)
    try:
        info = _extract_ytdlp_info(url)
    except InstagramRateLimited:
        raise
    except Exception as exc:
        if _is_no_video(exc):
            return _resolve_post_instaloader(shortcode)
        _guard_rate_limit(exc)
    else:
        return _post_preview_from_ytdlp(info, shortcode)


def _resolve_profile(username, cache):
    if cache is not None:
        cached = cache.get(username)
        if cached is not None:
            return cached
    _ensure_not_cooling_down()
    loader = new_loader()
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
    except Exception as exc:
        _guard_rate_limit(exc)
    info = ProfileInfo(
        username=profile.username,
        full_name=profile.full_name or "",
        is_private=bool(profile.is_private),
        profile_pic_url=str(profile.profile_pic_url or ""),
    )
    # Never fetch anything for a private profile here: we have no (anonymous) way to know the
    # viewer follows it, and the product rule is to try nothing at all in that case.
    avatar = None
    if not info.is_private and info.profile_pic_url:
        avatar = http.fetch_image(info.profile_pic_url, timeout=REQUEST_TIMEOUT)
    preview = ProfilePreview(loader, info, avatar)
    if cache is not None:
        cache.put(username, preview)
    return preview


# --------------------------------------------------------------------------
# Download: single post / carousel
# --------------------------------------------------------------------------


def download_media(item, folder, basename, cancel_event):
    """Stream one media file to `folder`. Returns False if it already exists.

    Writes to a `.part` file first and renames on success, so an interrupted
    transfer never leaves a truncated file that later runs would skip.
    """
    _check_cancel(cancel_event)
    path = filenames.media_path(folder, basename, item["is_video"])
    if os.path.exists(path):
        return False

    part_path = path + ".part"
    try:
        with requests.get(item["url"], stream=True, timeout=MEDIA_TIMEOUT) as response:
            response.raise_for_status()
            with open(part_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=_CHUNK):
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled()
                    if chunk:
                        output.write(chunk)
        os.replace(part_path, path)
    except BaseException:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise
    return True


def _download_via_ytdlp(url, folder, basename, cancel_event):
    """Download a reel/video through yt-dlp (proper format selection + audio/video merge)."""
    _check_cancel(cancel_event)
    _ensure_not_cooling_down()
    safe_name = filenames.safe_filename_part(basename)
    for ext in ("mp4", "mkv", "webm"):
        if os.path.exists(os.path.join(folder, f"{safe_name}.{ext}")):
            return False

    opts = _ytdlp.base_options(_ffmpeg_location())
    opts["outtmpl"] = os.path.join(folder, f"{safe_name}.%(ext)s")
    opts["format"] = _ytdlp.video_format()
    opts["format_sort"] = _ytdlp.format_sort(codec_first=True)
    opts["merge_output_format"] = "mp4"
    opts["noplaylist"] = True

    def hook(d):
        if cancel_event is not None and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("cancelled by user")

    opts["progress_hooks"] = [hook]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadCancelled as exc:
        raise DownloadCancelled() from exc
    except Exception as exc:
        _guard_rate_limit(exc)
    return True


def _download_item(item, folder, basename, cancel_event):
    if item.get("engine") == "ytdlp":
        return _download_via_ytdlp(item["url"], folder, basename, cancel_event)
    return download_media(item, folder, basename, cancel_event)


def download_post(post, items, folder, cancel_event, on_progress=None):
    """Download the selected `items` (from post_media/resolve) of one post. Returns files written."""
    os.makedirs(folder, exist_ok=True)
    downloaded = 0
    for position, item in enumerate(items, start=1):
        if on_progress is not None:
            on_progress(STAGE_POST_ITEM, position, len(items))
        if not item.get("url"):
            continue
        basename = filenames.instagram_post_basename(post.owner_username, post.shortcode, item["index"])
        if _download_item(item, folder, basename, cancel_event):
            downloaded += 1
    return downloaded


# --------------------------------------------------------------------------
# Download: profile
# --------------------------------------------------------------------------


class _CapturingLogger(_ytdlp._YdlLogger):
    """Routes yt-dlp output to our log file like `_YdlLogger`, and also keeps warning/error text.

    Used to recover the specific cookie-decrypt failure message yt-dlp logs before it collapses
    the exception into a generic "failed to load cookies" error.
    """

    def __init__(self, sink):
        self._sink = sink

    def warning(self, msg):
        self._sink.append(str(msg))
        super().warning(msg)

    def error(self, msg):
        self._sink.append(str(msg))
        super().error(msg)


_BULK_CATEGORY_URLS = {
    CATEGORY_POSTS: "https://www.instagram.com/{username}/",
    CATEGORY_REELS: "https://www.instagram.com/{username}/reels/",
}
_BULK_CATEGORY_STAGE = {
    CATEGORY_POSTS: STAGE_POST,
    CATEGORY_REELS: STAGE_REEL,
}


def _guard_cookie_error(browser, captured_messages, exc):
    """Classify a failed cookies-from-browser attempt; re-raises (never returns)."""
    text = " ".join(captured_messages).lower() + " " + str(exc).lower()
    if "dpapi" in text or "app-bound" in text:
        raise InstagramCookieError(browser, str(exc)) from exc
    if "could not find" in text and "cookies database" in text:
        raise InstagramCookieError(browser, str(exc)) from exc
    if "cookie" in text and ("failed to load" in text or "decrypt" in text):
        raise InstagramCookieError(browser, str(exc)) from exc
    _guard_rate_limit(exc)


def _download_collection_via_ytdlp(url, folder, cancel_event, on_progress, browser, stage):
    _check_cancel(cancel_event)
    _ensure_not_cooling_down()
    captured = []
    opts = _ytdlp.base_options(_ffmpeg_location())
    opts["logger"] = _CapturingLogger(captured)
    opts["cookiesfrombrowser"] = (browser, None, None, None)
    opts["noplaylist"] = False
    opts["outtmpl"] = os.path.join(folder, "instagram_%(uploader_id,uploader)s_%(id)s.%(ext)s")
    opts["format"] = _ytdlp.video_format()
    opts["format_sort"] = _ytdlp.format_sort(codec_first=True)
    opts["merge_output_format"] = "mp4"

    seen = 0

    def hook(d):
        nonlocal seen
        if cancel_event is not None and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("cancelled by user")
        if d.get("status") == "finished":
            seen += 1
            if on_progress is not None:
                on_progress(stage, seen, None)

    opts["progress_hooks"] = [hook]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadCancelled as exc:
        raise DownloadCancelled() from exc
    except Exception as exc:
        _guard_cookie_error(browser, captured, exc)
    entries = (info or {}).get("entries")
    if entries is None:
        entries = [info] if info else []
    return len(entries)


def _download_profile_bulk(username, categories, folder, cancel_event, on_progress, browser):
    downloaded = 0
    for category in categories:
        url = _BULK_CATEGORY_URLS[category].format(username=username)
        downloaded += _download_collection_via_ytdlp(
            url, folder, cancel_event, on_progress, browser, _BULK_CATEGORY_STAGE[category]
        )
    return downloaded


def download_profile(profile, categories, folder, cancel_event, on_progress=None, *, browser=None):
    """Download the chosen categories of a profile. Returns files written.

    `profile_pic` is always attempted anonymously (public profiles only - see `resolve`).
    `posts`/`reels` need an opted-in `browser` (cookiesfrombrowser name); without one this
    raises `InstagramSessionRequired` rather than trying an anonymous listing (CX-3-T08: not
    reliable). A private profile never downloads anything.
    """
    if profile.is_private:
        raise Exception(f"Profile {profile.username}: private but not followed.")

    os.makedirs(folder, exist_ok=True)
    downloaded = 0

    def report(stage, index=None):
        if on_progress is not None:
            on_progress(stage, index, None)

    if CATEGORY_PROFILE_PIC in categories:
        report(STAGE_PROFILE_PIC)
        if profile.profile_pic_url:
            pic_item = {"is_video": False, "url": profile.profile_pic_url}
            if download_media(pic_item, folder, filenames.instagram_profile_pic_basename(profile.username),
                              cancel_event):
                downloaded += 1

    bulk_categories = [c for c in categories if c != CATEGORY_PROFILE_PIC]
    if bulk_categories:
        if not browser:
            raise InstagramSessionRequired()
        downloaded += _download_profile_bulk(profile.username, bulk_categories, folder, cancel_event,
                                             on_progress, browser)

    return downloaded
