"""Runtime components (ffmpeg, Deno) downloaded on first launch instead of shipping in the installer.

The installer stays small; the first start shows a setup screen that calls :func:`install`
for every component :func:`missing` reports. Each component is pinned: every extracted
file must match its SHA-256 below, whichever source served it, so a mirror or a repacked
archive cannot change what runs.

Sources are tried in order:

1. A compact ``.tar.xz`` pack on this project's ``runtime-binaries`` release (only the files
   the app needs, xz-compressed; built by ``tools/build_runtime_packs.py``).
2. The original upstream archive (BtbN FFmpeg build / Deno release ZIP).
3. This project's mirror of that upstream archive (upstream FFmpeg autobuilds are pruned).

Layout: ``%LOCALAPPDATA%\\Arnold DW\\runtime\\<component>\\`` holds the files plus a
``component.json`` marker written last; a folder without a matching marker is incomplete.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
import threading
import time
import urllib.parse
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import _env

log = logging.getLogger(__name__)

RELEASE_BASE_URL = "https://github.com/arnoldgodsx/ArnoldDW/releases/download/runtime-binaries/"
ALLOWED_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
MARKER = "component.json"
CHUNK_SIZE = 256 * 1024
TIMEOUT = 30


@dataclass(frozen=True)
class Source:
    url: str
    kind: str  # "tar.xz" (our pack) or "zip" (upstream archive)
    max_bytes: int
    sha256: str | None = None  # whole-archive hash, when known (upstream archives)


@dataclass(frozen=True)
class Component:
    name: str
    title: str
    version: str
    files: dict[str, str]  # file name -> SHA-256 of the extracted file
    sources: tuple[Source, ...] = field(default=())
    description: str = ""


FFMPEG_VERSION = "9.0.2-27-g7e93014c5b"
FFMPEG_UPSTREAM = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-12-13-12/"
    "ffmpeg-n9.0.2-27-g7e93014c5b-win64-lgpl-shared-9.0.zip"
)
DENO_VERSION = "2.9.7"
DENO_UPSTREAM = "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip"


def pack_name(name: str, version: str) -> str:
    return f"arnolddw-{name}-{version}-win64.tar.xz"


def _mirror(url: str) -> str:
    return RELEASE_BASE_URL + PurePosixPath(urllib.parse.urlparse(url).path).name


FFMPEG = Component(
    name="ffmpeg",
    title="FFmpeg",
    version=FFMPEG_VERSION,
    description="Video ve sesi birleştirir, MP3'e dönüştürür",
    files={
        "ffmpeg.exe": "1f1334bab3fd4c8086b01dd1f618f2a3a453dfa39429b3a65a13b40502a194e3",
        "ffprobe.exe": "19cfb4211cc00c19591058ab06cd171eeec1dadc5296207e6f6d3414232380a5",
        "avcodec-63.dll": "501c1abd17650647ac829f72c5aa24379eb80e47c001163900da64cec36d68c6",
        "avdevice-63.dll": "33cd7781840597b09b68acb2d75491571ce238f4fcb83465942e6989df12374f",
        "avfilter-12.dll": "3541c6d1af33ae7919dfe945ed5e81fffd50741d948e535d9f0013935fc26d75",
        "avformat-63.dll": "4a598e944123550f3b4f09f5635dd6cf7b2c8b083ac21e2192e1a6290077ebef",
        "avutil-61.dll": "bf15dba19fcc23ba4a79faabae11705e8db0e8647a2003d7efdb0075fa9536c2",
        "swresample-7.dll": "6f1033a18a11358d6665bf80d07b57ff63efe8529e5cc8e73d49b07ddfc3fbe7",
        "swscale-10.dll": "fb7562f214f93743962bbb7879577b11bc8b52a589027fd220e14237b7d0c133",
    },
    sources=(
        Source(RELEASE_BASE_URL + pack_name("ffmpeg", FFMPEG_VERSION), "tar.xz", 80_000_000),
        Source(FFMPEG_UPSTREAM, "zip", 120_000_000,
               "de3f3b16b3dbf2038a56878aa35795f48bd220f01479697e008470773cecba5b"),
        Source(_mirror(FFMPEG_UPSTREAM), "zip", 120_000_000,
               "de3f3b16b3dbf2038a56878aa35795f48bd220f01479697e008470773cecba5b"),
    ),
)

DENO = Component(
    name="deno",
    title="Deno",
    version=DENO_VERSION,
    description="YouTube'da tüm kaliteleri açar",
    files={"deno.exe": "e020f3e232bd16e33768dee528e5983349c962952051ced0a5d58ad42f5d9b33"},
    sources=(
        Source(RELEASE_BASE_URL + pack_name("deno", DENO_VERSION), "tar.xz", 60_000_000),
        Source(DENO_UPSTREAM, "zip", 60_000_000,
               "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238"),
        Source(_mirror(DENO_UPSTREAM), "zip", 60_000_000,
               "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238"),
    ),
)

COMPONENTS: tuple[Component, ...] = (FFMPEG, DENO)

# Executable name -> component that provides it.
PROVIDES = {"ffmpeg": FFMPEG, "ffprobe": FFMPEG, "deno": DENO}


class ComponentError(Exception):
    """Installing a component failed; ``str(exc)`` is a Turkish message for the user."""


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------
# Locations and state
# --------------------------------------------------------------------------


def root_dir() -> str:
    """``%LOCALAPPDATA%\\Arnold DW\\runtime`` (machine-local: these are large binaries)."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, _env.APP_NAME, "runtime")


