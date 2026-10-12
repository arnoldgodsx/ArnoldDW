"""Main window: window chrome, navigation, the download manager and the worker -> UI queue."""

import logging
import queue
import threading
import time
from tkinter import messagebox

import customtkinter as ctk

from arnold_dw import APP_NAME, paths, single_instance
from arnold_dw.config import load_settings, save_settings
from arnold_dw.core.history import History
from arnold_dw.core.jobs import DownloadManager
from arnold_dw.core.runners import default_runners
from arnold_dw.core.runtime import components
from arnold_dw.ui.screens.downloads import DownloadsScreen
from arnold_dw.ui.screens.home import HomeScreen
from arnold_dw.ui.screens.instagram import InstagramScreen
from arnold_dw.ui.screens.settings import SettingsScreen
from arnold_dw.ui.screens.setup import SetupScreen
from arnold_dw.ui.screens.youtube import YouTubeScreen
from arnold_dw.ui.theme import APP_HEIGHT, APP_WIDTH, BG, SCREEN_PADX, SCREEN_PADY
from arnold_dw.ui.widgets.navbar import NavBar

log = logging.getLogger(__name__)

# Screen name -> class. Registering a screen here is all it takes to activate
# its home-screen card (see ui.screens.home.PLATFORMS) or its navigation tab
# (see ui.widgets.navbar.TABS).
SCREENS = {
    "home": HomeScreen,
    "youtube": YouTubeScreen,
    "instagram": InstagramScreen,
    "downloads": DownloadsScreen,
    "settings": SettingsScreen,
    "setup": SetupScreen,
}

POLL_INTERVAL_MS = 60
CLOSE_WAIT_SECONDS = 5.0

_JOB_EVENT = object()  # ui_queue marker: a DownloadManager event instead of a screen message


class ArnoldDW(ctk.CTk):
    def __init__(self, instance_key=None):
        super().__init__()

        self.ui_queue = queue.Queue()
        self.settings = load_settings()
        self.screen = None
        self._persistent = {}
        self._closing = False
        self._instance_key = instance_key

        self.downloads = DownloadManager(
            default_runners(),
            on_event=self._on_job_event,
            max_concurrent=self.settings.max_concurrent,
            history=History(paths.history_path()),
            thumbs_dir=paths.thumbs_dir(),
        )

        self._configure_window()
        self.navbar = NavBar(self)
        if components.missing():
            # First launch: download ffmpeg/Deno before anything else (no navigation yet).
            self.show_screen("setup")
        else:
            self.navbar.pack(side="bottom", fill="x")
            self.show_screen("home")
        self._apply_dark_titlebar()
        self._tag_instance_window()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_queue)
        threading.Thread(target=self._load_history, daemon=True, name="history-load").start()

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

    def _top_level_hwnd(self):
        import ctypes
        self.update_idletasks()
        return ctypes.windll.user32.GetParent(self.winfo_id())

    def _apply_dark_titlebar(self):
        try:
            import ctypes
            hwnd = self._top_level_hwnd()
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def _tag_instance_window(self):
        if self._instance_key is None:
            return
        try:
            single_instance.tag_window(self._top_level_hwnd(), self._instance_key)
        except Exception:
            log.warning("Could not tag the window for single-instance activation", exc_info=True)

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
            if self.screen.name == name:
                return
            if self.screen.persistent:
                self.screen.pack_forget()
                self.screen.on_hide()
            else:
                self.screen.destroy()  # also cancels the screen's pending `after` jobs
            self.screen = None
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        screen = self._persistent.get(name)
        if screen is None:
            screen = SCREENS[name](self)
            screen.pack(fill="both", expand=True, padx=SCREEN_PADX, pady=SCREEN_PADY)
            self.screen = screen
            screen.build()
            if screen.persistent:
                self._persistent[name] = screen
        else:
            screen.pack(fill="both", expand=True, padx=SCREEN_PADX, pady=SCREEN_PADY)
            self.screen = screen
        self.navbar.set_active(screen.tab or screen.name)
        self.navbar.refresh_badges()
        screen.on_show()
        log.debug("Screen: %s", name)

    def finish_setup(self):
        """The setup screen installed every component: continue to the app."""
        self.navbar.pack(side="bottom", fill="x")
        self.show_screen("home")

    # Kept for UI automation scripts (hq/tools/snap.py --script).
    def _show_home(self):
        self.show_screen("home")

    def _show_youtube(self):
        self.show_screen("youtube")

    def _show_instagram(self):
        self.show_screen("instagram")

    def _show_downloads(self):
        self.show_screen("downloads")

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def active_download_count(self):
        return self.downloads.active_count()

    def has_active_downloads(self):
        """Used by the settings screen before an engine restart."""
        return self.downloads.active_count() > 0

    def _load_history(self):
        try:
            self.downloads.load_history()
        except Exception:
            log.exception("Could not load the download history")

    def _on_job_event(self, kind, payload):
        # Any thread: hand the event to the UI thread.
        self.ui_queue.put((_JOB_EVENT, kind, payload))

    def _dispatch_job_events(self, events):
        # A progress snapshot is superseded by any later event of the same job in this batch.
        latest = {}
        for index, (kind, payload) in enumerate(events):
            if kind in ("added", "updated", "progress"):
                latest[payload.id] = index
        receivers = [s for s in self._persistent.values()]
        if self.screen is not None and self.screen not in receivers:
            receivers.append(self.screen)
        for index, (kind, payload) in enumerate(events):
            if kind == "progress" and latest.get(payload.id) != index:
                continue
            for screen in receivers:
                try:
                    screen.on_job_event(kind, payload)
                except Exception:
                    log.exception("Error handling job event %r in %s", kind, screen.name)
        self.navbar.refresh_badges()

    # ------------------------------------------------------------------
    # Worker -> UI messages
    # ------------------------------------------------------------------

    def post_message(self, screen, kind, *args):
        """Thread-safe. Delivered on the UI thread only if `screen` is still displayed (or persistent)."""
        self.ui_queue.put((screen, kind, args))

    def _poll_queue(self):
        job_events = []
        try:
            while True:
                screen, kind, args = self.ui_queue.get_nowait()
                if screen is _JOB_EVENT:
                    job_events.append((kind, args))
                    continue
                if job_events:
                    self._dispatch_job_events(job_events)
                    job_events = []
                visible = screen is self.screen or (screen.persistent and screen in self._persistent.values())
                if not visible or not screen.winfo_exists():
                    continue  # the screen that asked is gone; drop stale results
                try:
                    screen.handle_message(kind, args)
                except Exception:
                    log.exception("Error handling %s message %r", screen.name, kind)
        except queue.Empty:
            pass
        if job_events:
            self._dispatch_job_events(job_events)
        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_queue)

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _on_close(self, force=False):
        """Ask if downloads are still running; then cancel them, let them clean up, and exit."""
        if self._closing:
            return
        active = self.downloads.active_count()
        if active and not force:
            if not messagebox.askyesno(
                APP_NAME, f"{active} indirme devam ediyor. Çıkılsın mı?\n"
                          "Devam eden indirmeler iptal edilir.",
                icon="warning", parent=self,
            ):
                return
        self._closing = True
        self.downloads.cancel_all()
        workers = self.downloads.threads()
        for screen in {*self._persistent.values(), self.screen} - {None}:
            workers += screen.shutdown()
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
        self.downloads.close()  # flush history writes
        for screen in {*self._persistent.values(), self.screen} - {None}:
            screen.destroy()
        self.screen = None
        self._persistent.clear()
        self.destroy()
