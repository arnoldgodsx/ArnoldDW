"""Platform-neutral data model shared by every platform engine.

Everything in here is plain data: ``to_dict()`` output is JSON-serializable and
``from_dict()`` accepts dicts written by older/newer versions (unknown keys are
ignored, missing keys fall back to defaults) so the queue and history screens
can persist these objects safely.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any


class Platform(StrEnum):
    YOUTUBE = "youtube"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    YOUTUBE_CHANNEL = "youtube_channel"
    INSTAGRAM_POST = "instagram_post"
    INSTAGRAM_PROFILE = "instagram_profile"
    TIKTOK = "tiktok"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class MediaKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    SLIDESHOW = "slideshow"


def _enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _known_kwargs(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls) if not f.name.startswith("_")}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class MediaAsset:
    """A directly downloadable file that belongs to an item (slideshow image, music track)."""

    url: str
    kind: MediaKind = MediaKind.IMAGE
    width: int | None = None
    height: int | None = None
    ext: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "kind": self.kind.value,
            "width": self.width,
            "height": self.height,
            "ext": self.ext,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MediaAsset:
        kwargs = _known_kwargs(cls, data)
        kwargs["kind"] = _enum(MediaKind, kwargs.get("kind"), MediaKind.IMAGE)
        return cls(**kwargs)


@dataclass
class MediaItem:
    """A single downloadable thing: a video, an audio track, an image or a photo slideshow."""

    id: str
    url: str
    title: str = ""
    platform: Platform = Platform.GENERIC
    kind: MediaKind = MediaKind.VIDEO
    uploader: str | None = None
    duration: float | None = None
    thumbnail_url: str | None = None
    # Quality rungs the source offers, best first, as the shorter frame side
    # (1080 for both 1920x1080 and a portrait 1080x1920). Empty when unknown.
    heights: list[int] = field(default_factory=list)
    has_audio: bool = True
    extractor: str | None = None
    assets: list[MediaAsset] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def max_height(self) -> int:
        return max(self.heights) if self.heights else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "media",
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "platform": self.platform.value,
            "kind": self.kind.value,
            "uploader": self.uploader,
            "duration": self.duration,
            "thumbnail_url": self.thumbnail_url,
            "heights": list(self.heights),
            "has_audio": self.has_audio,
            "extractor": self.extractor,
            "assets": [a.to_dict() for a in self.assets],
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict) -> MediaItem:
        kwargs = _known_kwargs(cls, data)
        kwargs["platform"] = _enum(Platform, kwargs.get("platform"), Platform.GENERIC)
        kwargs["kind"] = _enum(MediaKind, kwargs.get("kind"), MediaKind.VIDEO)
        kwargs["heights"] = [int(h) for h in kwargs.get("heights") or []]
        kwargs["assets"] = [MediaAsset.from_dict(a) for a in kwargs.get("assets") or []]
        kwargs["extra"] = dict(kwargs.get("extra") or {})
        return cls(**kwargs)


class EntryPager:
    """Pulls collection entries lazily, a page at a time.

    Wraps a (possibly network-backed) iterator of raw entries so that huge
    playlists never have to be listed in one go. Call ``next_page`` from a
    worker thread; it blocks while the next entries are fetched.
    """

    def __init__(self, raw_entries, convert: Callable[[Any], MediaItem | None], keepalive: Any = None):
        self._iter: Iterator = iter(raw_entries)
        self._convert = convert
        self._lock = threading.Lock()
        # Object the iterator depends on (e.g. the YoutubeDL instance behind a lazy generator).
        self._keepalive = keepalive
        self.exhausted = False

    def close(self) -> None:
        with self._lock:
            self.exhausted = True
            closer = getattr(self._keepalive, "close", None)
            self._keepalive = None
        if closer:
            closer()

    def next_page(self, size: int, cancel_event: threading.Event | None = None) -> list[MediaItem]:
        page: list[MediaItem] = []
        with self._lock:
            while not self.exhausted and len(page) < size:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    raw = next(self._iter)
                except StopIteration:
                    self.exhausted = True
                    break
                except Exception as exc:
                    # The source broke mid-listing (network, site change): keep what we
                    # already have, stop paging, and only raise when nothing was fetched.
                    self.exhausted = True
                    if page:
                        break
                    from .errors import to_platform_error

                    raise to_platform_error(exc) from exc
                item = self._convert(raw)
                if item is not None:
                    page.append(item)
        return page


@dataclass
class Collection:
    """A playlist, channel, profile or multi-video post.

    ``entries`` holds what has been loaded so far. When the source is paged,
    ``has_more`` is true and ``load_more()`` fetches the next page (the pager
    itself is runtime-only and is not serialized).
    """

    id: str
    url: str
    title: str = ""
    platform: Platform = Platform.GENERIC
    uploader: str | None = None
    thumbnail_url: str | None = None
    count: int | None = None
    entries: list[MediaItem] = field(default_factory=list)
    extractor: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _pager: EntryPager | None = field(default=None, repr=False, compare=False)

    @property
    def has_more(self) -> bool:
        return self._pager is not None and not self._pager.exhausted

    def load_more(self, size: int = 50, cancel_event: threading.Event | None = None) -> list[MediaItem]:
        """Fetch and append the next ``size`` entries. Blocking; call from a worker thread."""
        if self._pager is None:
            return []
        page = self._pager.next_page(size, cancel_event)
        self.entries.extend(page)
        return page

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "collection",
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "platform": self.platform.value,
            "uploader": self.uploader,
            "thumbnail_url": self.thumbnail_url,
            "count": self.count,
            "entries": [e.to_dict() for e in self.entries],
            "extractor": self.extractor,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Collection:
        kwargs = _known_kwargs(cls, data)
        kwargs["platform"] = _enum(Platform, kwargs.get("platform"), Platform.GENERIC)
        kwargs["entries"] = [MediaItem.from_dict(e) for e in kwargs.get("entries") or []]
        kwargs["extra"] = dict(kwargs.get("extra") or {})
        return cls(**kwargs)


ResolveResult = MediaItem | Collection


def result_from_dict(data: dict) -> ResolveResult:
    """Inverse of ``MediaItem.to_dict`` / ``Collection.to_dict``."""
    if data.get("type") == "collection":
        return Collection.from_dict(data)
    return MediaItem.from_dict(data)


@dataclass
class DownloadOptions:
    """What to download and where. Serializable so a queued job can be persisted."""

    output_dir: str
    mode: MediaKind = MediaKind.VIDEO  # VIDEO or AUDIO
    max_height: int | None = None  # quality rung cap (shorter frame side); None = best available
    audio_format: str = "mp3"  # "mp3" or "m4a"
    audio_quality: str = "192"  # kbps, only used for mp3
    filename_template: str = "%(title).150B [%(id)s].%(ext)s"
    ffmpeg_location: str | None = None
    include_slideshow_audio: bool = True
    playlist_items: str | None = None  # yt-dlp syntax, e.g. "1,3-5"

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "mode": self.mode.value,
            "max_height": self.max_height,
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "filename_template": self.filename_template,
            "ffmpeg_location": self.ffmpeg_location,
            "include_slideshow_audio": self.include_slideshow_audio,
            "playlist_items": self.playlist_items,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DownloadOptions:
        kwargs = _known_kwargs(cls, data)
        kwargs["mode"] = _enum(MediaKind, kwargs.get("mode"), MediaKind.VIDEO)
        return cls(**kwargs)


@dataclass
class Progress:
    """Progress report passed to ``progress`` callbacks (runtime only, not persisted)."""

    stage: str  # "downloading" | "processing" | "finished"
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed: float | None = None  # bytes/s
    eta: float | None = None  # seconds
    index: int = 1  # 1-based file index for multi-file downloads
    count: int = 1
    filename: str | None = None

    @property
    def fraction(self) -> float:
        if self.stage == "finished":
            return 1.0
        if not self.total_bytes:
            return 0.0
        return max(0.0, min(1.0, self.downloaded_bytes / self.total_bytes))


ProgressCallback = Callable[[Progress], None]
