"""Relaunching the app, e.g. to pick up a freshly installed yt-dlp engine.

Flow: the UI calls :func:`request` and closes the window normally; after the main loop has
returned, :func:`relaunch_if_requested` starts a new instance. Starting it only after the
old window is gone avoids two instances fighting over config or a single-instance lock.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from . import _env

log = logging.getLogger(__name__)

_requested = False


def request() -> None:
    global _requested
    _requested = True


def cancel() -> None:
    global _requested
    _requested = False


def requested() -> bool:
    return _requested


def relaunch_command(executable: str | None = None, argv: list[str] | None = None,
                     frozen: bool | None = None) -> list[str]:
    """Command line that starts the app the way the current process was started."""
    executable = executable or sys.executable
    argv = list(sys.argv if argv is None else argv)
    frozen = _env.is_frozen() if frozen is None else frozen
    if frozen or not argv or not argv[0]:
        return [executable, *argv[1:]]
    return [executable, os.path.abspath(argv[0]), *argv[1:]]


def relaunch_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the new instance without PyInstaller's per-process bootstrap state."""
    env = dict(os.environ if environ is None else environ)
    for key in list(env):
        if key.startswith("_PYI_") or key == "_MEIPASS2":
            del env[key]
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def relaunch() -> bool:
    cmd = relaunch_command()
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(cmd, env=relaunch_env(), cwd=os.getcwd(), close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
    except OSError:
        log.exception("could not relaunch the app: %s", cmd)
        return False
    log.info("relaunched: %s", cmd)
    return True


def relaunch_if_requested() -> bool:
    """Call after the UI main loop has exited. Never raises."""
    if not _requested:
        return False
    try:
        return relaunch()
    except Exception:
        log.exception("relaunch failed")
        return False
