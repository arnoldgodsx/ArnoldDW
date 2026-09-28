"""Live updates for the yt-dlp engine, independent of app releases.

YouTube changes break a given yt-dlp release within weeks, so the app installs newer
yt-dlp wheels from PyPI into the user's profile and prefers them at startup::

    %APPDATA%\\Arnold DW\\engine\\yt-dlp\\
        state.json          {"schema": 1, "active": "2026.9.1", "broken": {...}, "last_check": ...}
        2026.9.1\\           site dir: yt_dlp/, yt_dlp_ejs/, *.dist-info/, engine.json
        .staging-*\\         in-progress install, renamed into place when complete

Every wheel is checked against the size and sha256 PyPI publishes before it is unpacked.
The yt-dlp-ejs version pinned by the new yt-dlp (its YouTube challenge solver scripts) is
installed alongside it. ``state.json`` is replaced atomically, so a crash mid-update leaves
the previous engine active.

``activate()`` must run before anything imports ``yt_dlp``. It installs a
``sys.meta_path`` finder at position 0 that serves ``yt_dlp`` / ``yt_dlp_ejs`` (and all of
their submodules) exclusively from the engine directory. A plain ``sys.path.insert`` is not
enough in a frozen app: with PyInstaller < 6 the bundled copy is served by a meta-path
importer that runs before ``sys.path`` is consulted, and in every version a missing
submodule must not silently fall back to the bundled (older) copy. If the new engine fails
to import, it is unloaded, marked broken and the next candidate (previous engine or the
bundled yt-dlp) is used instead.
"""

from __future__ import annotations

import ast
import compileall
import contextlib
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from . import _env
from .versioning import is_newer, parse_version, pinned_requirement, python_satisfies, same_version

log = logging.getLogger(__name__)

PROJECT = "yt-dlp"
EJS_PROJECT = "yt-dlp-ejs"
PACKAGES = ("yt_dlp", "yt_dlp_ejs")
PYPI_PROJECT_URL = "https://pypi.org/pypi/{project}/json"
PYPI_RELEASE_URL = "https://pypi.org/pypi/{project}/{version}/json"
STATE_FILE = "state.json"
MANIFEST_FILE = "engine.json"
STATE_SCHEMA = 1
KEEP_OLD_VERSIONS = 1
LOCK_STALE_SECONDS = 30 * 60
CHUNK_SIZE = 64 * 1024
TIMEOUT = (10, 60)  # connect, read

Channel = Literal["stable", "nightly"]
ProgressCallback = Callable[[int, int], None]


class UpdateError(Exception):
    """Update failed. ``user_message`` is the Turkish text to show in the UI."""

    def __init__(self, message: str, user_message: str = "Motor güncellemesi başarısız oldu."):
        super().__init__(message)
        self.user_message = user_message


class UpdateCancelled(UpdateError):
    def __init__(self):
        super().__init__("update cancelled by user", "Motor güncellemesi iptal edildi.")


@dataclass(frozen=True)
class DistFile:
    """One wheel on PyPI."""

    project: str
    version: str
    filename: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class UpdateInfo:
    version: str  # new yt-dlp version, PyPI spelling (e.g. "2026.9.1")
    current: str | None  # engine version running in this process
    wheel: DistFile
    ejs: DistFile | None  # challenge-solver package pinned by this yt-dlp release

    @property
    def files(self) -> tuple[DistFile, ...]:
        return (self.wheel,) if self.ejs is None else (self.wheel, self.ejs)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)


# ----------------------------------------------------------------------------
# Import redirection
# ----------------------------------------------------------------------------


