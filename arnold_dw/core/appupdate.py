"""Manifest based application updates without any UI dependencies."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FEED_URL = "https://github.com/arnoldgodsx/ArnoldDW/releases/latest/download/latest.json"
CHUNK_SIZE = 128 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
_VERSION = re.compile(
    r"^v?(?P<epoch>\d+!)?(?P<release>\d+(?:\.\d+)*)(?P<pre>[-_.]?(?:a|b|rc|alpha|beta|c|pre|preview)[-_.]?\d*)?"
    r"(?P<post>(?:-(?:\d+)|[-_.]?(?:post|rev|r)[-_.]?\d*))?(?P<dev>[-_.]?dev[-_.]?\d*)?"
    r"(?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?$",
    re.IGNORECASE,
)
_PRE = re.compile(r"^(?:[-_.]?)(a|b|rc|alpha|beta|c|pre|preview)(?:[-_.]?)(\d*)$", re.I)
_POST = re.compile(r"^(?:-(\d+)|[-_.]?(post|rev|r)[-_.]?(\d*))$", re.I)
_DEV = re.compile(r"^[-_.]?dev[-_.]?(\d*)$", re.I)


class UpdateError(Exception):
    """Base class for update feed and download failures."""


class UpdateNetworkError(UpdateError):
    """The update feed or asset could not be reached."""


class UpdateValidationError(UpdateError):
    """The manifest or downloaded asset did not pass validation."""


class UpdateCancelled(UpdateError):
    """The user cancelled an update download."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    published: str
    notes: str
    url: str
    sha256: str
    size: int


def _parse_version(value: str) -> tuple:
    """Parse the common PEP 440 public/local version forms for ordering."""
    match = _VERSION.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid version: {value!r}")
    epoch = int((match.group("epoch") or "0!").rstrip("!"))
    release = tuple(int(part) for part in match.group("release").split("."))
    while len(release) > 1 and release[-1] == 0:
        release = release[:-1]
    pre_text = match.group("pre")
    post_text = match.group("post")
    dev_text = match.group("dev")
    pre = None
    if pre_text:
        pre_match = _PRE.fullmatch(pre_text)
        label = pre_match.group(1).lower()
        pre = ({"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}.get(label, label), int(pre_match.group(2) or 0))
    post = None
    if post_text:
        post_match = _POST.fullmatch(post_text)
        post = int(post_match.group(1) or post_match.group(3) or 0)
    dev = None
    if dev_text:
        dev_match = _DEV.fullmatch(dev_text)
        dev = int(dev_match.group(1) or 0)
    local = match.group("local")

    # PEP 440 sorts dev-only releases before prereleases, then final releases;
    # post releases come after the final release. Local labels sort after public.
    if pre is None and post is None and dev is not None:
        pre_key = (0, "", 0)
    elif pre is None:
        pre_key = (2, "", 0)
    else:
        pre_key = (1, {"a": 0, "b": 1, "rc": 2}[pre[0]], pre[1])
    post_key = (1, post) if post is not None else (0, 0)
    dev_key = (0, dev) if dev is not None else (1, 0)
    local_key: tuple = () if local is None else tuple(
        (1, int(part)) if part.isdigit() else (0, part.lower())
        for part in re.split(r"[-_.]", local)
    )
    return epoch, release, pre_key, post_key, dev_key, (0, local_key) if local is None else (1, local_key)


def is_newer(candidate: str, current: str) -> bool:
    """Return whether candidate is newer using PEP 440 release ordering."""
    return _parse_version(candidate) > _parse_version(current)


def _http_url(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise UpdateValidationError(f"Manifest {field} must be a URL string")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise UpdateValidationError(f"Manifest {field} must use HTTP or HTTPS")
    return value


def _read_manifest(url: str, timeout: float) -> dict:
    _http_url(url, "feed URL")
    request = urllib.request.Request(url, headers={"User-Agent": "ArnoldDW-Updater/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_MANIFEST_BYTES + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateNetworkError(f"Could not fetch update manifest: {exc}") from exc
    if len(body) > MAX_MANIFEST_BYTES:
        raise UpdateValidationError("Update manifest is too large")
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateValidationError("Update manifest is not valid JSON") from exc
    if not isinstance(data, dict):
        raise UpdateValidationError("Update manifest must be a JSON object")
    return data


def check(current_version: str, feed_url: str = DEFAULT_FEED_URL, timeout: float = 10) -> UpdateInfo | None:
    """Return validated update metadata when the feed has a newer release."""
    try:
        current_key = _parse_version(current_version)
        data = _read_manifest(feed_url, timeout)
        version = data.get("version")
        if not isinstance(version, str):
            raise UpdateValidationError("Manifest version must be a string")
        candidate_key = _parse_version(version)
        if candidate_key <= current_key:
            return None
        assets = data.get("assets")
        setup = assets.get("setup") if isinstance(assets, dict) else None
        if not isinstance(setup, dict):
            raise UpdateValidationError("Manifest is missing the setup asset")
        url = _http_url(setup.get("url"), "setup URL")
        digest = setup.get("sha256")
        size = setup.get("size")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise UpdateValidationError("Manifest setup SHA-256 is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise UpdateValidationError("Manifest setup size must be a positive integer")
        published = data.get("published", "")
        notes = data.get("notes", "")
        if not isinstance(published, str) or not isinstance(notes, str):
            raise UpdateValidationError("Manifest published and notes fields must be strings")
        return UpdateInfo(version, published, notes, url, digest.lower(), size)
    except (ValueError, TypeError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateValidationError(str(exc)) from exc


def download(
    info: UpdateInfo,
    dest_dir: str | os.PathLike[str],
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download, bound, hash-check, then atomically publish the installer."""
    _http_url(info.url, "setup URL")
    if info.size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", info.sha256):
        raise UpdateValidationError("Update metadata is invalid")
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / f"ArnoldDW-{info.version}-setup.exe"
    part_path = final_path.with_name(final_path.name + ".part")
    digest = hashlib.sha256()
    total = 0
    limit = info.size + max(1, info.size // 20)
    request = urllib.request.Request(info.url, headers={"User-Agent": "ArnoldDW-Updater/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, part_path.open("wb") as output:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled("Update download cancelled")
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise UpdateValidationError("Downloaded setup exceeds the manifest size limit")
                digest.update(chunk)
                output.write(chunk)
                if progress_cb is not None:
                    progress_cb(total, info.size)
        if cancel_event is not None and cancel_event.is_set():
            raise UpdateCancelled("Update download cancelled")
        if total == 0:
            raise UpdateValidationError("Downloaded setup is empty")
        if digest.hexdigest() != info.sha256:
            raise UpdateValidationError("Downloaded setup SHA-256 does not match manifest")
        os.replace(part_path, final_path)
        return final_path
    except (UpdateError, UpdateNetworkError):
        part_path.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        part_path.unlink(missing_ok=True)
        raise UpdateNetworkError(f"Could not download update: {exc}") from exc


def launch_installer(path: str | os.PathLike[str]) -> subprocess.Popen:
    """Start Inno Setup silently; the caller should exit immediately after."""
    installer = Path(path)
    if not installer.is_file():
        raise FileNotFoundError(installer)
    return subprocess.Popen(
        [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTAPPLICATIONS"],
        close_fds=True,
    )
