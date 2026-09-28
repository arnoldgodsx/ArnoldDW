"""YouTube preview + download via yt-dlp. UI-independent: runs synchronously in the
caller's (worker) thread, reports progress through callbacks, cancels via threading.Event."""

import glob
import logging
import os
import re
from dataclasses import dataclass

import yt_dlp

from arnold_dw import config
from arnold_dw.core import filenames, formats, http
from arnold_dw.core.errors import DownloadCancelled
from arnold_dw.core.progress import CombinedProgress
from arnold_dw.core.runtime import binaries, selectors, ytdlp_updater

log = logging.getLogger(__name__)

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|live/)|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)


def is_youtube_url(text):
    return bool(YOUTUBE_RE.match(text or ""))


class YtDlpLogger:
    """Route yt-dlp's own output to our log file instead of a (missing) console."""

    def __init__(self, logger=log):
        self._log = logger

    def debug(self, msg):
        self._log.debug("yt-dlp: %s", msg)

    def info(self, msg):
        self._log.debug("yt-dlp: %s", msg)

    def warning(self, msg):
        self._log.warning("yt-dlp: %s", msg)

    def error(self, msg):
        self._log.error("yt-dlp: %s", msg)


@dataclass
class Preview:
    url: str
    info: dict
    thumbnail: object  # PIL.Image.Image | None


@dataclass(frozen=True)
class DownloadPrefs:
    """The user settings that shape a download (see config.Settings)."""

    video_mode: str = "compat"
    embed_metadata: bool = True
    embed_thumbnail: bool = True

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.video_mode, settings.embed_metadata, settings.embed_thumbnail)


def current_prefs():
    """Prefs as saved right now; the settings screen writes every change to disk at once."""
    return DownloadPrefs.from_settings(config.load_settings())


def build_preview_options(runtime=None):
    # The JS runtime matters here too: without it YouTube only lists 360p and below.
    runtime = binaries.ytdlp_runtime_options() if runtime is None else runtime
    return {
        **runtime,
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 2,
        "logger": YtDlpLogger(),
    }


def fetch_preview(url):
    """Metadata + thumbnail for a single video. Raises on extraction failure."""
    try:
        with yt_dlp.YoutubeDL(build_preview_options()) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        ytdlp_updater.report_failure(exc)
        raise
    thumbnail = http.fetch_image(info.get("thumbnail"), timeout=12)
    return Preview(url=url, info=info, thumbnail=thumbnail)


def build_download_options(fmt, quality, download_dir, prefs=None, runtime=None):
    """yt-dlp params for an MP4/MP3 download: tools found on this machine + format/tagging."""
    prefs = current_prefs() if prefs is None else prefs
    runtime = binaries.ytdlp_runtime_options() if runtime is None else runtime
    opts = {
        **runtime,
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
        "windowsfilenames": True,
        "outtmpl": filenames.youtube_outtmpl(download_dir, formats.filename_label(fmt, quality)),
        "logger": YtDlpLogger(),
    }
    # Tagging runs through ffmpeg; without it the post-processors would only fail.
    has_ffmpeg = "ffmpeg_location" in runtime
    embed = {
        "embed_metadata": prefs.embed_metadata and has_ffmpeg,
        "embed_thumbnail": prefs.embed_thumbnail and has_ffmpeg,
    }
    if fmt == formats.FORMAT_MP3:
        bitrate = formats.AUDIO_BITRATE.get(quality, "192")
        opts.update(selectors.audio_download_options("mp3", bitrate, **embed))
    else:
        height = formats.QUALITY_HEIGHTS.get(quality, formats.DEFAULT_MAX_HEIGHT)
        mode = prefs.video_mode if prefs.video_mode in config.VIDEO_MODES else "compat"
        opts.update(selectors.video_download_options(height, mode, **embed))
    return opts


@dataclass(frozen=True)
class DownloadResult:
    path: str              # the finished .mp4 / .mp3
    already_existed: bool  # True: the same file (same quality) was already there, nothing downloaded


