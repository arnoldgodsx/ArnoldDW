"""Daily background check for a newer yt-dlp engine.

It only looks: installing is always the user's decision (Settings -> engine update). The
result is kept on a process-wide :data:`notifier`, so any screen built later can show it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from . import ytdlp_updater

log = logging.getLogger(__name__)

CHECK_INTERVAL = 24 * 60 * 60
STARTUP_DELAY = 10.0
NOTICE_TEXT = "Motor güncellemesi var · Ayarlar"


def should_check(auto_check: bool, last_check: float, now: float, interval: float = CHECK_INTERVAL) -> bool:
    """Whether the background check is due (at most once per ``interval``)."""
    if not auto_check:
        return False
    if last_check <= 0 or last_check > now:  # never checked, or the clock went back
        return True
    return now - last_check >= interval


class BackgroundCheck:
    """Runs one delayed update check per process and remembers what it found."""

    def __init__(self, check: Callable[..., object] | None = None, clock: Callable[[], float] = time.time):
        self._check = check or ytdlp_updater.check_for_update
        self._clock = clock
        self._lock = threading.Lock()
        self._started = False
        self._running = False
        self.result = None  # ytdlp_updater.UpdateInfo once an update was found

    @property
    def pending(self) -> bool:
        """True while a scheduled or running check has not finished yet."""
        return self._running

    def start(self, settings, save: Callable[[], object], delay: float = STARTUP_DELAY) -> bool:
        """Schedule the check if it is due. Idempotent; returns True if a check was scheduled.

        ``settings`` needs ``engine_auto_check``, ``engine_channel`` and ``last_engine_check``;
        ``save()`` persists them after a successful check.
        """
        with self._lock:
            if self._started:
                return False
            self._started = True
            if not should_check(settings.engine_auto_check, settings.last_engine_check, self._clock()):
                return False
            self._running = True
        timer = threading.Timer(delay, self._run, args=(settings, save))
        timer.daemon = True
        timer.name = "engine-autocheck"
        timer.start()
        return True

    def _run(self, settings, save) -> None:
        try:
            info = self._check(settings.engine_channel, raise_errors=True)
        except Exception as exc:
            # Try again on the next start; don't record the failed attempt as a check.
            log.info("background engine check failed: %s", exc)
        else:
            self.result = info
            settings.last_engine_check = self._clock()
            try:
                save()
            except Exception:
                log.exception("could not save the engine check time")
            if info is not None:
                log.info("engine update available: %s -> %s", info.current, info.version)
        finally:
            self._running = False

    def notice(self) -> str | None:
        """Text for the home screen notice line, or ``None`` when there is nothing to say."""
        return NOTICE_TEXT if self.result is not None else None

    def clear(self) -> None:
        """Forget the found update (installed, or superseded by a manual check)."""
        self.result = None


notifier = BackgroundCheck()
