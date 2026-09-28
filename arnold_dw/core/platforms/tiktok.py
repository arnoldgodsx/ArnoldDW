"""TikTok: videos (watermark-free), audio extracted from the video, and photo slideshows.

Videos go through yt-dlp. Its TikTok format list contains:
  * ``download`` - the "Download video" address (``download_addr``/``downloadAddr``):
    the file the app saves, with the bouncing TikTok logo + username **watermark**.
  * ``play`` / ``h264_*`` / ``bytevc1_*`` - playback addresses (``play_addr`` /
    ``bitrateInfo``): the clean stream the player uses, **no watermark**.
We never pick ``download`` unless nothing else exists, prefer H.264 over H.265
(bytevc1) for compatibility and never pick bytevc2 (unplayable).

Photo posts (``/photo/<id>``) are not supported by yt-dlp (the URL falls to the
generic extractor, and the ``/video/<id>`` form only yields the music track), so
they are read from TikTok's public embed page (``__FRONTITY_CONNECT_STATE__`` ->
``imagePostInfo.displayImages``), falling back to the item JSON of the regular
page through yt-dlp's TikTok extractor (which solves the anti-bot challenge).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

import requests
import yt_dlp

from . import _http
from ._ytdlp import (
    audio_postprocessors,
    base_options,
    check_cancel,
    download_options,
    extract,
    is_video_format,
    item_from_info,
    run_download,
    video_heights,
)
from .errors import ErrorCode, PlatformError, to_platform_error
from .models import DownloadOptions, MediaAsset, MediaItem, MediaKind, Platform, Progress
from .router import analyze_online, tiktok_url

log = logging.getLogger("arnold_dw.platforms.tiktok")

# Excludes the watermarked "download" address and the unplayable bytevc2 codec.
# ``?`` keeps formats where the field is missing (most formats have no format_note).
WATERMARK_FREE = "[format_id!=download][format_note!*=?watermark][vcodec!=?bytevc2]"

EMBED_URL = "https://www.tiktok.com/embed/v2/{id}"
_EMBED_STATE_RE = re.compile(r'<script[^>]*\bid="__FRONTITY_CONNECT_STATE__"[^>]*>(.*?)</script>', re.S)
_EMBED_ATTEMPTS = 3


def is_h264(fmt: dict) -> bool:
    return (fmt.get("vcodec") or "").lower().startswith(("h264", "avc"))


def is_watermark_free(fmt: dict) -> bool:
    return (
        is_video_format(fmt)
        and fmt.get("format_id") != "download"
        and "watermark" not in (fmt.get("format_note") or "").lower()
        and fmt.get("vcodec") != "bytevc2"
    )


def _user_from_url(url: str | None) -> str | None:
    match = re.search(r"tiktok\.com/@([\w.-]+)/", url or "")
    return match.group(1) if match else None


def _canonical(url: str, cancel_event=None):
    check_cancel(cancel_event)
    det = analyze_online(url)
    if det.platform is not Platform.TIKTOK:
        raise PlatformError(ErrorCode.INVALID_LINK, f"not a TikTok post: {url}")
    return det


# --------------------------------------------------------------------------
# Resolve
# --------------------------------------------------------------------------


def video_item_from_info(info: dict) -> MediaItem:
    item = item_from_info(info, Platform.TIKTOK)
    formats = info.get("formats") or []
    clean = video_heights(formats, is_watermark_free)
    # Downloads prefer H.264 (plays everywhere); TikTok's sharper rungs are often H.265-only,
    # so only offer the rungs we will actually deliver.
    clean_h264 = video_heights(formats, lambda f: is_watermark_free(f) and is_h264(f))
    item.heights = clean_h264 or clean or item.heights
    item.extra["watermark_free"] = bool(clean)
    for key, out in (("track", "music_title"), ("artist", "music_author"), ("uploader", "username")):
        if info.get(key):
            item.extra[out] = info[key]
    # yt-dlp uses the (often long, hashtag-heavy) caption as title; keep it on one line.
    item.title = re.sub(r"\s+", " ", item.title).strip() or item.id
    return item


def resolve(url: str, *, cancel_event=None) -> MediaItem:
    """Resolve a TikTok video/photo link (short links included). Blocking (network)."""
    det = _canonical(url, cancel_event)
    if det.subtype == "photo":
        return resolve_photo(det.media_id, _user_from_url(det.url), cancel_event=cancel_event)
    ydl, info = extract(det.url, cancel_event=cancel_event)
    ydl.close()
    item = video_item_from_info(info)
    if item.kind is not MediaKind.VIDEO:
        # A photo post opened through its /video/ URL: yt-dlp only sees the music track.
        return resolve_photo(det.media_id, _user_from_url(det.url) or item.extra.get("username"),
                             cancel_event=cancel_event)
    return item


def _fetch_embed_video_data(video_id: str, session: requests.Session, cancel_event=None) -> dict | None:
    """``videoData`` from the public embed page, or None when it is not available."""
    for attempt in range(_EMBED_ATTEMPTS):
        check_cancel(cancel_event)
        try:
            resp = session.get(EMBED_URL.format(id=video_id), timeout=15)
        except requests.RequestException as exc:
            if attempt == _EMBED_ATTEMPTS - 1:
                raise to_platform_error(exc) from exc
            time.sleep(0.8 * (attempt + 1))
            continue
        match = _EMBED_STATE_RE.search(resp.text) if resp.ok else None
        if match:
            try:
                state = json.loads(match.group(1))
            except ValueError:
                state = {}
            for key, page in ((state.get("source") or {}).get("data") or {}).items():
                if key.startswith("/embed/") and isinstance(page, dict):
                    return page.get("videoData") or None
            return None
        # Occasionally TikTok answers with an anti-bot interstitial; retry shortly.
        time.sleep(0.8 * (attempt + 1))
    return None


def _fetch_item_struct(video_id: str, user: str | None) -> dict | None:
    """Item JSON from the regular page via yt-dlp's TikTok extractor (private API, used as fallback)."""
    with yt_dlp.YoutubeDL(base_options()) as ydl:
        ie = ydl.get_info_extractor("TikTok")
        fetch = getattr(ie, "_extract_web_data_and_status", None)
        if fetch is None:
            log.warning("yt-dlp TikTok extractor has no _extract_web_data_and_status; fallback unavailable")
            return None
        try:
            data, status = fetch(tiktok_url(video_id, user), video_id)
        except Exception as exc:
            raise to_platform_error(exc) from exc
    if status in (10216, 10222):
        raise PlatformError(ErrorCode.PRIVATE, f"tiktok status {status}")
    if status == 10204:
        raise PlatformError(ErrorCode.GEO_BLOCKED, "tiktok status 10204")
    if status not in (0, -1) or not data:
        raise PlatformError(ErrorCode.NOT_FOUND, f"tiktok status {status}")
    return data


