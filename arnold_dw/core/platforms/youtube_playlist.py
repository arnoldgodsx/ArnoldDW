"""Fast, paged listing of YouTube playlists and channels.

Only metadata is fetched (yt-dlp ``extract_flat``): ~1-2 s for the first page
and ~1 s per further 50 entries, independent of playlist size. Downloading the
entries reuses the single-video flow (Phase 2).
"""

from __future__ import annotations

from ._ytdlp import best_thumbnail, extract
from .errors import ErrorCode, PlatformError
from .models import Collection, EntryPager, MediaItem, MediaKind, Platform
from .router import analyze

DEFAULT_PAGE_SIZE = 50

_UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "[unavailable video]"}


def listing_url(url: str) -> str:
    """URL to list for ``url``: channels default to their Videos tab, playlists to the canonical playlist page."""
    det = analyze(url)
    if det.platform is Platform.YOUTUBE_CHANNEL:
        return det.url if det.subtype else det.url + "/videos"
    if det.platform is Platform.YOUTUBE_PLAYLIST:
        return det.url
    if det.platform is Platform.YOUTUBE and det.playlist_url:
        return det.playlist_url
    raise PlatformError(ErrorCode.INVALID_LINK, f"not a YouTube playlist/channel: {url}")


def entry_to_item(entry: dict, default_uploader: str | None = None) -> MediaItem | None:
    """Flat playlist entry -> MediaItem. Private/deleted placeholders are dropped."""
    if not isinstance(entry, dict):
        return None
    if entry.get("_type") == "playlist":  # nested tab (e.g. channel root) - not a video
        return None
    video_id = entry.get("id")
    if not video_id:
        return None
    title = entry.get("title") or ""
    if title.strip().lower() in _UNAVAILABLE_TITLES:
        return None
    if entry.get("availability") in ("private", "needs_auth", "subscriber_only", "premium_only"):
        return None
    url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"
    extra = {}
    for key in ("live_status", "view_count"):
        if entry.get(key) is not None:
            extra[key] = entry[key]
    if "/shorts/" in url:
        extra["shorts"] = True
    return MediaItem(
        id=video_id,
        url=url,
        title=title or video_id,
        platform=Platform.YOUTUBE,
        kind=MediaKind.VIDEO,
        uploader=entry.get("channel") or entry.get("uploader") or default_uploader,
        duration=entry.get("duration"),
        thumbnail_url=best_thumbnail(entry) or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        extractor="Youtube",
        extra=extra,
    )


def open_playlist(url: str, *, page_size: int = DEFAULT_PAGE_SIZE, cancel_event=None) -> Collection:
    """List a playlist/channel: returns a Collection with the first page loaded.

    Blocking (network) - call from a worker thread. Use ``collection.load_more()``
    (also blocking) while ``collection.has_more`` is true.
    """
    target = listing_url(url)
    ydl, info = extract(target, process=False, cancel_event=cancel_event)
    if info.get("_type") not in ("playlist", "multi_video") or "entries" not in info:
        ydl.close()
        raise PlatformError(ErrorCode.NO_MEDIA, f"not a playlist: {target}")

    uploader = info.get("channel") or info.get("uploader")
    pager = EntryPager(info["entries"], lambda entry: entry_to_item(entry, uploader), keepalive=ydl)
    det = analyze(target)
    collection = Collection(
        id=str(info.get("id") or det.media_id or ""),
        url=target,
        title=info.get("title") or "",
        platform=det.platform if det.platform is not Platform.UNKNOWN else Platform.YOUTUBE_PLAYLIST,
        uploader=uploader,
        thumbnail_url=best_thumbnail(info),
        count=info.get("playlist_count"),
        extractor=info.get("extractor_key"),
        _pager=pager,
    )
    collection.load_more(page_size, cancel_event)
    return collection


def iter_pages(url: str, *, page_size: int = DEFAULT_PAGE_SIZE, cancel_event=None):
    """Yield the playlist/channel entries page by page (each page a list of MediaItem)."""
    collection = open_playlist(url, page_size=page_size, cancel_event=cancel_event)
    if collection.entries:
        yield list(collection.entries)
    while collection.has_more:
        if cancel_event is not None and cancel_event.is_set():
            return
        page = collection.load_more(page_size, cancel_event)
        if page:
            yield page
