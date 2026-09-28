"""Small HTTP helpers for engines that download files directly (not through yt-dlp)."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

import requests

from .errors import DownloadCancelled, to_platform_error
from .models import Progress
from .router import USER_AGENT

CHUNK_SIZE = 256 * 1024

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "video/mp4": "mp4",
}


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return session


def ext_from_content_type(content_type: str | None, default: str) -> str:
    if not content_type:
        return default
    return _CONTENT_TYPE_EXT.get(content_type.split(";")[0].strip().lower(), default)


def ext_from_url(url: str, default: str) -> str:
    match = re.search(r"\.([A-Za-z0-9]{2,4})(?:$|[?~#])", url.split("?")[0])
    if not match:
        return default
    ext = match.group(1).lower()
    return "jpg" if ext == "jpeg" else ext


def download_file(
    url: str,
    dest_without_ext: str,
    *,
    default_ext: str,
    session: requests.Session | None = None,
    headers: dict | None = None,
    cancel_event=None,
    progress: Callable[[Progress], None] | None = None,
    index: int = 1,
    count: int = 1,
    timeout: float = 30,
) -> str:
    """Stream ``url`` to ``dest_without_ext + '.' + ext`` and return the final path.

    The extension comes from the response Content-Type (falling back to ``default_ext``).
    Data is written to a ``.part`` file that is renamed only when complete, so a
    cancelled or failed download never leaves a truncated file behind.
    Raises ``requests.HTTPError`` for HTTP errors (callers may retry, e.g. on expired signed URLs).
    """
    http = session or new_session()
    if cancel_event is not None and cancel_event.is_set():
        raise DownloadCancelled()
    resp = http.get(url, headers=headers, stream=True, timeout=timeout)
    try:
        resp.raise_for_status()
        ext = ext_from_content_type(resp.headers.get("Content-Type"), default_ext)
        final_path = f"{dest_without_ext}.{ext}"
        part_path = final_path + ".part"
        total = int(resp.headers.get("Content-Length") or 0) or None
        done = 0
        started = time.monotonic()
        try:
            with open(part_path, "wb") as out:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled()
                    if not chunk:
                        continue
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        elapsed = max(time.monotonic() - started, 1e-6)
                        speed = done / elapsed
                        eta = (total - done) / speed if total and speed else None
                        progress(Progress("downloading", done, total, speed, eta, index, count,
                                          os.path.basename(final_path)))
            os.replace(part_path, final_path)
        except BaseException:
            try:
                os.remove(part_path)
            except OSError:
                pass
            raise
        return final_path
    except (DownloadCancelled, requests.HTTPError):
        raise
    except Exception as exc:
        raise to_platform_error(exc) from exc
    finally:
        resp.close()


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def safe_filename_part(value, fallback: str = "media", max_len: int = 100) -> str:
    """Make ``value`` safe to use inside a Windows file name."""
    text = _UNSAFE.sub("_", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" .")[:max_len].strip(" .")
    if not text or text.lower() in _RESERVED_NAMES:
        return fallback
    return text
