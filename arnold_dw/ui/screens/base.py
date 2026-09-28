"""Base class for screens: lifecycle, worker threads and UI-queue messaging."""

import logging
import threading

import customtkinter as ctk

from arnold_dw.ui.afterjobs import AfterJobsMixin
from arnold_dw.ui.theme import BG

log = logging.getLogger(__name__)


class Screen(AfterJobsMixin, ctk.CTkFrame):
    """One full-window screen.

    Lifecycle: the window creates the screen, packs it, then calls build().
    Leaving the screen destroys it, which cancels every job started with
    schedule(). Worker threads talk back only through post(); the window
    delivers a message to `on_<kind>(*args)` on the UI thread, and only while
    this screen instance is still the one on display.
    """

    name = ""

    def __init__(self, app):
        super().__init__(app, fg_color=BG)
        self.app = app
        self._workers = []

    def build(self):
        raise NotImplementedError

    # --- threading --------------------------------------------------------

    def post(self, kind, *args):
        """Thread-safe: queue a message for this screen's `on_<kind>` handler."""
        self.app.post_message(self, kind, *args)

    def handle_message(self, kind, args):
        handler = getattr(self, f"on_{kind}", None)
        if handler is None:
            log.error("%s has no handler for message %r", type(self).__name__, kind)
            return
        handler(*args)

    def start_worker(self, target, *args, track=False):
        """Run `target(*args)` on a daemon thread. Tracked workers are awaited on app close."""
        thread = threading.Thread(target=target, args=args, daemon=True,
                                  name=f"{self.name}-{target.__name__}")
        if track:
            self._workers = [t for t in self._workers if t.is_alive()]
            self._workers.append(thread)
        thread.start()
        return thread

    # --- lifecycle hooks ----------------------------------------------------

    def is_busy(self):
        """True while leaving the screen would abandon running work."""
        return False

    def shutdown(self):
        """App is closing: signal running work to stop. Returns threads worth waiting for."""
        return [t for t in self._workers if t.is_alive()]