def final_path(ydl, info, fmt):
    """Where the finished file of this (format-selected) download ends up.

    Merged streams get `merge_output_format`; a single fallback stream keeps
    its own container (e.g. .webm); MP3 is converted in place.
    """
    stem, _ext = os.path.splitext(ydl.prepare_filename(info))
    if fmt == formats.FORMAT_MP3:
        return stem + formats.output_extension(fmt)
    if info.get("requested_formats"):
        ext = ydl.params.get("merge_output_format") or info.get("ext")
    else:
        ext = info.get("ext")
    return f"{stem}.{ext}" if ext else stem + formats.output_extension(fmt)


def _reported_path(result):
    """The file yt-dlp says it wrote (after post-processing), when it tells us."""
    downloads = (result or {}).get("requested_downloads") or []
    path = downloads[-1].get("filepath") if downloads else None
    return path if path and os.path.exists(path) else None


def download(url, fmt, quality, download_dir, cancel_event,
             on_progress=None, on_processing=None):
    """Download `url` as MP4/MP3 into `download_dir`. Blocks until finished.

    on_progress(fraction | None, downloaded_bytes, speed_bps | None, eta_seconds | None)
        while bytes arrive, combined over all streams of the download (video +
        audio), so it never jumps back; fraction is None while the size is unknown.
    on_processing() once, when post-processing (merge / MP3 conversion) begins -
        from then on the download can no longer be cancelled.

    Returns a DownloadResult. If the target file already exists nothing is
    downloaded (already_existed=True). Raises DownloadCancelled if
    `cancel_event` gets set during the transfer (partial files of this
    download are removed), or the yt-dlp error.
    """
    os.makedirs(download_dir, exist_ok=True)
    partial_paths = set()
    processing = False
    combined = CombinedProgress()

    def progress_hook(d):
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Kullanıcı tarafından iptal edildi")
        status = d.get("status")
        if status not in ("downloading", "finished"):
            return
        key = d.get("filename") or d.get("tmpfilename") or ""
        if status == "downloading":
            for name in ("tmpfilename", "filename"):
                if d.get(name):
                    partial_paths.add(d[name])
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        result = combined.update(key, d.get("downloaded_bytes"), total, d.get("speed"), d.get("eta"),
                                 finished=status == "finished")
        if on_progress is not None and status == "downloading":
            on_progress(result.fraction, result.downloaded, result.speed, result.eta)

    def postprocessor_hook(d):
        nonlocal processing
        if d.get("status") == "started" and not processing:
            processing = True
            if on_processing is not None:
                on_processing()

    opts = build_download_options(fmt, quality, download_dir)
    opts["progress_hooks"] = [progress_hook]
    opts["postprocessor_hooks"] = [postprocessor_hook]

    log.info("Download start: %s fmt=%s quality=%s dir=%s", url, fmt, quality, download_dir)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if cancel_event.is_set():
                raise DownloadCancelled()
            path = final_path(ydl, info, fmt)
            if os.path.exists(path):
                log.info("Already downloaded: %s", path)
                return DownloadResult(path, already_existed=True)
            combined = CombinedProgress.for_info(info)
            result = ydl.process_ie_result(info, download=True)
            path = _reported_path(result) or path
    except DownloadCancelled:
        log.info("Download cancelled: %s", url)
        raise
    except Exception as exc:
        if cancel_event.is_set() and not processing:
            _remove_partial_files(partial_paths)
            log.info("Download cancelled: %s", url)
            raise DownloadCancelled() from exc
        ytdlp_updater.report_failure(exc)
        raise
    log.info("Download finished: %s -> %s", url, path)
    return DownloadResult(path, already_existed=False)


def _remove_partial_files(paths_seen):
    """Delete what a cancelled transfer left behind (.part, fragments, unmerged streams)."""
    for path in paths_seen:
        candidates = [path, f"{path}.ytdl", *glob.glob(glob.escape(path) + "-Frag*")]
        for candidate in candidates:
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
            except OSError:
                log.warning("Could not remove partial file %s", candidate, exc_info=True)