def component_dir(component: Component) -> str:
    return os.path.join(root_dir(), component.name)


def is_installed(component: Component) -> bool:
    folder = component_dir(component)
    try:
        with open(os.path.join(folder, MARKER), encoding="utf-8") as fh:
            marker = json.load(fh)
    except (OSError, ValueError):
        return False
    if not isinstance(marker, dict) or marker.get("version") != component.version:
        return False
    sizes = marker.get("sizes") or {}
    for name in component.files:
        path = os.path.join(folder, name)
        try:
            if os.path.getsize(path) != sizes.get(name):
                return False
        except OSError:
            return False
    return True


def missing() -> list[Component]:
    """Components that still have to be downloaded (none when running from a source checkout)."""
    return [c for c in COMPONENTS if not _bundled(c) and not is_installed(c)]


def _bundled(component: Component) -> bool:
    """A source checkout (or an old build) keeps the tools in ``bin/`` next to the app."""
    return all(os.path.isfile(os.path.join(_env.bin_dir(), name)) for name in component.files)


def executable(name: str) -> str | None:
    """Path of ``ffmpeg``/``ffprobe``/``deno`` from ``bin/`` or the installed component."""
    exe = _env.exe_name(name)
    bundled = os.path.join(_env.bin_dir(), exe)
    if os.path.isfile(bundled):
        return bundled
    component = PROVIDES.get(name)
    if component is not None and is_installed(component):
        return os.path.join(component_dir(component), exe)
    return None


def download_size_hint(components: list[Component]) -> int:
    """Approximate download size in bytes (our packs), for the setup screen."""
    return sum(PACK_SIZES.get(c.name, 0) for c in components)


# Approximate sizes of the xz packs, shown before the download starts.
PACK_SIZES = {"ffmpeg": 43_000_000, "deno": 29_500_000}


# --------------------------------------------------------------------------
# Installing
# --------------------------------------------------------------------------

ProgressCallback = Callable[[int, int | None], None]


def install(component: Component, progress: ProgressCallback | None = None,
            cancel_event: threading.Event | None = None, session=None) -> str:
    """Download, verify and install one component. Returns its folder. Blocking.

    Raises :class:`Cancelled` or :class:`ComponentError` (message ready for the user).
    """
    os.makedirs(root_dir(), exist_ok=True)
    errors = []
    for source in component.sources:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        staging = tempfile.mkdtemp(prefix=f".staging-{component.name}-", dir=root_dir())
        try:
            archive = os.path.join(staging, "download.part")
            _download(source, archive, progress, cancel_event, session)
            files = os.path.join(staging, "files")
            os.mkdir(files)
            _extract(component, source, archive, files)
            os.remove(archive)
            _write_marker(component, files, source)
            _activate(component, files)
            log.info("Installed %s %s from %s", component.name, component.version, source.url)
            return component_dir(component)
        except Cancelled:
            raise
        except Exception as exc:  # try the next source
            log.warning("Installing %s from %s failed: %s", component.name, source.url, exc)
            errors.append(exc)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    raise ComponentError(_user_message(component, errors))


