"""Create a privacy-scrubbed support archive for troubleshooting."""

import importlib.metadata
import os
import re
import subprocess
import sys
import zipfile
from datetime import date

from arnold_dw import __version__, paths

MAX_LOG_BYTES = 5 * 1024 * 1024
_SENSITIVE = re.compile(
    r"(?i)(\b(?:cookie|set-cookie|authorization|proxy-authorization)\s*:\s*)"
    r"[^\r\n]+|"
    r"([\"']?\b(?:token|sessionid|session_id|password|passwd|secret|sig|signature)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}&]+)"
)
_URL_QUERY = re.compile(r"(https?://[^\s\"'<>?]+\?)[^\s\"'<>#]+", re.I)


def _mask_text(value, username=None):
    text = str(value)
    if username:
        text = re.sub(re.escape(username), "<user>", text, flags=re.I)
    text = _URL_QUERY.sub(r"\1<redacted>", text)
    return _SENSITIVE.sub(lambda match: (match.group(1) or match.group(2)) + "<redacted>", text)


def _windows_version():
    """Read Windows release details from the registry (avoids PE-based version APIs)."""
    if os.name != "nt":
        return "Unavailable (not Windows)"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            fields = ("ProductName", "DisplayVersion", "CurrentBuild", "UBR")
            values = []
            for field in fields:
                try:
                    values.append(f"{field}={winreg.QueryValueEx(key, field)[0]}")
                except OSError:
                    pass
        return "; ".join(values) or "Unknown Windows version"
    except Exception as exc:
        return f"Unavailable ({type(exc).__name__})"


def _dpi_info():
    if os.name != "nt":
        return "Unavailable (not Windows)"
    try:
        import ctypes

        dpi = ctypes.windll.user32.GetDpiForSystem()
        return f"{dpi} DPI ({dpi / 96 * 100:.0f}%)"
    except Exception:
        return "Unavailable"


def _package_version(name):
    try:
        if name == "yt-dlp":
            import yt_dlp

            return yt_dlp.version.__version__
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"


def _ffmpeg_info():
    executable = paths.FFMPEG_PATH if os.path.isfile(paths.FFMPEG_PATH) else "ffmpeg"
    try:
        result = subprocess.run([executable, "-version"], capture_output=True, text=True,
                                timeout=3, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        first_line = (result.stdout or result.stderr).splitlines()[0]
        return f"{executable} ({first_line})"
    except Exception as exc:
        return f"{executable} (unavailable: {type(exc).__name__})"


def _system_report(username):
    try:
        from arnold_dw import config

        config_path = config.config_path()
    except Exception:
        config_path = paths.config_path()

    lines = [
        f"Arnold DW: {__version__}",
        f"yt-dlp: {_package_version('yt-dlp')}",
        f"ffmpeg: {_ffmpeg_info()}",
        f"Python: {sys.version.split()[0]} ({sys.executable})",
        f"Windows: {_windows_version()}",
        f"Display scaling: {_dpi_info()}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
    ]
    return "\n".join(_mask_text(line, username) for line in lines).encode("utf-8"), config_path


def _recent_log_bytes(log_paths, limit=MAX_LOG_BYTES):
    """Collect newest log bytes first, respecting one aggregate size limit."""
    remaining = limit
    collected = []
    for path in sorted(log_paths, key=lambda item: os.path.getmtime(item), reverse=True):
        if remaining <= 0:
            break
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as stream:
                stream.seek(max(0, size - remaining))
                data = stream.read(remaining)
            if size > len(data):
                data = b"[Earlier log content omitted to enforce 5 MB limit]\n" + data
            username = os.path.basename(os.path.expanduser("~"))
            scrubbed = _mask_text(data.decode("utf-8", errors="replace"), username).encode("utf-8")
            if len(scrubbed) > remaining:
                scrubbed = scrubbed[-remaining:]
            collected.append((os.path.basename(path), scrubbed))
            remaining -= len(scrubbed)
        except OSError:
            continue
    return collected


def build_report(dest_dir):
    """Write and return the path to a timestamped diagnostics ZIP archive."""
    os.makedirs(dest_dir, exist_ok=True)
    username = os.path.basename(os.path.expanduser("~"))
    system_text, settings_path = _system_report(username)
    logs = []
    try:
        logs = [os.path.join(paths.log_dir(), name) for name in os.listdir(paths.log_dir())
                if name.lower().endswith(".log") and os.path.isfile(os.path.join(paths.log_dir(), name))]
    except OSError:
        pass

    report_path = os.path.join(dest_dir, f"ArnoldDW-rapor-{date.today():%Y-%m-%d}.zip")
    with zipfile.ZipFile(report_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.txt", system_text)
        try:
            with open(settings_path, encoding="utf-8") as stream:
                settings = stream.read()
        except OSError:
            settings = "{}"
        archive.writestr("settings.json", _mask_text(settings, username))
        for name, data in _recent_log_bytes(logs):
            archive.writestr(f"logs/{name}", data)
    return report_path
