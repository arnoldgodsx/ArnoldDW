"""Filesystem locations: bundled resources, per-user AppData and download folders."""

import os
import sys

from arnold_dw import APP_NAME

# Repository root when running from source; PyInstaller's unpack dir when frozen.
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", _SOURCE_ROOT)
    return os.path.join(base, *parts)


ICON_PATH = resource_path("logo", "icon.ico")
APP_LOGO_PATH = resource_path("logo", "app-logo.png")
YOUTUBE_LOGO_PATH = resource_path("logo", "youtube.png")
INSTAGRAM_LOGO_PATH = resource_path("logo", "instagram.png")
BACK_ICON_PATH = resource_path("logo", "back.png")
FFMPEG_PATH = resource_path("bin", "ffmpeg.exe")


def config_dir():
    """Per-user app data dir (%APPDATA%\\Arnold DW). Re-reads the environment on every call."""
    return os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME)


def config_path():
    return os.path.join(config_dir(), "config.json")


def log_dir():
    return os.path.join(config_dir(), "logs")


def history_path():
    return os.path.join(config_dir(), "history.db")


def thumbs_dir():
    """Small cover images of downloads, referenced from the history."""
    return os.path.join(config_dir(), "thumbs")


def default_download_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads", APP_NAME)


# Snapshot values for callers that just need the paths as of startup.
CONFIG_DIR = config_dir()
CONFIG_PATH = config_path()
LOG_DIR = log_dir()
DEFAULT_DOWNLOAD_DIR = default_download_dir()