def _user_message(component: Component, errors: list[Exception]) -> str:
    import requests

    if any(isinstance(e, PermissionError) for e in errors):
        return f"{component.title} kaydedilemedi: klasöre yazma izni yok."
    if all(isinstance(e, requests.RequestException | ConnectionError | TimeoutError) for e in errors):
        return f"{component.title} indirilemedi. İnternet bağlantınızı kontrol edip tekrar deneyin."
    return f"{component.title} indirilemedi veya doğrulanamadı. Lütfen tekrar deneyin."


def _download(source: Source, destination: str, progress, cancel_event, session) -> None:
    import requests

    _check_url(source.url)
    http = session or requests.Session()
    digest = hashlib.sha256()
    with http.get(source.url, stream=True, timeout=TIMEOUT,
                  headers={"User-Agent": f"{_env.APP_NAME} component installer"}) as response:
        _check_url(getattr(response, "url", None) or source.url)
        response.raise_for_status()
        total = _content_length(response)
        if total is not None and total > source.max_bytes:
            raise ValueError(f"{source.url} is larger than {source.max_bytes} bytes")
        done = 0
        last = 0.0
        with open(destination, "wb") as out:
            for chunk in response.iter_content(CHUNK_SIZE):
                if cancel_event is not None and cancel_event.is_set():
                    raise Cancelled()
                if not chunk:
                    continue
                done += len(chunk)
                if done > source.max_bytes:
                    raise ValueError(f"{source.url} exceeds {source.max_bytes} bytes")
                out.write(chunk)
                digest.update(chunk)
                now = time.monotonic()
                if progress is not None and now - last >= 0.1:
                    last = now
                    progress(done, total)
        if progress is not None:
            progress(done, total)
    if source.sha256 and digest.hexdigest() != source.sha256:
        raise ValueError(f"archive SHA-256 mismatch for {source.url}")


def _content_length(response) -> int | None:
    try:
        value = int(response.headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _check_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError(f"refusing to download from {url!r}")


def _extract(component: Component, source: Source, archive: str, destination: str) -> None:
    """Copy exactly the pinned files out of the archive (matched by file name, any folder)."""
    wanted = set(component.files)
    found = set()
    if source.kind == "tar.xz":
        with tarfile.open(archive, "r:xz") as tar:
            for member in tar:
                name = PurePosixPath(member.name).name
                if not member.isfile() or name not in wanted or name in found:
                    continue
                with tar.extractfile(member) as src, open(os.path.join(destination, name), "wb") as dst:
                    shutil.copyfileobj(src, dst, CHUNK_SIZE)
                found.add(name)
    else:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                name = PurePosixPath(info.filename).name
                if info.is_dir() or name not in wanted or name in found:
                    continue
                with zf.open(info) as src, open(os.path.join(destination, name), "wb") as dst:
                    shutil.copyfileobj(src, dst, CHUNK_SIZE)
                found.add(name)
    if found != wanted:
        raise ValueError(f"{source.url} lacks {sorted(wanted - found)}")
    for name, expected in component.files.items():
        if _sha256(os.path.join(destination, name)) != expected:
            raise ValueError(f"SHA-256 mismatch for {name} from {source.url}")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_marker(component: Component, folder: str, source: Source) -> None:
    marker = {
        "name": component.name,
        "version": component.version,
        "source": source.url,
        "sizes": {name: os.path.getsize(os.path.join(folder, name)) for name in component.files},
    }
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as fh:
        json.dump(marker, fh, indent=2)


def _activate(component: Component, folder: str) -> None:
    """Swap the verified folder into place; an older install is moved aside first."""
    target = component_dir(component)
    if os.path.exists(target):
        old = f"{target}.old-{os.getpid()}-{int(time.time())}"
        os.replace(target, old)
        shutil.rmtree(old, ignore_errors=True)
    os.replace(folder, target)


def cleanup_staging() -> None:
    """Remove leftovers of interrupted installs (called before a new attempt)."""
    try:
        entries = os.listdir(root_dir())
    except OSError:
        return
    for entry in entries:
        if entry.startswith(".staging-") or ".old-" in entry:
            shutil.rmtree(os.path.join(root_dir(), entry), ignore_errors=True)


def install_missing() -> int:
    """Install every missing component without UI. Returns a process exit code."""
    cleanup_staging()
    for component in missing():
        try:
            install(component)
        except (ComponentError, Cancelled) as exc:
            log.error("%s", exc)
            return 1
    return 0
