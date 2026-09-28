"""YouTube preview + download via yt-dlp. UI-independent: runs synchronously in the
caller's (worker) thread, reports progress through callbacks, cancels via threading.Event."""

import glob
import logging
import os
import re
from dataclasses import dataclass

import yt_dlp

from arnold_dw import paths
from arnold_dw.core import filenames, formats, http
from arnold_dw.core.errors import DownloadCancelled

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


def fetch_preview(url):
    """Metadata + thumbnail for a single video. Raises on extraction failure."""
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 2,
        "logger": YtDlpLogger(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    thumbnail = http.fetch_image(info.get("thumbnail"), timeout=12)
    return Preview(url=url, info=info, thumbnail=thumbnail)


def build_download_options(fmt, quality, download_dir):
    opts = {
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
        "windowsfilenames": True,
        "outtmpl": filenames.youtube_outtmpl(download_dir),
        "logger": YtDlpLogger(),
    }
    if os.path.isfile(paths.FFMPEG_PATH):
        opts["ffmpeg_location"] = paths.FFMPEG_PATH
    opts.update(formats.build_format_options(fmt, quality))
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