def _first(urls) -> str | None:
    if isinstance(urls, str):
        return urls or None
    for url in urls or []:
        if url:
            return url
    return None


def slideshow_from_embed(video_data: dict, video_id: str) -> MediaItem | None:
    images = ((video_data.get("imagePostInfo") or {}).get("displayImages")) or []
    assets = [
        MediaAsset(url, MediaKind.IMAGE, img.get("width"), img.get("height"), _http.ext_from_url(url, "jpg"))
        for img in images
        if (url := _first(img.get("urlList")))
    ]
    if not assets:
        return None
    info = video_data.get("itemInfos") or {}
    author = video_data.get("authorInfos") or {}
    music = video_data.get("musicInfos") or {}
    return _slideshow_item(
        video_id, assets, _first(music.get("playUrl")),
        caption=info.get("text"), user=author.get("uniqueId"), nickname=author.get("nickName"),
        music_title=music.get("musicName"), music_author=music.get("authorName"),
        cover=_first(info.get("covers")),
    )


def slideshow_from_item_struct(item: dict, video_id: str) -> MediaItem | None:
    images = ((item.get("imagePost") or {}).get("images")) or []
    assets = [
        MediaAsset(url, MediaKind.IMAGE, img.get("imageWidth"), img.get("imageHeight"),
                   _http.ext_from_url(url, "jpg"))
        for img in images
        if (url := _first((img.get("imageURL") or {}).get("urlList")))
    ]
    if not assets:
        return None
    author = item.get("author") or {}
    music = item.get("music") or {}
    video = item.get("video") or {}
    return _slideshow_item(
        video_id, assets, _first(music.get("playUrl")),
        caption=item.get("desc"), user=author.get("uniqueId"), nickname=author.get("nickname"),
        music_title=music.get("title"), music_author=music.get("authorName"),
        cover=video.get("cover") or video.get("originCover"),
    )


