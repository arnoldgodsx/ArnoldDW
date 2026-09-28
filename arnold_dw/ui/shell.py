"""Hand files to the operating system: open with the default app, show in Explorer."""

import logging
import os
import subprocess
import sys

log = logging.getLogger(__name__)


def open_file(path):
    """Open `path` with its default application. Returns False if it doesn't exist or failed."""
    if not path or not os.path.exists(path):
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - a file the user downloaded, opened on request
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except OSError:
        log.warning("Could not open %s", path, exc_info=True)
        return False


def show_in_folder(path):
    """Open the containing folder with `path` selected. Returns False if nothing to show."""
    if not path:
        return False
    path = os.path.normpath(path)
    try:
        if os.path.exists(path):
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
            return True
        folder = os.path.dirname(path)
        if os.path.isdir(folder):
            if sys.platform == "win32":
                os.startfile(folder)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", folder])
            return True
    except OSError:
        log.warning("Could not show %s in its folder", path, exc_info=True)
    return False
