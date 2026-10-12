"""Discovery of external tools used by yt-dlp: ffmpeg and a JavaScript runtime.

YouTube (yt-dlp >= 2025.11) needs a JS runtime to solve the player's "n"/signature
challenges; without one yt-dlp logs "No supported JavaScript runtime could be found" and
many formats go missing. The solver scripts come from the ``yt-dlp-ejs`` Python package
(bundled with the app, pinned to the version yt-dlp expects), so the runtime only has to
execute them - no network access is needed.

Search order (first usable wins): runtimes in ``bin/`` (source checkout) or downloaded on
first launch (``core.runtime.components``), then deno / node / bun found on PATH. The order within each group follows
yt-dlp's own priority. QuickJS is deliberately not used: it is supported by yt-dlp but
takes tens of seconds per video.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import _env, components
from .versioning import meets_minimum

log = logging.getLogger(__name__)

# Mirrors yt_dlp.utils._jsruntime.*.MIN_SUPPORTED_VERSION (yt-dlp 2026.08.19). When yt-dlp
# is already imported its own values are used instead, so a newer engine wins.
JS_RUNTIME_MIN_VERSIONS: dict[str, tuple[int, ...]] = {
    "deno": (2, 3, 0),
    "node": (22, 0, 0),
    "bun": (1, 2, 11),
}
JS_RUNTIME_PRIORITY = ("deno", "node", "bun")

_VERSION_PATTERNS = {
    "ffmpeg": re.compile(r"ffmpeg version (\S+)"),
    "deno": re.compile(r"^deno (\S+)", re.M),
    "node": re.compile(r"^v(\S+)", re.M),
    "bun": re.compile(r"^(\d\S*)", re.M),
}
_YTDLP_RUNTIME_CLASSES = {"deno": "DenoJsRuntime", "node": "NodeJsRuntime", "bun": "BunJsRuntime"}

# yt-dlp may fetch the hash-pinned solver scripts from the yt-dlp/ejs GitHub release when
# the bundled yt-dlp-ejs package is missing or does not match the engine version (e.g. right
# after a live engine update). yt-dlp verifies them against hashes shipped in its own code.
REMOTE_COMPONENTS = ("ejs:github",)


@dataclass(frozen=True)
class JsRuntime:
    name: str
    path: str
    version: str
    bundled: bool


def _run_version(path: str, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            stdin=subprocess.DEVNULL,
            **_env.no_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("could not run %s: %s", path, exc)
        return None
    return (proc.stdout or "") + (proc.stderr or "")


def _probe_version(tool: str, path: str) -> str | None:
    output = _run_version(path, ["-version"] if tool == "ffmpeg" else ["--version"])
    if not output:
        return None
    match = _VERSION_PATTERNS[tool].search(output)
    return match.group(1) if match else None


def _bundled(name: str) -> str | None:
    return components.executable(name)


@functools.cache
def ffmpeg_path() -> str | None:
    """App-provided ffmpeg (``bin/`` or the downloaded component), else ffmpeg on PATH, else ``None``."""
    path = _bundled("ffmpeg") or shutil.which("ffmpeg")
    if path is None:
        log.warning("ffmpeg not found (neither bundled nor on PATH)")
    return path


@functools.cache
def ffprobe_path() -> str | None:
    """ffprobe next to the ffmpeg in use, or ``None``.

    yt-dlp looks for ffprobe only in the ``ffmpeg_location`` directory. Without mutagen it
    needs ffprobe to embed covers into MP4/M4A (MP3 works with ffmpeg alone).
    """
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return None
    candidate = os.path.join(os.path.dirname(ffmpeg), _env.exe_name("ffprobe"))
    return candidate if os.path.isfile(candidate) else None


@functools.cache
def _ffmpeg_version(path: str) -> str | None:
    return _probe_version("ffmpeg", path)


def ffmpeg_version(path: str | None = None) -> str | None:
    """Version string reported by ``ffmpeg -version`` (e.g. ``"7.1.1-full_build-www.gyan.dev"``)."""
    path = path or ffmpeg_path()
    return _ffmpeg_version(path) if path else None


def js_runtime_min_versions() -> dict[str, tuple[int, ...]]:
    """Minimum runtime versions, taken from the loaded yt-dlp when possible.

    Never triggers ``import yt_dlp`` itself (that would pin the engine before activation).
    """
    minimums = dict(JS_RUNTIME_MIN_VERSIONS)
    if "yt_dlp" not in sys.modules:
        return minimums
    try:
        import importlib

        module = importlib.import_module("yt_dlp.utils._jsruntime")
        for name, cls_name in _YTDLP_RUNTIME_CLASSES.items():
            value = getattr(getattr(module, cls_name, None), "MIN_SUPPORTED_VERSION", None)
            if isinstance(value, tuple) and all(isinstance(p, int) for p in value):
                minimums[name] = value
    except Exception as exc:  # private yt-dlp API: fall back to our table
        log.debug("could not read yt-dlp JS runtime minimums: %s", exc)
    return minimums


def _candidates() -> list[tuple[str, str, bool]]:
    found: list[tuple[str, str, bool]] = []
    seen: set[str] = set()
    for bundled in (True, False):
        for name in JS_RUNTIME_PRIORITY:
            path = _bundled(name) if bundled else shutil.which(name)
            if path:
                key = os.path.normcase(os.path.realpath(path))
                if key not in seen:
                    seen.add(key)
                    found.append((name, path, bundled))
    return found


@functools.cache
def find_js_runtime() -> JsRuntime | None:
    """First usable JS runtime (bundled before system, deno > node > bun), or ``None``."""
    minimums = js_runtime_min_versions()
    for name, path, bundled in _candidates():
        version = _probe_version(name, path)
        if version is None:
            log.info("ignoring %s at %s: version could not be determined", name, path)
            continue
        if not meets_minimum(version, minimums[name]):
            log.info("ignoring %s %s at %s: older than %s", name, version, path,
                     ".".join(map(str, minimums[name])))
            continue
        runtime = JsRuntime(name=name, path=path, version=version, bundled=bundled)
        log.info("JS runtime for YouTube: %s %s (%s)", name, version, path)
        return runtime
    log.warning("no supported JavaScript runtime found; YouTube formats may be limited")
    return None


def ytdlp_runtime_options() -> dict:
    """yt-dlp ``YoutubeDL`` params wiring in the discovered tools.

    Keys: ``ffmpeg_location`` (when ffmpeg was found), ``js_runtimes`` (when a runtime was
    found; replaces yt-dlp's PATH-only ``{"deno": {}}`` default) and ``remote_components``.
    Merge into the caller's options: ``{**base_opts, **ytdlp_runtime_options()}``.
    """
    opts: dict = {"remote_components": list(REMOTE_COMPONENTS)}
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    runtime = find_js_runtime()
    if runtime:
        opts["js_runtimes"] = {runtime.name: {"path": runtime.path}}
    return opts


def refresh() -> None:
    """Forget cached discovery results (e.g. after the user installs a runtime)."""
    ffmpeg_path.cache_clear()
    ffprobe_path.cache_clear()
    _ffmpeg_version.cache_clear()
    find_js_runtime.cache_clear()
