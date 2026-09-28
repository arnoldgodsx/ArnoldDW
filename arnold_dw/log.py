"""Rotating file log in %APPDATA%\\Arnold DW\\logs (the packaged exe has no console)."""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from arnold_dw import paths

LOG_FILENAME = "arnold_dw.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"

_log_path = None


def setup_logging(level=logging.INFO, directory=None):
    """Attach the rotating file handler to the root logger. Idempotent.

    Returns the log file path, or None when the log dir isn't writable (the
    app keeps running; records then only go to stderr when one exists).
    """
    global _log_path
    if _log_path is not None:
        return _log_path

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)

    directory = directory or paths.log_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, LOG_FILENAME)
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                      encoding="utf-8", delay=True)
    except OSError:
        path = None
        handler = None

    if handler is not None:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.WARNING)
        root.addHandler(console)

    _install_excepthooks()
    _log_path = path or ""
    return path


def _install_excepthooks():
    logger = logging.getLogger("arnold_dw.uncaught")

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        logger.critical("Uncaught exception in thread %s",
                        getattr(args.thread, "name", "?"),
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
