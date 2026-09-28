"""Application entry point."""

import logging

from arnold_dw import APP_NAME, __version__, single_instance
from arnold_dw.log import setup_logging

log = logging.getLogger(__name__)


def main():
    lock = single_instance.acquire()
    if lock is None:
        # Already running for this user: bring that window forward instead of opening a second one.
        single_instance.activate_existing()
        return

    log_path = setup_logging()
    log.info("%s %s starting (log: %s)", APP_NAME, __version__, log_path)

    # Import the UI (and through it yt_dlp) only after logging is up. Engine
    # activation (a newer downloaded yt-dlp) must also happen before this import.
    from arnold_dw.core.runtime import restart, ytdlp_updater

    engine = ytdlp_updater.activate()  # never raises; falls back to the bundled yt-dlp
    log.info("yt-dlp engine %s (%s)", engine, ytdlp_updater.engine_source())

    import customtkinter as ctk

    from arnold_dw.ui.window import ArnoldDW

    ctk.set_appearance_mode("dark")
    app = ArnoldDW(instance_key=lock.key)
    app.mainloop()
    lock.release()
    log.info("%s exited", APP_NAME)
    restart.relaunch_if_requested()  # "Restart now" after an engine update