def _slideshow_item(video_id, assets, music_url, *, caption, user, nickname, music_title, music_author, cover):
    if music_url:
        assets = assets + [MediaAsset(music_url, MediaKind.AUDIO, ext=_http.ext_from_url(music_url, "m4a"))]
    extra = {"image_count": sum(a.kind is MediaKind.IMAGE for a in assets), "watermark_free": True}
    if user:
        extra["username"] = user
    if music_title:
        extra["music_title"] = music_title
    if music_author:
        extra["music_author"] = music_author
    title = re.sub(r"\s+", " ", caption or "").strip()
    return MediaItem(
        id=video_id,
        url=tiktok_url(video_id, user, photo=True),
        title=title or f"TikTok {video_id}",
        platform=Platform.TIKTOK,
        kind=MediaKind.SLIDESHOW,
        uploader=nickname or user,
        thumbnail_url=cover or assets[0].url,
        has_audio=bool(music_url),
        extractor="TikTokPhoto",
        assets=assets,
        extra=extra,
    )


def resolve_photo(video_id: str, user: str | None = None, *, cancel_event=None, session=None) -> MediaItem:
    """Resolve a photo (slideshow) post: images + music. Blocking (network)."""
    http = session or _http.new_session()
    video_data = _fetch_embed_video_data(video_id, http, cancel_event)
    if video_data:
        item = slideshow_from_embed(video_data, video_id)
        if item:
            return item
    log.info("embed page had no images for %s, falling back to page JSON", video_id)
    check_cancel(cancel_event)
    struct = _fetch_item_struct(video_id, user)
    item = slideshow_from_item_struct(struct or {}, video_id)
    if item is None:
        raise PlatformError(ErrorCode.NO_MEDIA, f"no images in tiktok post {video_id}")
    return item


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------


def _video_download_options(options: DownloadOptions) -> dict:
    opts = download_options(options, video_filter=WATERMARK_FREE, codec_first=True)
    if options.mode is MediaKind.AUDIO:
        # Take the sound from the (clean) video itself: TikTok's separate "audio" format is
        # the music track, which for licensed songs is not what the video sounds like.
        opts["format"] = f"b{WATERMARK_FREE}/b"
        opts["format_sort"] = ["vcodec:h264", "acodec:aac"]
        opts["postprocessors"] = audio_postprocessors(options.audio_format, options.audio_quality)
    return opts


def download(target: MediaItem | str, options: DownloadOptions, *, cancel_event=None, progress=None) -> list[str]:
    """Download a TikTok video (as MP4 or audio) or a photo post. Returns file paths. Blocking."""
    if isinstance(target, str):
        det = _canonical(target, cancel_event)
        if det.subtype == "photo":
            target = resolve_photo(det.media_id, _user_from_url(det.url), cancel_event=cancel_event)
        else:
            try:
                return _download_video(det.url, options, cancel_event, progress)
            except PlatformError as exc:
                if exc.code is not ErrorCode.NO_MEDIA:
                    raise
                target = resolve(det.url, cancel_event=cancel_event)  # photo post behind a /video/ link
    if target.kind is MediaKind.SLIDESHOW:
        return download_slideshow(target, options, cancel_event=cancel_event, progress=progress)
    return _download_video(target.url, options, cancel_event, progress)


