"""One running app per user data folder (Windows named mutex).

The first instance owns a mutex named after the AppData folder and tags its
main window with a window property carrying the same key. A second launch
finds the mutex taken, looks up the tagged window, brings it to the front and
exits. Keying on the data folder (not just the app name) keeps a test run
with a redirected %APPDATA% independent from the user's own instance.
"""

import logging
import sys
import time
import zlib

from arnold_dw import paths

log = logging.getLogger(__name__)

PROP_NAME = "ArnoldDW.InstanceKey"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
SW_SHOW = 5


def instance_key(data_dir=None):
    """Nonzero 31-bit key derived from the (case-insensitive) data folder."""
    data_dir = (data_dir or paths.config_dir()).lower().rstrip("\\/")
    return (zlib.crc32(data_dir.encode("utf-8")) & 0x7FFFFFFF) or 1


def mutex_name(key):
    return f"Local\\ArnoldDW-{key:08x}"


class InstanceLock:
    """Holds the mutex for the life of the process (or until release())."""

    def __init__(self, handle, key):
        self.handle = handle
        self.key = key

    def release(self):
        if self.handle and sys.platform == "win32":
            _kernel32().CloseHandle(self.handle)
        self.handle = None


def acquire(key=None):
    """InstanceLock if this is the first instance, None if another one is running."""
    key = key or instance_key()
    if sys.platform != "win32":
        return InstanceLock(None, key)
    import ctypes

    kernel32 = _kernel32()
    handle = kernel32.CreateMutexW(None, False, mutex_name(key))
    error = ctypes.get_last_error()
    if not handle:
        log.warning("CreateMutexW failed (%s); running without the single-instance guard", error)
        return InstanceLock(None, key)
    if error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return InstanceLock(handle, key)


def tag_window(hwnd, key):
    """Mark our top-level window so a second instance can find it."""
    if sys.platform != "win32" or not hwnd:
        return False
    return bool(_user32().SetPropW(hwnd, PROP_NAME, key))


def find_window(key):
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = _user32()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if user32.GetPropW(hwnd, PROP_NAME) == key:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def activate_existing(key=None, timeout=5.0):
    """Bring the running instance's window to the front. Returns True if it was found."""
    key = key or instance_key()
    deadline = time.monotonic() + timeout
    while True:
        hwnd = find_window(key)
        if hwnd:
            user32 = _user32()
            user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            return True
        # The first instance may still be starting up (mutex taken, window not yet tagged).
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


_dlls = {}


def _kernel32():
    if "kernel32" not in _dlls:
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        _dlls["kernel32"] = k
    return _dlls["kernel32"]


def _user32():
    if "user32" not in _dlls:
        import ctypes
        from ctypes import wintypes

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        u.SetPropW.restype = wintypes.BOOL
        u.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        u.GetPropW.restype = wintypes.HANDLE
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.IsIconic.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        _dlls["user32"] = u
    return _dlls["user32"]
