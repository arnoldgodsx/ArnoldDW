"""Any site yt-dlp supports: resolve a link to a MediaItem/Collection and download it.

``SUPPORTED_SITES`` lists only the sites that were verified end-to-end with real
links (see the CL-3 T03 report). Other yt-dlp sites still go through this engine
but are not advertised.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from ._ytdlp import best_thumbnail, download_options, extract, item_from_info, run_download
from .errors import ErrorCode, PlatformError, to_platform_error
from .models import Collection, DownloadOptions, EntryPager, MediaItem, MediaKind, Platform
from .router import analyze

DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True)
class SiteInfo:
    name: str
    extractors: tuple[str, ...]
    example: str


# Verified 2026-09-27/28 from a TR connection with yt-dlp 2026.08.19 (resolve + download).
SUPPORTED_SITES: tuple[SiteInfo, ...] = (
    SiteInfo("X (Twitter)", ("Twitter",), "https://x.com/<kullanıcı>/status/<id>"),
    SiteInfo("Reddit", ("Reddit",), "https://www.reddit.com/r/<alt>/comments/<id>/<başlık>/"),
    SiteInfo("SoundCloud", ("Soundcloud", "SoundcloudSet", "SoundcloudUser", "SoundcloudPlaylist"),
             "https://soundcloud.com/<sanatçı>/<parça>"),
    SiteInfo("Twitch (klip)", ("TwitchClips",), "https://clips.twitch.tv/<klip>"),
    SiteInfo("Dailymotion", ("Dailymotion",), "https://www.dailymotion.com/video/<id>"),
)

_AUDIO_EXTRACTOR_PREFIXES = ("Soundcloud", "Bandcamp", "Mixcloud", "Audiomack")


def is_verified(extractor_key: str | None) -> bool:
    return bool(extractor_key) and any(extractor_key in site.extractors for site in SUPPORTED_SITES)


def _default_kind(extractor_key: str | None) -> MediaKind:
    if extractor_key and extractor_key.startswith(_AUDIO_EXTRACTOR_PREFIXES):
        return MediaKind.AUDIO
    return MediaKind.VIDEO


def _platform_of(url: str) -> Platform:
    platform = analyze(url).platform
    return platform if platform in (Platform.YOUTUBE, Platform.TIKTOK) else Platform.GENERIC


def _entry_converter(source_url: str, parent_extractor: str | None):
    counter = itertools.count(1)

    def convert(entry) -> MediaItem | None:
        index = next(counter)
        if not isinstance(entry, dict):
            return None
        extractor = entry.get("extractor_key") or entry.get("ie_key") or parent_extractor
        item = item_from_info(entry, _platform_of(entry.get("webpage_url") or entry.get("url") or ""),
                              default_kind=_default_kind(extractor))
        item.extractor = extractor
        if not entry.get("webpage_url") and entry.get("_type") != "url":
            # Fully-resolved entry without its own page (e.g. the 2nd video of a tweet):
            # download it through the parent link so it gets a proper title/metadata.
            item.extra["source_url"] = source_url
            item.extra["playlist_index"] = index
        if not item.id:
            item.id = f"{index}"
        return item

    return convert


def resolve(url: str, *, page_size: int = DEFAULT_PAGE_SIZE, cancel_event=None) -> MediaItem | Collection:
    """Resolve any yt-dlp supported link. Blocking (network); call from a worker thread."""
    det = analyze(url)
    target = det.url or url
    if det.platform is Platform.UNKNOWN and not det.url:
        raise PlatformError(ErrorCode.INVALID_LINK, repr(url))
    ydl, info = extract(target, process=False, cancel_event=cancel_event)

    if info.get("_type") in ("playlist", "multi_video"):
        return _collection(target, info, ydl, page_size, cancel_event)

    try:
        processed = ydl.process_ie_result(info, download=False)
    except Exception as exc:
        ydl.close()
        raise to_platform_error(exc) from exc
    if processed and processed.get("_type") in ("playlist", "multi_video"):
        return _collection(target, processed, ydl, page_size, cancel_event)
    ydl.close()
    if not processed:
        raise PlatformError(ErrorCode.NO_MEDIA, target)
    extractor = processed.get("extractor_key")
    item = item_from_info(processed, _platform_of(target), default_kind=_default_kind(extractor))
    if not item.url:
        item.url = target
    return item


def _collection(target: str, info: dict, ydl, page_size: int, cancel_event) -> Collection:
    extractor = info.get("extractor_key") or info.get("ie_key")
    pager = EntryPager(info.get("entries") or [], _entry_converter(target, extractor), keepalive=ydl)
    collection = Collection(
        id=str(info.get("id") or ""),
        url=info.get("webpage_url") or target,
        title=info.get("title") or "",
        platform=Platform.GENERIC,
        uploader=info.get("uploader") or info.get("channel"),
        thumbnail_url=best_thumbnail(info),
        count=info.get("playlist_count"),
        extractor=extractor,
        _pager=pager,
    )
    collection.load_more(page_size, cancel_event)
    if not collection.entries and not collection.has_more:
        raise PlatformError(ErrorCode.NO_MEDIA, target)
    return collection


def download(
    target: MediaItem | str,
    options: DownloadOptions,
    *,
    cancel_event=None,
    progress=None,
) -> list[str]:
    """Download a resolved item (or a URL) and return the created file paths. Blocking."""
    url = target if isinstance(target, str) else target.url
    extra = {} if isinstance(target, str) else target.extra
    if extra.get("source_url") and extra.get("playlist_index"):
        url = extra["source_url"]
        options = DownloadOptions.from_dict({**options.to_dict(), "playlist_items": str(extra["playlist_index"])})
    det = analyze(url)
    url = det.url or url
    if isinstance(target, MediaItem) and target.kind is MediaKind.AUDIO and options.mode is MediaKind.VIDEO:
        # Audio-only source (e.g. SoundCloud): "video" makes no sense, deliver audio instead.
        options = DownloadOptions.from_dict({**options.to_dict(), "mode": MediaKind.AUDIO.value})
    paths = run_download(url, download_options(options), cancel_event=cancel_event, progress=progress)
    if not paths:
        raise PlatformError(ErrorCode.NO_MEDIA, url)
    return paths