def _download_video(url, options, cancel_event, progress) -> list[str]:
    paths = run_download(url, _video_download_options(options), cancel_event=cancel_event, progress=progress)
    if not paths:
        raise PlatformError(ErrorCode.NO_MEDIA, url)
    return paths


def download_slideshow(
    item: MediaItem, options: DownloadOptions, *, cancel_event=None, progress=None, session=None
) -> list[str]:
    """Save a photo post's images (``tiktok_<user>_<id>_01.jpg`` ...) and its music track.

    In AUDIO mode only the music is saved, converted to the requested format.
    Signed image URLs expire after a while; on HTTP 403/404/410 the post is
    resolved again once and the download retried.
    """
    os.makedirs(options.output_dir, exist_ok=True)
    user = _http.safe_filename_part(item.extra.get("username") or "tiktok", "tiktok", 40)
    base = os.path.join(options.output_dir, f"tiktok_{user}_{item.id}")
    image_indexes = [i for i, a in enumerate(item.assets) if a.kind is MediaKind.IMAGE]
    music = next((a for a in item.assets if a.kind is MediaKind.AUDIO), None)

    if options.mode is MediaKind.AUDIO:
        if music is None:
            raise PlatformError(ErrorCode.NO_MEDIA, f"slideshow {item.id} has no music")
        opts = download_options(options)
        opts["outtmpl"] = f"{base}_music.%(ext)s"
        return run_download(music.url, opts, cancel_event=cancel_event, progress=progress)

    if not image_indexes:
        raise PlatformError(ErrorCode.NO_MEDIA, f"slideshow {item.id} has no images")
    # (destination without extension, fallback extension, index into item.assets)
    jobs = [(f"{base}_{n:02d}", "jpg", idx) for n, idx in enumerate(image_indexes, start=1)]
    if music is not None and options.include_slideshow_audio:
        jobs.append((f"{base}_music", music.ext or "m4a", item.assets.index(music)))

    http = session or _http.new_session()
    headers = {"Referer": "https://www.tiktok.com/"}
    paths: list[str] = []
    current = item
    refreshed = False
    for n, (dest, default_ext, asset_index) in enumerate(jobs, start=1):
        existing = _existing(dest)
        if existing:
            paths.append(existing)
            continue
        while True:
            asset = current.assets[asset_index]
            try:
                paths.append(_http.download_file(
                    asset.url, dest, default_ext=default_ext, session=http, headers=headers,
                    cancel_event=cancel_event, progress=progress, index=n, count=len(jobs),
                ))
                break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if refreshed or status not in (403, 404, 410):
                    raise to_platform_error(exc) from exc
                log.info("tiktok asset URL rejected (%s), re-resolving %s", status, item.id)
                refreshed = True
                current = resolve_photo(item.id, item.extra.get("username"), cancel_event=cancel_event,
                                        session=http)
                if len(current.assets) != len(item.assets):
                    raise PlatformError(ErrorCode.NOT_FOUND, "tiktok post changed while downloading") from exc
    if progress is not None:
        progress(Progress("finished", index=len(jobs), count=len(jobs)))
    return paths


def _existing(dest_without_ext: str) -> str | None:
    folder, name = os.path.split(dest_without_ext)
    try:
        for entry in os.listdir(folder or "."):
            stem, ext = os.path.splitext(entry)
            if stem == name and ext and ext != ".part":
                path = os.path.join(folder, entry)
                if os.path.getsize(path) > 0:
                    return path
    except OSError:
        return None
    return None
