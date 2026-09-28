"""Small HTTP helpers with hard response-size limits (thumbnails, profile pages)."""

import io
import logging

import requests
from PIL import Image

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PAGE_BYTES = 10 * 1024 * 1024
_CHUNK = 64 * 1024


class ResponseTooLarge(Exception):
    pass


def get_bytes(url, *, timeout, limit, headers=None):
    """GET `url` into memory, refusing bodies larger than `limit` bytes."""
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise ResponseTooLarge(f"{url}: Content-Length {declared} > {limit}")
        buf = bytearray()
        for chunk in response.iter_content(chunk_size=_CHUNK):
            buf.extend(chunk)
            if len(buf) > limit:
                raise ResponseTooLarge(f"{url}: body exceeds {limit} bytes")
        return bytes(buf), response


def get_text(url, *, timeout, limit=MAX_PAGE_BYTES, headers=None):
    body, response = get_bytes(url, timeout=timeout, limit=limit, headers=headers)
    return body.decode(response.encoding or "utf-8", errors="replace")


def fetch_image(url, timeout=15, limit=MAX_IMAGE_BYTES):
    """Download and decode an image as RGB; None on any failure (previews are optional)."""
    if not url:
        return None
    try:
        body, _ = get_bytes(url, timeout=timeout, limit=limit)
        return Image.open(io.BytesIO(body)).convert("RGB")
    except Exception:
        log.warning("Could not load image %s", url, exc_info=True)
        return None
