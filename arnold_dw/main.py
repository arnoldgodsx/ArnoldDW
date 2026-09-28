"""Application entry point."""

import logging

from arnold_dw import APP_NAME, __version__
from arnold_dw.log import setup_logging

log = logging.getLogger(__name__)


def main():
    log_path = setup_logging()
    log.info("%s %s starting (log: %s)", APP_NAME, __version__, log_path)

    # Import the UI (and through it yt_dlp) only after logging is up. Engine
    # activation (a newer downloaded yt-dlp) must also happen before this import.
    import customtkinter as ctk

    from arnold_dw.ui.window import ArnoldDW

    ctk.set_appearance_mode("dark")
    app = ArnoldDW()
    app.mainloop()
    log.info("%s exited", APP_NAME)
