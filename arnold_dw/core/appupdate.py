"""Manifest based application updates without any UI dependencies."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
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

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DEFAULT_FEED_URL = "https://github.com/arnoldgodsx/ArnoldDW/releases/latest/download/latest.json"
CHUNK_SIZE = 128 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
TRUSTED_KEYS = {
    "2026a": bytes.fromhex("e1b5e84a1a6ce55183bd9346fe0061ab48bef86fb273d2882269eb74d5aa447c"),
}
ASSET_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
logger = logging.getLogger(__name__)
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

    user_message = "Güncelleme doğrulanamadı"


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
    feed_host: str = ""


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


def _https_url(value: object, field: str, allowed_hosts: set[str] | frozenset[str] | None = None) -> str:
    if not isinstance(value, str):
        raise UpdateValidationError(f"Manifest {field} must be a URL string")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise UpdateValidationError(f"Manifest {field} must use HTTPS")
    if allowed_hosts is not None and parsed.hostname.lower() not in allowed_hosts:
        raise UpdateValidationError(f"Manifest {field} host is not allowed")
    return value


def _response_url(response, field: str, allowed_hosts: set[str] | frozenset[str]) -> str:
    final_url = getattr(response, "url", None)
    if not final_url and hasattr(response, "geturl"):
        final_url = response.geturl()
    return _https_url(final_url, f"final {field} URL", allowed_hosts)


def _canonical_json(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_manifest(wrapper: object) -> dict:
    """Verify a signed envelope before decoding or returning any payload fields."""
    try:
        if not isinstance(wrapper, dict) or set(wrapper) != {"payload", "signatures"}:
            raise ValueError("expected signed manifest envelope")
        payload_text = wrapper["payload"]
        signatures = wrapper["signatures"]
        if not isinstance(payload_text, str) or not isinstance(signatures, list) or not signatures:
            raise ValueError("manifest envelope fields are invalid")
        payload = base64.b64decode(payload_text, validate=True)
        seen = set()
        verified = False
        for entry in signatures:
            if not isinstance(entry, dict) or set(entry) != {"key_id", "sig"}:
                raise ValueError("manifest signature entry is invalid")
            key_id, signature_text = entry["key_id"], entry["sig"]
            if not isinstance(key_id, str) or key_id not in TRUSTED_KEYS:
                raise ValueError(f"unknown signing key id: {key_id!r}")
            if key_id in seen:
                raise ValueError(f"duplicate signing key id: {key_id}")
            seen.add(key_id)
            signature = base64.b64decode(signature_text, validate=True)
            try:
                Ed25519PublicKey.from_public_bytes(TRUSTED_KEYS[key_id]).verify(signature, payload)
                verified = True
            except InvalidSignature:
                continue
        if not verified:
            raise ValueError("manifest signature verification failed")
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict) or _canonical_json(data) != payload:
            raise ValueError("signed manifest payload is not canonical JSON")
        return data
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Update manifest signature/validation rejected: %s", exc)
        raise UpdateValidationError(f"{UpdateValidationError.user_message}: {exc}") from exc


def _read_manifest(url: str, timeout: float) -> tuple[dict, str]:
    feed_host = urllib.parse.urlparse(_https_url(url, "feed URL")).hostname.lower()
    request = urllib.request.Request(url, headers={"User-Agent": "ArnoldDW-Updater/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            _response_url(response, "feed", {feed_host})
            body = response.read(MAX_MANIFEST_BYTES + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateNetworkError(f"Could not fetch update manifest: {exc}") from exc
    if len(body) > MAX_MANIFEST_BYTES:
        raise UpdateValidationError("Update manifest is too large")
    try:
        wrapper = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateValidationError("Update manifest is not valid JSON") from exc
    return verify_manifest(wrapper), feed_host


def check(current_version: str, feed_url: str = DEFAULT_FEED_URL, timeout: float = 10) -> UpdateInfo | None:
    """Return validated update metadata when the feed has a newer release."""
    try:
        current_key = _parse_version(current_version)
        data, feed_host = _read_manifest(feed_url, timeout)
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
        allowed_hosts = ASSET_HOSTS | {feed_host}
        url = _https_url(setup.get("url"), "setup URL", allowed_hosts)
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
        return UpdateInfo(version, published, notes, url, digest.lower(), size, feed_host)
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
    allowed_hosts = ASSET_HOSTS | ({info.feed_host.lower()} if info.feed_host else set())
    _https_url(info.url, "setup URL", allowed_hosts)
    if info.size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", info.sha256):
        raise UpdateValidationError("Update metadata is invalid")
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / f"ArnoldDW-{info.version}-setup.exe"
    part_path = final_path.with_name(final_path.name + ".part")
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(info.url, headers={"User-Agent": "ArnoldDW-Updater/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, part_path.open("wb") as output:
            _response_url(response, "setup", allowed_hosts)
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled("Update download cancelled")
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > info.size:
                    raise UpdateValidationError("Downloaded setup exceeds the manifest size limit")
                digest.update(chunk)
                output.write(chunk)
                if progress_cb is not None:
                    progress_cb(total, info.size)
        if cancel_event is not None and cancel_event.is_set():
            raise UpdateCancelled("Update download cancelled")
        if total != info.size:
            raise UpdateValidationError("Downloaded setup size does not match manifest")
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
