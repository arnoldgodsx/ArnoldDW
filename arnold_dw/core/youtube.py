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
        "outtmpl": filenames.youtube_outtmpl(download_dir),
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


def download(url, fmt, quality, download_dir, cancel_event,
             on_progress=None, on_processing=None):
    """Download `url` as MP4/MP3 into `download_dir`. Blocks until finished.

    on_progress(fraction | None, downloaded_bytes, speed_bps | None, eta_seconds | None)
        while bytes arrive; fraction is None when the total size is unknown.
    on_processing() once, when post-processing (merge / MP3 conversion) begins -
        from then on the download can no longer be cancelled.

    Raises DownloadCancelled if `cancel_event` gets set during the transfer
    (partial files of this download are removed), or the yt-dlp error.
    """
    os.makedirs(download_dir, exist_ok=True)
    partial_paths = set()
    processing = False

    def progress_hook(d):
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Kullanıcı tarafından iptal edildi")
        if d.get("status") != "downloading":
            return
        for key in ("tmpfilename", "filename"):
            if d.get(key):
                partial_paths.add(d[key])
        if on_progress is not None:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            fraction = min(downloaded / total, 1.0) if total else None
            on_progress(fraction, downloaded, d.get("speed"), d.get("eta"))

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
            ydl.download([url])
    except Exception as exc:
        if cancel_event.is_set() and not processing:
            _remove_partial_files(partial_paths)
            log.info("Download cancelled: %s", url)
            raise DownloadCancelled() from exc
        ytdlp_updater.report_failure(exc)
        raise
    log.info("Download finished: %s", url)


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