class EngineFinder(importlib.abc.MetaPathFinder):
    """Serves the given top-level packages and their submodules from ``site_dir`` only."""

    def __init__(self, site_dir: str, packages: tuple[str, ...] = PACKAGES):
        self.site_dir = site_dir
        self.packages = frozenset(
            p for p in packages if os.path.isfile(os.path.join(site_dir, p, "__init__.py"))
        )

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.partition(".")[0]
        if top not in self.packages:
            return None
        if fullname == top:
            return importlib.machinery.PathFinder.find_spec(fullname, [self.site_dir], target)
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None:
            # Do not let another finder hand out the bundled copy of this submodule.
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return spec

    def __repr__(self):
        return f"<EngineFinder {self.site_dir!r} {sorted(self.packages)}>"


def _purge_modules(packages=PACKAGES) -> None:
    for name in list(sys.modules):
        if name.partition(".")[0] in packages:
            del sys.modules[name]
    importlib.invalidate_caches()


def _read_version_file(path: str) -> str | None:
    """``__version__`` from a yt_dlp/version.py source file, without executing it."""
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), path)
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


def detect_bundled_version() -> str | None:
    """Version of the yt-dlp shipped with the app, found without importing ``yt_dlp``.

    Works for a normal install and for PyInstaller's frozen archive: the version module's
    code object is fetched from whatever loader serves it and run in a scratch namespace.
    """
    try:
        spec = importlib.machinery.PathFinder.find_spec("yt_dlp")
        if spec is not None and spec.submodule_search_locations:
            locations = list(spec.submodule_search_locations)
            vspec = importlib.machinery.PathFinder.find_spec("yt_dlp.version", locations)
            if vspec is not None and vspec.loader is not None:
                code = vspec.loader.get_code("yt_dlp.version")
                namespace: dict = {"__name__": "yt_dlp.version"}
                exec(code, namespace)
                version = namespace.get("__version__")
                if isinstance(version, str):
                    return version
    except Exception as exc:
        log.warning("could not read bundled yt-dlp version from its module: %s", exc)
    try:
        from importlib import metadata

        return metadata.version(PROJECT)
    except Exception:
        return None


def _loaded_version() -> str | None:
    module = sys.modules.get("yt_dlp.version")
    version = getattr(module, "__version__", None)
    return version if isinstance(version, str) else None


# ----------------------------------------------------------------------------
# Engine manager
# ----------------------------------------------------------------------------

_DETECT = object()


