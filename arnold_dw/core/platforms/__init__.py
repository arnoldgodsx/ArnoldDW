"""Platform engines: link detection, TikTok, generic yt-dlp sites and YouTube playlists.

UI-free. Every network function is synchronous and blocking - call it from a
worker thread. Cancellation uses a ``threading.Event``; progress is reported
through a callback receiving ``models.Progress``. Failures raise
``errors.PlatformError`` whose ``user_message`` is ready to show.

Typical flow::

    det = analyze(pasted_text)              # offline, instant
    result = resolve(pasted_text)           # worker thread: MediaItem or Collection
    files = download(result, DownloadOptions(output_dir=...), cancel_event=ev, progress=cb)
"""

from __future__ import annotations

from . import generic, tiktok, youtube_playlist
from .errors import DownloadCancelled, ErrorCode, PlatformError
from .models import (
    Collection,
    DownloadOptions,
    MediaAsset,
    MediaItem,
    MediaKind,
    Platform,
    Progress,
    ResolveResult,
    result_from_dict,
)
from .router import Detection, analyze, analyze_online, detect, extract_url, resolve_short_link, warm_up

__all__ = [
    "Collection", "Detection", "DownloadCancelled", "DownloadOptions", "ErrorCode", "MediaAsset", "MediaItem",
    "MediaKind", "Platform", "PlatformError", "Progress", "ResolveResult", "analyze", "analyze_online", "detect",
    "download", "extract_url", "resolve", "resolve_short_link", "result_from_dict", "warm_up",
]


def resolve(text: str, *, cancel_event=None) -> ResolveResult:
    """Resolve pasted text to a MediaItem or Collection. Blocking (network).

    Instagram links are handled by ``core.instagram`` and raise ``UNSUPPORTED`` here.
    Single YouTube videos resolve through yt-dlp like any generic site.
    """
    det = analyze_online(text)
    if det.platform in (Platform.YOUTUBE_PLAYLIST, Platform.YOUTUBE_CHANNEL):
        return youtube_playlist.open_playlist(det.url, cancel_event=cancel_event)
    if det.platform is Platform.TIKTOK:
        return tiktok.resolve(det.url, cancel_event=cancel_event)
    if det.platform in (Platform.YOUTUBE, Platform.GENERIC):
        return generic.resolve(det.url, cancel_event=cancel_event)
    if det.platform in (Platform.INSTAGRAM_POST, Platform.INSTAGRAM_PROFILE):
        raise PlatformError(ErrorCode.UNSUPPORTED, "instagram is handled by core.instagram")
    raise PlatformError(ErrorCode.INVALID_LINK if det.url is None else ErrorCode.UNSUPPORTED, repr(text))


def download(target: MediaItem | str, options: DownloadOptions, *, cancel_event=None, progress=None) -> list[str]:
    """Download a resolved MediaItem (or a link) with the matching engine. Returns file paths. Blocking."""
    platform = target.platform if isinstance(target, MediaItem) else analyze(target).platform
    if platform is Platform.TIKTOK:
        return tiktok.download(target, options, cancel_event=cancel_event, progress=progress)
    if platform in (Platform.YOUTUBE, Platform.GENERIC):
        return generic.download(target, options, cancel_event=cancel_event, progress=progress)
    raise PlatformError(ErrorCode.UNSUPPORTED, f"no download engine for {platform}")
