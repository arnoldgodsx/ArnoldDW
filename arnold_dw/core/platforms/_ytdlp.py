"""Shared yt-dlp plumbing for the platform engines.

Format selectors here are intentionally simple (prefer H.264/AAC in MP4 for
compatibility); they will be unified with ``core/runtime/selectors.py`` in Phase 2.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

import yt_dlp

from .errors import DownloadCancelled, to_platform_error
from .models import DownloadOptions, MediaItem, MediaKind, Platform, Progress

log = logging.getLogger("arnold_dw.platforms")


class _YdlLogger:
    """Routes yt-dlp output to our log file instead of the console."""

    def debug(self, msg):
        log.debug(msg)

    def info(self, msg):
        log.debug(msg)

    def warning(self, msg):
        log.warning(msg)

    def error(self, msg):
        log.error(msg)


def base_options(ffmpeg_location: str | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "windowsfilenames": True,
        "socket_timeout": 15,
        "retries": 3,
        "fragment_retries": 3,
        "logger": _YdlLogger(),
    }
    if ffmpeg_location:
        opts["ffmpeg_location"] = ffmpeg_location
    return opts


def check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise DownloadCancelled()


def extract(url: str, *, process: bool = True, extra_opts: dict | None = None, cancel_event=None):
    """Run yt-dlp metadata extraction. Returns ``(ydl, info)``.

    Playlists are listed flat and lazily; the returned ``YoutubeDL`` must stay
    alive while a lazy ``info['entries']`` generator is consumed.
    """
    check_cancel(cancel_event)
    opts = base_options()
    opts.update({"skip_download": True, "extract_flat": "in_playlist", "lazy_playlist": True})
    if extra_opts:
        opts.update(extra_opts)
    ydl = yt_dlp.YoutubeDL(opts)
    try:
        info = ydl.extract_info(url, download=False, process=process)
    except Exception as exc:
        ydl.close()
        raise to_platform_error(exc) from exc
    check_cancel(cancel_event)
    if not info:
        ydl.close()
        raise to_platform_error(RuntimeError("no media found"))
    return ydl, info


# --------------------------------------------------------------------------
# info dict -> model
# --------------------------------------------------------------------------


def best_thumbnail(info: dict) -> str | None:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = [t for t in info.get("thumbnails") or [] if t.get("url")]
    if not thumbs:
        return None
    # yt-dlp orders thumbnails worst -> best; prefer an explicit preference when present.
    thumbs.sort(key=lambda t: (t.get("preference") or 0, (t.get("width") or 0) * (t.get("height") or 0)))
    return thumbs[-1]["url"]


def is_video_format(fmt: dict) -> bool:
    if fmt.get("vcodec") == "none" or fmt.get("video_ext") == "none":
        return False
    return bool(fmt.get("vcodec") or fmt.get("height") or fmt.get("width") or fmt.get("video_ext"))


def resolution_rung(fmt: dict) -> int | None:
    """Quality rung of a format as users know it ("1080p"): the shorter side of the frame.

    A portrait 1080x1920 TikTok is "1080p", same as a landscape 1920x1080 video.
    """
    width, height = fmt.get("width"), fmt.get("height")
    if width and height:
        return int(min(width, height))
    return int(height) if height else None


def video_heights(formats: list[dict], predicate: Callable[[dict], bool] | None = None) -> list[int]:
    """Distinct quality rungs (see ``resolution_rung``) offered by the video formats, best first."""
    rungs = {
        rung
        for f in formats
        if is_video_format(f) and (predicate is None or predicate(f)) and (rung := resolution_rung(f))
    }
    return sorted(rungs, reverse=True)


def media_kind(info: dict, default: MediaKind = MediaKind.VIDEO) -> MediaKind:
    formats = info.get("formats") or []
    if formats:
        if any(is_video_format(f) for f in formats):
            return MediaKind.VIDEO
        if all(f.get("vcodec") == "none" or f.get("video_ext") == "none" for f in formats):
            return MediaKind.AUDIO
    ext = (info.get("ext") or "").lower()
    if ext in ("jpg", "jpeg", "png", "webp", "gif"):
        return MediaKind.IMAGE
    if ext in ("mp3", "m4a", "aac", "opus", "ogg", "wav", "flac"):
        return MediaKind.AUDIO
    if info.get("vcodec") == "none":
        return MediaKind.AUDIO
    return default


def item_from_info(info: dict, platform: Platform, *, default_kind: MediaKind = MediaKind.VIDEO) -> MediaItem:
    formats = info.get("formats") or []
    kind = media_kind(info, default_kind)
    has_audio = True
    if formats:
        has_audio = any(f.get("acodec") != "none" for f in formats)
    elif info.get("acodec") == "none":
        has_audio = False
    url = info.get("webpage_url") or info.get("original_url") or info.get("url") or ""
    extra = {}
    for key in ("live_status", "availability", "view_count", "upload_date", "playlist_index"):
        if info.get(key) is not None:
            extra[key] = info[key]
    return MediaItem(
        id=str(info.get("id") or ""),
        url=url,
        title=info.get("title") or info.get("fulltitle") or str(info.get("id") or ""),
        platform=platform,
        kind=kind,
        uploader=info.get("uploader") or info.get("channel") or info.get("uploader_id"),
        duration=info.get("duration"),
        thumbnail_url=best_thumbnail(info),
        heights=video_heights(formats),
        has_audio=has_audio,
        extractor=info.get("extractor_key") or info.get("ie_key"),
        extra=extra,
    )


# --------------------------------------------------------------------------
# Format selection (simple; Phase 2 moves this to core/runtime/selectors.py)
# --------------------------------------------------------------------------

def video_format(video_filter: str = "") -> str:
    """Best video+audio (merged) or best progressive file; the ranking comes from ``format_sort``."""
    v = video_filter
    return f"bv*{v}+ba/b{v}/bv*+ba/b"


def format_sort(max_height: int | None = None, *, codec_first: bool = False) -> list[str]:
    """yt-dlp ``format_sort`` keys: resolution cap + H.264/AAC preference for compatibility.

    ``res:N`` ranks by the shorter frame side (so portrait videos are capped
    correctly) and falls back to the closest larger rung instead of failing.
    With ``codec_first`` an H.264 stream wins even over a sharper H.265/VP9/AV1
    one - used where the higher rungs are H.265 only (TikTok).
    """
    res = f"res:{max_height}" if max_height else "res"
    keys = [res, "vcodec:h264", "acodec:aac"]
    if codec_first:
        keys = ["vcodec:h264", res, "acodec:aac"]
    return keys


def audio_postprocessors(audio_format: str, audio_quality: str) -> list[dict]:
    codec = "m4a" if audio_format == "m4a" else "mp3"
    return [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": codec,
        "preferredquality": audio_quality if codec == "mp3" else "0",
    }]


_TITLE_LIMIT_RE = re.compile(r"%\(title\)\.(\d+)B")
WINDOWS_MAX_PATH = 259
# Room for " [<19-digit id>]" plus yt-dlp temp suffixes such as ".fhls-audio-128000-Audio.mp4.part-Frag12.part".
_NAME_OVERHEAD = 90


def fit_template(output_dir: str, template: str) -> str:
    """Shrink ``%(title).NB`` so the final path stays under Windows' 260-character limit.

    Long titles (tweets, TikTok captions) in a deep folder otherwise fail with
    "No such file or directory" on systems without long-path support.
    """
    budget = WINDOWS_MAX_PATH - len(os.path.abspath(output_dir)) - 1 - _NAME_OVERHEAD
    budget = max(budget, 24)
    return _TITLE_LIMIT_RE.sub(lambda m: f"%(title).{min(int(m.group(1)), budget)}B", template)


def download_options(
    options: DownloadOptions, *, video_filter: str = "", codec_first: bool = False
) -> dict[str, Any]:
    opts = base_options(options.ffmpeg_location)
    opts["outtmpl"] = os.path.join(options.output_dir, fit_template(options.output_dir, options.filename_template))
    if options.playlist_items:
        opts["noplaylist"] = False
        opts["playlist_items"] = options.playlist_items
    if options.mode == MediaKind.AUDIO:
        opts["format"] = f"ba/b{video_filter}/b"
        opts["format_sort"] = ["acodec:aac"]
        opts["postprocessors"] = audio_postprocessors(options.audio_format, options.audio_quality)
    else:
        opts["format"] = video_format(video_filter)
        opts["format_sort"] = format_sort(options.max_height, codec_first=codec_first)
        opts["merge_output_format"] = "mp4"
    return opts


# --------------------------------------------------------------------------
# Running a download
# --------------------------------------------------------------------------


def _collect_paths(info: dict | None) -> list[str]:
    if not info:
        return []
    paths: list[str] = []
    for entry in info.get("entries") or []:
        paths.extend(_collect_paths(entry))
    for rd in info.get("requested_downloads") or []:
        path = rd.get("filepath") or rd.get("filename")
        if path and path not in paths:
            paths.append(path)
    return paths


def _remove_quietly(path: str | None) -> None:
    if not path:
        return
    for candidate in (path, path + ".ytdl"):
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError:
            pass


# yt-dlp names the separate video/audio streams of a merged download "<name>.f<format_id>.<ext>".
_INTERMEDIATE_RE = re.compile(r"\.f[\w-]+\.\w+$")


def run_download(url: str, ydl_opts: dict, *, cancel_event=None, progress=None) -> list[str]:
    """Download with yt-dlp, reporting ``Progress`` and honouring ``cancel_event``.

    Returns the final file paths. On cancel or failure, ``.part`` files and
    not-yet-merged stream files of the interrupted item are removed (completed
    files are kept); cancel raises ``DownloadCancelled``, anything else ``PlatformError``.
    """
    check_cancel(cancel_event)
    leftovers: set[str] = set()

    def hook(d):
        if d.get("tmpfilename"):
            leftovers.add(d["tmpfilename"])
        if d.get("status") == "finished" and _INTERMEDIATE_RE.search(d.get("filename") or ""):
            leftovers.add(d["filename"])
        if cancel_event is not None and cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("cancelled by user")
        if progress is None:
            return
        info = d.get("info_dict") or {}
        index = info.get("playlist_autonumber") or info.get("playlist_index") or 1
        count = info.get("n_entries") or 1
        name = os.path.basename(d.get("filename") or "") or None
        if d.get("status") == "downloading":
            progress(Progress(
                "downloading",
                int(d.get("downloaded_bytes") or 0),
                d.get("total_bytes") or d.get("total_bytes_estimate"),
                d.get("speed"),
                d.get("eta"),
                index,
                count,
                name,
            ))
        elif d.get("status") == "finished":
            progress(Progress("processing", int(d.get("downloaded_bytes") or 0), d.get("total_bytes"),
                              index=index, count=count, filename=name))

    opts = dict(ydl_opts)
    opts["progress_hooks"] = [hook]
    try:
        os.makedirs(os.path.dirname(opts.get("outtmpl") or "") or ".", exist_ok=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        for path in leftovers:
            _remove_quietly(path)
        raise to_platform_error(exc) from exc
    paths = [p for p in _collect_paths(info) if os.path.exists(p)]
    if progress is not None:
        progress(Progress("finished", count=max(len(paths), 1), index=max(len(paths), 1)))
    return paths