class EngineManager:
    """Owns one engine directory. The module-level functions use a default instance."""

    def __init__(self, root: str | os.PathLike, *, session=None, bundled_version=_DETECT):
        self.root = os.fspath(root)
        self._session = session
        self._bundled_version = bundled_version
        self._activated: str | None = None
        self._active_dir: str | None = None
        self._finder: EngineFinder | None = None
        self._lock = threading.Lock()

    # -- versions -------------------------------------------------------------

    def bundled_version(self) -> str | None:
        if self._bundled_version is _DETECT:
            self._bundled_version = detect_bundled_version()
        return self._bundled_version

    def current_version(self) -> str | None:
        """yt-dlp version in use by this process (the bundled one until activation)."""
        if self._activated is not None:
            return self._activated
        return _loaded_version() or self.bundled_version()

    def engine_source(self) -> str:
        """``"engine"`` when an updated yt-dlp from the engine directory is active, else ``"bundled"``."""
        return "engine" if self._active_dir else "bundled"

    def installed_version(self) -> str | None:
        """Engine version that ``activate()`` will try first on the next start."""
        return self._load_state().get("active")

    def restart_required(self) -> bool:
        """True when an installed engine is newer than the one running now."""
        installed = self.installed_version()
        return bool(installed) and is_newer(installed, self.current_version())

    def last_check(self) -> float | None:
        value = self._load_state().get("last_check")
        return float(value) if isinstance(value, (int, float)) else None

    def installed_versions(self) -> list[str]:
        """Complete engine directories, newest first."""
        try:
            names = os.listdir(self.root)
        except OSError:
            return []
        versions = [
            n for n in names
            if not n.startswith(".") and parse_version(n) and os.path.isfile(self._manifest_path(n))
        ]
        return sorted(versions, key=parse_version, reverse=True)

    # -- state ----------------------------------------------------------------

    def _state_path(self) -> str:
        return os.path.join(self.root, STATE_FILE)

    def _manifest_path(self, version: str) -> str:
        return os.path.join(self.root, version, MANIFEST_FILE)

    def _load_state(self) -> dict:
        state = {"schema": STATE_SCHEMA, "active": None, "broken": {}, "last_check": None}
        try:
            with open(self._state_path(), encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return state
        except (OSError, ValueError) as exc:
            log.warning("engine state unreadable, starting fresh: %s", exc)
            return state
        if not isinstance(data, dict):
            return state
        if isinstance(data.get("active"), str):
            state["active"] = data["active"]
        if isinstance(data.get("broken"), dict):
            state["broken"] = {str(k): str(v) for k, v in data["broken"].items()}
        if isinstance(data.get("last_check"), (int, float)):
            state["last_check"] = data["last_check"]
        return state

    def _save_state(self, state: dict) -> None:
        os.makedirs(self.root, exist_ok=True)
        state = {**state, "schema": STATE_SCHEMA}
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._state_path())
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp)
            raise

    def _update_state(self, **changes) -> dict:
        with self._lock:
            state = self._load_state()
            state.update(changes)
            self._save_state(state)
            return state

    def _mark_broken(self, version: str, reason: str) -> None:
        with self._lock:
            state = self._load_state()
            state["broken"][version] = reason[:500]
            if state.get("active") == version:
                state["active"] = None
            self._save_state(state)
        log.error("yt-dlp engine %s marked broken: %s", version, reason)

    def mark_active_broken(self, reason: str) -> bool:
        """Report that the running engine fails at runtime (e.g. ImportError while extracting).

        The next start falls back to the previous engine or the bundled yt-dlp. Returns False
        when the bundled yt-dlp is running (nothing to roll back).
        """
        if not self._active_dir or not self._activated:
            return False
        self._mark_broken(os.path.basename(self._active_dir), reason)
        return True

    # -- activation -----------------------------------------------------------

    def activate(self, verify: bool = True) -> str:
        """Put the newest usable engine in front of the import system; return its version.

        Call once at startup before any ``import yt_dlp``. Falls back to the bundled
        yt-dlp when no newer engine is installed or every candidate fails to import.
        """
        if self._activated is not None:
            return self._activated
        if "yt_dlp" in sys.modules:
            loaded = _loaded_version() or self.bundled_version() or "unknown"
            log.warning("activate() called after yt_dlp was imported; staying on %s", loaded)
            self._activated = loaded
            return loaded

        bundled = self.bundled_version()
        state = self._load_state()
        broken = state["broken"]
        installed = self.installed_versions()
        candidates = list(installed)
        preferred = state.get("active")
        if preferred in candidates:
            candidates.remove(preferred)
            candidates.insert(0, preferred)

        for version in candidates:
            if version in broken or not is_newer(version, bundled):
                continue
            site_dir = os.path.join(self.root, version)
            finder = EngineFinder(site_dir)
            if "yt_dlp" not in finder.packages:
                continue
            sys.meta_path.insert(0, finder)
            try:
                loaded = self._verify_import(site_dir, version) if verify else version
            except Exception as exc:
                self._remove_finder(finder)
                _purge_modules()
                self._mark_broken(version, f"{type(exc).__name__}: {exc}")
                log.exception("yt-dlp engine %s failed to load, rolling back", version)
                continue
            self._finder = finder
            self._active_dir = site_dir
            self._activated = loaded
            if state.get("active") != version:
                with contextlib.suppress(OSError):
                    self._update_state(active=version)
            log.info("using yt-dlp engine %s from %s (bundled: %s)", loaded, site_dir, bundled)
            return loaded

        stale = preferred and (preferred in broken or preferred not in installed or not is_newer(preferred, bundled))
        if stale:
            with contextlib.suppress(OSError):
                self._update_state(active=None)
        self._activated = bundled or "unknown"
        log.info("using bundled yt-dlp %s", self._activated)
        return self._activated

    @staticmethod
    def _remove_finder(finder: EngineFinder) -> None:
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(finder)

    @staticmethod
    def _verify_import(site_dir: str, expected: str) -> str:
        yt_dlp = importlib.import_module("yt_dlp")
        origin = os.path.normcase(os.path.abspath(getattr(yt_dlp, "__file__", "") or ""))
        if not origin.startswith(os.path.normcase(os.path.abspath(site_dir)) + os.sep):
            raise ImportError(f"yt_dlp was loaded from {origin}, not from {site_dir}")
        version = getattr(importlib.import_module("yt_dlp.version"), "__version__", None)
        if not same_version(version, expected):
            raise ImportError(f"engine directory {expected} contains yt-dlp {version}")
        # Instantiating YoutubeDL imports every extractor and the post-processors, which
        # is where a missing dependency of a newer release would surface.
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            ydl.get_info_extractor("Youtube")
        return version

    # -- update check ---------------------------------------------------------

    def _http(self):
        if self._session is None:
            import requests

            from arnold_dw import __version__

            session = requests.Session()
            session.headers["User-Agent"] = f"ArnoldDW/{__version__} (engine-updater)"
            self._session = session
        return self._session

    def _get_json(self, url: str) -> dict:
        response = self._http().get(url, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"unexpected JSON from {url}")
        return data

    @staticmethod
    def _pick_wheel(project: str, version: str, files: list[dict]) -> DistFile:
        for entry in files or ():
            filename = entry.get("filename", "")
            sha256 = (entry.get("digests") or {}).get("sha256")
            if (
                entry.get("packagetype") == "bdist_wheel"
                and filename.endswith("-py3-none-any.whl")
                and not entry.get("yanked")
                and sha256
                and entry.get("url", "").startswith("https://")
            ):
                return DistFile(project, version, filename, entry["url"], sha256.lower(), int(entry.get("size") or 0))
        raise UpdateError(f"no pure-Python wheel for {project} {version}")

    @staticmethod
    def _latest_release(data: dict, channel: Channel) -> str:
        if channel == "stable":
            return data["info"]["version"]
        releases = data.get("releases") or {}
        usable = [
            v for v, files in releases.items()
            if parse_version(v) and any(
                f.get("packagetype") == "bdist_wheel" and not f.get("yanked") for f in files or ()
            )
        ]
        if not usable:
            raise UpdateError("PyPI lists no usable releases")
        return max(usable, key=parse_version)

    def check_for_update(self, channel: Channel = "stable", *, raise_errors: bool = False) -> UpdateInfo | None:
        """Newest yt-dlp on PyPI if it beats everything already available, else ``None``.

        ``channel="nightly"`` also considers yt-dlp's nightly builds (published to PyPI as
        ``.devN`` releases), which usually carry YouTube fixes days before a stable release.
        Network and parsing errors are logged and reported as "no update", or raised as
        :class:`UpdateError` when ``raise_errors`` is set (so a UI can tell "up to date"
        from "could not check").
        """
        try:
            info = self._build_update_info(channel)
        except Exception as exc:
            log.warning("yt-dlp update check failed: %s", exc)
            if not raise_errors:
                return None
            raise _check_error(exc) from exc
        with contextlib.suppress(OSError):
            self._update_state(last_check=time.time())
        return info

    def _build_update_info(self, channel: Channel) -> UpdateInfo | None:
        project = self._get_json(PYPI_PROJECT_URL.format(project=PROJECT))
        latest = self._latest_release(project, channel)
        if project.get("info", {}).get("version") == latest:
            release = project
        else:
            release = self._get_json(PYPI_RELEASE_URL.format(project=PROJECT, version=latest))

        state = self._load_state()
        baseline = max(
            [v for v in (self.bundled_version(), self.current_version(), *self.installed_versions())
             if v and v not in state["broken"] and parse_version(v)],
            key=parse_version,
            default=None,
        )
        if not is_newer(latest, baseline):
            log.info("yt-dlp is up to date (%s, newest on PyPI: %s)", baseline, latest)
            return None
        if latest in state["broken"]:
            log.info("skipping yt-dlp %s: previously failed (%s)", latest, state["broken"][latest])
            return None
        requires_python = release.get("info", {}).get("requires_python")
        if not python_satisfies(requires_python):
            log.warning("yt-dlp %s requires Python %s; running %s", latest, requires_python, sys.version)
            return None

        wheel = self._pick_wheel(PROJECT, latest, release.get("urls") or [])
        ejs = None
        ejs_version = pinned_requirement(release.get("info", {}).get("requires_dist"), EJS_PROJECT)
        if ejs_version:
            ejs_release = self._get_json(PYPI_RELEASE_URL.format(project=EJS_PROJECT, version=ejs_version))
            ejs = self._pick_wheel(EJS_PROJECT, ejs_version, ejs_release.get("urls") or [])
        return UpdateInfo(version=latest, current=self.current_version(), wheel=wheel, ejs=ejs)

    # -- install --------------------------------------------------------------

    def download_and_install(
        self,
        info: UpdateInfo,
        progress_cb: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Download, verify and install ``info``; it becomes active on the next start.

        ``progress_cb(done_bytes, total_bytes)`` is called from this (worker) thread.
        Raises :class:`UpdateCancelled` when ``cancel_event`` is set, :class:`UpdateError`
        on any failure; the previously active engine stays untouched in both cases.
        """
        os.makedirs(self.root, exist_ok=True)
        with self._install_lock():
            self._remove_stale_staging()
            target = os.path.join(self.root, info.version)
            if self._is_installed(target, info):
                log.info("yt-dlp %s already installed", info.version)
            else:
                self._install(info, target, progress_cb, cancel_event)
            with self._lock:
                state = self._load_state()
                state["active"] = info.version
                state["broken"].pop(info.version, None)
                self._save_state(state)
            self._prune()
        log.info("yt-dlp %s installed; active after restart", info.version)
        return info.version

    def _install(self, info, target, progress_cb, cancel_event) -> None:
        staging = tempfile.mkdtemp(prefix=f".staging-{info.version}-", dir=self.root)
        try:
            downloads = os.path.join(staging, ".downloads")
            os.makedirs(downloads)
            total = info.total_size
            done = 0
            for dist in info.files:
                path = os.path.join(downloads, dist.filename)
                done = self._download(dist, path, done, total, progress_cb, cancel_event)
            _check_cancel(cancel_event)
            for dist in info.files:
                _extract_wheel(os.path.join(downloads, dist.filename), staging)
            shutil.rmtree(downloads)

            found = _read_version_file(os.path.join(staging, "yt_dlp", "version.py"))
            if not same_version(found, info.version):
                raise UpdateError(f"wheel for {info.version} contains yt-dlp {found}")
            _check_cancel(cancel_event)
            # Byte-compiling doubles as a compatibility check for this Python and makes the
            # first start on the new engine fast. workers=1: no child processes (frozen app).
            if not compileall.compile_dir(staging, quiet=2, workers=1):
                raise UpdateError(
                    f"yt-dlp {info.version} does not compile on Python {sys.version.split()[0]}",
                    "Yeni motor sürümü bu uygulama sürümüyle uyumlu değil.",
                )
            manifest = {
                "version": info.version,
                "wheel": info.wheel.filename,
                "wheel_sha256": info.wheel.sha256,
                "ejs_version": info.ejs.version if info.ejs else None,
                "ejs_sha256": info.ejs.sha256 if info.ejs else None,
                "installed_at": time.time(),
                "python": sys.version.split()[0],
            }
            with open(os.path.join(staging, MANIFEST_FILE), "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)
            _check_cancel(cancel_event)
            if os.path.exists(target):
                if self._active_dir and os.path.samefile(target, self._active_dir):
                    raise UpdateError(f"engine {info.version} is in use and cannot be replaced")
                shutil.rmtree(target)
            os.replace(staging, target)
        except UpdateError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except BaseException as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, Exception):
                raise _as_update_error(exc) from exc
            raise

    def _download(self, dist: DistFile, path: str, done: int, total: int, progress_cb, cancel_event) -> int:
        _check_cancel(cancel_event)
        digest = hashlib.sha256()
        size = 0
        with self._http().get(dist.url, stream=True, timeout=TIMEOUT) as response:
            response.raise_for_status()
            with open(path, "wb") as fh:
                for chunk in response.iter_content(CHUNK_SIZE):
                    _check_cancel(cancel_event)
                    if not chunk:
                        continue
                    fh.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    if dist.size and size > dist.size:
                        raise UpdateError(f"{dist.filename}: more data than the {dist.size} bytes announced")
                    if progress_cb:
                        progress_cb(done + size, total)
        if dist.size and size != dist.size:
            raise UpdateError(f"{dist.filename}: got {size} bytes, expected {dist.size}")
        if digest.hexdigest() != dist.sha256:
            raise UpdateError(
                f"{dist.filename}: sha256 mismatch ({digest.hexdigest()} != {dist.sha256})",
                "İndirilen motor dosyası doğrulanamadı; güncelleme uygulanmadı.",
            )
        return done + size

    def _is_installed(self, target: str, info: UpdateInfo) -> bool:
        try:
            with open(os.path.join(target, MANIFEST_FILE), encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError):
            return False
        return (
            isinstance(manifest, dict)
            and manifest.get("wheel_sha256") == info.wheel.sha256
            and manifest.get("ejs_sha256") == (info.ejs.sha256 if info.ejs else None)
            and os.path.isfile(os.path.join(target, "yt_dlp", "__init__.py"))
        )

    @contextlib.contextmanager
    def _install_lock(self):
        path = os.path.join(self.root, ".install.lock")
        for attempt in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    stale = time.time() - os.path.getmtime(path) > LOCK_STALE_SECONDS
                except OSError:
                    stale = True
                if attempt == 0 and stale:
                    with contextlib.suppress(OSError):
                        os.remove(path)
                    continue
                raise UpdateError("another engine update is running", "Başka bir motor güncellemesi sürüyor.") from None
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)

    def _remove_stale_staging(self) -> None:
        with contextlib.suppress(OSError):
            for name in os.listdir(self.root):
                if name.startswith(".staging-"):
                    shutil.rmtree(os.path.join(self.root, name), ignore_errors=True)

    def _prune(self) -> None:
        """Keep the active engine, the one loaded in this process and at most one older good one."""
        state = self._load_state()
        active = state.get("active")
        in_use = os.path.basename(self._active_dir) if self._active_dir else None
        keep = {v for v in (active, in_use) if v}
        older = [
            v for v in self.installed_versions()
            if v not in keep and v not in state["broken"] and (not active or is_newer(active, v))
        ]
        keep.update(older[:KEEP_OLD_VERSIONS])
        for name in os.listdir(self.root):
            if name.startswith(".") or name == STATE_FILE or name in keep:
                continue
            path = os.path.join(self.root, name)
            if os.path.isdir(path):
                log.info("removing old yt-dlp engine %s", name)
                shutil.rmtree(path, ignore_errors=True)


def _check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise UpdateCancelled()


def _as_update_error(exc: Exception) -> UpdateError:
    try:
        import requests

        network_errors: tuple = (requests.RequestException, ConnectionError, TimeoutError)
    except ImportError:  # pragma: no cover - requests is a hard dependency of the app
        network_errors = (ConnectionError, TimeoutError)
    if isinstance(exc, network_errors):
        return UpdateError(f"network error: {exc}", "Motor güncellemesi indirilemedi. İnternet bağlantınızı kontrol edin.")
    if isinstance(exc, OSError):
        return UpdateError(f"disk error: {exc}", "Motor güncellemesi diske yazılamadı.")
    return UpdateError(f"{type(exc).__name__}: {exc}")


def _check_error(exc: Exception) -> UpdateError:
    return UpdateError(f"{type(exc).__name__}: {exc}",
                       "Güncellemeler denetlenemedi. İnternet bağlantınızı kontrol edin.")


def engine_failure_reason(exc: BaseException | None) -> str | None:
    """Describe ``exc`` if it shows the yt-dlp engine itself is broken, else ``None``.

    A half-working engine (a new yt-dlp whose submodule is missing or renamed) surfaces as
    ImportError/AttributeError raised from inside the ``yt_dlp`` package, possibly wrapped by
    yt-dlp's own DownloadError (``exc_info``) or chained. Errors raised elsewhere - our own
    hooks, network problems, unavailable videos - never count.
    """
    seen: set[int] = set()
    stack = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ImportError, AttributeError)) and _raised_in_engine(current):
            return f"{type(current).__name__}: {current}"[:500]
        exc_info = getattr(current, "exc_info", None)
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            stack.append(exc_info[1])
        stack.extend([current.__cause__, current.__context__])
    return None


def _raised_in_engine(exc: BaseException) -> bool:
    tb = exc.__traceback__
    last = None
    while tb is not None:
        last = tb.tb_frame.f_code.co_filename
        tb = tb.tb_next
    if last is None:
        return False
    parts = os.path.normcase(os.path.normpath(last)).split(os.sep)
    return any(p in PACKAGES for p in parts[:-1])


def _extract_wheel(wheel_path: str, dest: str) -> None:
    """Unpack the import packages of a wheel (plus its dist-info) into ``dest``."""
    dest_abs = os.path.abspath(dest)
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            for member in archive.infolist():
                name = member.filename
                top = name.split("/", 1)[0]
                if top not in PACKAGES and not top.endswith(".dist-info"):
                    continue  # skip *.data/ (scripts, man pages) and stray files
                target = os.path.abspath(os.path.join(dest_abs, *name.split("/")))
                if not target.startswith(dest_abs + os.sep):
                    raise UpdateError(f"unsafe path in wheel: {name}")
                if member.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"corrupt wheel {os.path.basename(wheel_path)}: {exc}") from exc


# ----------------------------------------------------------------------------
# Module-level API (default engine directory)
# ----------------------------------------------------------------------------

_default_manager: EngineManager | None = None
_default_lock = threading.Lock()


def engine_root() -> str:
    return os.path.join(_env.app_data_dir(), "engine", "yt-dlp")


def default_manager() -> EngineManager:
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            _default_manager = EngineManager(engine_root())
        return _default_manager


def activate(verify: bool = True) -> str:
    """See :meth:`EngineManager.activate`. Call before the first ``import yt_dlp``."""
    try:
        return default_manager().activate(verify=verify)
    except Exception:
        # Never let engine housekeeping stop the app from starting.
        log.exception("engine activation failed; using bundled yt-dlp")
        return default_manager().current_version() or "unknown"


def check_for_update(channel: Channel = "stable", *, raise_errors: bool = False) -> UpdateInfo | None:
    return default_manager().check_for_update(channel, raise_errors=raise_errors)


def download_and_install(
    info: UpdateInfo,
    progress_cb: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    return default_manager().download_and_install(info, progress_cb, cancel_event)


def current_version() -> str | None:
    return default_manager().current_version()


def engine_source() -> str:
    return default_manager().engine_source()


def installed_version() -> str | None:
    return default_manager().installed_version()


def restart_required() -> bool:
    return default_manager().restart_required()


def mark_active_broken(reason: str) -> bool:
    return default_manager().mark_active_broken(reason)


def report_failure(exc: BaseException) -> bool:
    """Mark the running engine broken if ``exc`` came from inside it. Never raises.

    Returns True when the engine was marked (the next start rolls back to the previous one).
    """
    try:
        reason = engine_failure_reason(exc)
        return bool(reason) and default_manager().mark_active_broken(reason)
    except Exception:
        log.exception("could not record the engine failure")
        return False
