"""Main window: window chrome, screen switching and the worker -> UI message queue."""

import logging
import queue
import time

import customtkinter as ctk

from arnold_dw import APP_NAME, paths
from arnold_dw.config import load_settings, save_settings
from arnold_dw.ui.screens.home import HomeScreen
from arnold_dw.ui.screens.instagram import InstagramScreen
from arnold_dw.ui.screens.youtube import YouTubeScreen
from arnold_dw.ui.theme import APP_HEIGHT, APP_WIDTH, BG, SCREEN_PADX, SCREEN_PADY

log = logging.getLogger(__name__)

# Screen name -> class. Registering a screen here is all it takes to activate
# its home-screen card (see ui.screens.home.PLATFORMS).
SCREENS = {
    "home": HomeScreen,
    "youtube": YouTubeScreen,
    "instagram": InstagramScreen,
}

POLL_INTERVAL_MS = 60
CLOSE_WAIT_SECONDS = 5.0


class ArnoldDW(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.ui_queue = queue.Queue()
        self.settings = load_settings()
        self.screen = None
        self._closing = False

        self._configure_window()
        self.show_screen("home")
        self._apply_dark_titlebar()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_queue)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _configure_window(self):
        self.title(APP_NAME)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        try:
            self.iconbitmap(paths.ICON_PATH)
        except Exception:
            log.warning("Could not set window icon", exc_info=True)

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ArnoldDW.YoutubeDownloader.1"
            )
        except Exception:
            pass

    def _apply_dark_titlebar(self):
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def report_callback_exception(self, exc, val, tb):
        log.error("Unhandled exception in Tk callback", exc_info=(exc, val, tb))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @property
    def download_dir(self):
        return self.settings.download_dir

    def set_download_dir(self, path):
        self.settings.download_dir = path
        save_settings(self.settings)

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------

    def has_screen(self, name):
        return name in SCREENS

    def show_screen(self, name):
        if self.screen is not None:
            self.screen.destroy()  # also cancels the screen's pending `after` jobs
            self.screen = None
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        screen = SCREENS[name](self)
        screen.pack(fill="both", expand=True, padx=SCREEN_PADX, pady=SCREEN_PADY)
        self.screen = screen
        screen.build()
        log.debug("Screen: %s", name)

    # Kept for UI automation scripts (hq/tools/snap.py --script).
    def _show_home(self):
        self.show_screen("home")

    def _show_youtube(self):
        self.show_screen("youtube")

    def _show_instagram(self):
        self.show_screen("instagram")

    # ------------------------------------------------------------------
    # Worker -> UI messages
    # ------------------------------------------------------------------

    def post_message(self, screen, kind, *args):
        """Thread-safe. Delivered on the UI thread only if `screen` is still displayed."""
        self.ui_queue.put((screen, kind, args))

    def _poll_queue(self):
        try:
            while True:
                screen, kind, args = self.ui_queue.get_nowait()
                if screen is not self.screen or not screen.winfo_exists():
                    continue  # the screen that asked is gone; drop stale results
                try:
                    screen.handle_message(kind, args)
                except Exception:
                    log.exception("Error handling %s message %r", screen.name, kind)
        except queue.Empty:
            pass
        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_queue)

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _on_close(self):
        """Cancel running downloads, give them a moment to clean up, then exit."""
        if self._closing:
            return
        self._closing = True
        workers = self.screen.shutdown() if self.screen is not None else []
        if not workers:
            self._finish_close()
            return
        log.info("Closing: waiting for %d worker(s) to stop", len(workers))
        self.withdraw()
        deadline = time.monotonic() + CLOSE_WAIT_SECONDS

        def wait():
            if any(t.is_alive() for t in workers) and time.monotonic() < deadline:
                self.after(100, wait)
            else:
                self._finish_close()

        wait()

    def _finish_close(self):
        try:
            self.after_cancel(self._poll_job)
        except Exception:
            pass
        if self.screen is not None:
            self.screen.destroy()
            self.screen = None
        self.destroy()
