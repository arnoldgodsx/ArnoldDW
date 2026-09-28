"""Process environment helpers shared by the runtime modules (paths, subprocess flags)."""

from __future__ import annotations

import os
import subprocess
import sys

APP_NAME = "Arnold DW"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> str:
    """Directory holding bundled resources (``bin/``, ``logo/``).

    PyInstaller unpacks them to ``sys._MEIPASS``; in a source checkout it is the repo root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def bin_dir() -> str:
    return os.path.join(bundle_dir(), "bin")


def app_data_dir() -> str:
    """``%APPDATA%\\Arnold DW`` (falls back to the home directory when APPDATA is unset)."""
    return os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME)


def exe_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def no_window_kwargs() -> dict:
    """``subprocess`` kwargs that keep a console window from flashing up in the windowed exe."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
