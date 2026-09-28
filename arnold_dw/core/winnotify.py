"""Small dependency-free Windows notification-area balloon implementation."""

import ctypes
import logging
import os
import threading
from ctypes import wintypes

from arnold_dw import paths

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = "ArnoldDW.YoutubeDownloader.1"
_WM_APP = 0x8000
_WM_NOTIFY = _WM_APP + 1
_WM_SHOW = _WM_APP + 2
_WM_CLEANUP = _WM_APP + 3
_NIM_ADD, _NIM_MODIFY, _NIM_DELETE = 0, 1, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP, _NIF_INFO = 1, 2, 4, 0x10
_NIN_BALLOONHIDE, _NIN_BALLOONTIMEOUT, _NIN_BALLOONUSERCLICK = 0x402, 0x403, 0x405
_WM_TIMER = 0x113
_TIMER_ID = 1


class _NotifyIconData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256), ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON),
    ]


def _truncate(text, limit):
    return str(text).replace("\x00", " ")[:limit - 1]


class _WindowsNotifier:
    def __init__(self):
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread = None
        self._thread_id = 0
        self._hwnd = None
        self._callbacks = {}
        self._next_id = 1
        self._icon = None
        self._icon_owned = False
        self._wndproc = None

    def show(self, title, body, callback):
        if os.name != "nt":
            return False
        try:
            self._ensure_thread()
            if not self._ready.wait(3) or not self._hwnd:
                return False
            with self._lock:
                icon_id = self._next_id
                self._next_id = 1 if icon_id >= 0x7FFFFFFF else icon_id + 1
                self._callbacks[icon_id] = callback
            result = threading.Event()
            # Retain the request object until the UI thread has handled it.
            request = {"id": icon_id, "title": title, "body": body, "result": result}
            with self._lock:
                self._requests[icon_id] = request
            ctypes.windll.user32.PostMessageW(self._hwnd, _WM_SHOW, icon_id, 0)
            return result.wait(3) and request.get("success", False)
        except Exception:
            log.debug("Windows notification could not be shown", exc_info=True)
            return False

    def _ensure_thread(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._requests = {}
            self._thread = threading.Thread(target=self._run, name="ArnoldDW-notifications", daemon=True)
            self._thread.start()

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        self._thread_id = kernel32.GetCurrentThreadId()
        user32.RegisterClassW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                           wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.SetTimer.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
        ctypes.windll.shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                                            ctypes.POINTER(_NotifyIconData)]
        ctypes.windll.shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        @ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                            wintypes.WPARAM, wintypes.LPARAM)
        def wndproc(hwnd, message, wparam, lparam):
            if message == _WM_SHOW:
                self._show_request(int(wparam))
                return 0
            if message == _WM_NOTIFY:
                code = int(lparam) & 0xFFFFFFFF
                icon_id = int(wparam)
                if code == _NIN_BALLOONUSERCLICK:
                    callback = self._callbacks.get(icon_id)
                    if callback:
                        try:
                            callback()
                        except Exception:
                            log.exception("Notification click callback failed")
                if code in (_NIN_BALLOONHIDE, _NIN_BALLOONTIMEOUT, _NIN_BALLOONUSERCLICK):
                    self._delete_icon(icon_id)
                return 0
            if message == _WM_TIMER and wparam == _TIMER_ID:
                user32.KillTimer(hwnd, _TIMER_ID)
                self._delete_all_icons()
                return 0
            if message == 0x0002:  # WM_DESTROY
                self._delete_all_icons()
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._wndproc = wndproc
        class_name = "ArnoldDW.NotificationWindow"

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        instance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(0, ctypes.cast(wndproc, ctypes.c_void_p), 0, 0, instance,
                       None, None, None, None, class_name)
        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom and ctypes.GetLastError() != 1410:  # class already registered
            self._ready.set()
            return
        self._hwnd = user32.CreateWindowExW(0, class_name, class_name, 0, 0, 0, 0, 0,
                                           None, None, instance, None)
        self._ready.set()
        if not self._hwnd:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_request(self, icon_id):
        request = self._requests.pop(icon_id, None)
        if request is None:
            return
        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
            user32.LoadIconW.restype = wintypes.HICON
            icon = user32.LoadImageW(None, paths.ICON_PATH, 1, 0, 0, 0x10) if os.path.isfile(paths.ICON_PATH) else None
            self._icon_owned = bool(icon)
            if not icon:
                icon = user32.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))
            self._icon = icon
            data = _NotifyIconData()
            data.cbSize = ctypes.sizeof(data)
            data.hWnd = self._hwnd
            data.uID = icon_id
            data.uFlags = _NIF_ICON | _NIF_MESSAGE | _NIF_TIP
            data.uCallbackMessage = _WM_NOTIFY
            data.hIcon = icon
            data.szTip = "Arnold DW"
            if not shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(data)):
                request["success"] = False
                return
            data.uFlags = _NIF_INFO
            data.szInfoTitle = _truncate(request["title"], 64)
            data.szInfo = _truncate(request["body"], 256)
            data.dwInfoFlags = 1  # NIIF_INFO
            request["success"] = bool(shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(data)))
            if not request["success"]:
                self._delete_icon(icon_id)
            else:
                user32.SetTimer(self._hwnd, _TIMER_ID, 30000, None)
        except Exception:
            request["success"] = False
            log.debug("Windows notification API failed", exc_info=True)
        finally:
            request["result"].set()

    def _delete_icon(self, icon_id):
        try:
            data = _NotifyIconData()
            data.cbSize = ctypes.sizeof(data)
            data.hWnd = self._hwnd
            data.uID = icon_id
            ctypes.windll.shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(data))
        except Exception:
            pass
        self._callbacks.pop(icon_id, None)
        if not self._callbacks and self._icon and self._icon_owned:
            try:
                user32 = ctypes.windll.user32
                user32.DestroyIcon.argtypes = [wintypes.HICON]
                user32.DestroyIcon.restype = wintypes.BOOL
                user32.DestroyIcon(self._icon)
            except Exception:
                pass
            self._icon = None
            self._icon_owned = False

    def _delete_all_icons(self):
        for icon_id in list(self._callbacks):
            self._delete_icon(icon_id)


_notifier = _WindowsNotifier()


def _is_app_foreground():
    if os.name != "nt":
        return True
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return process_id.value == os.getpid()
    except Exception:
        return False


def notify(title, body, on_click=None):
    """Show a balloon only while Arnold DW is in the background. Never raises."""
    try:
        if os.name != "nt" or _is_app_foreground():
            return False
        callback = on_click if callable(on_click) else None
        return bool(_notifier.show(_truncate(title, 64), _truncate(body, 256), callback))
    except Exception:
        log.debug("Notification unavailable", exc_info=True)
        return False
