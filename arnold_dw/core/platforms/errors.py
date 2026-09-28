"""Errors raised by platform engines, with user-facing Turkish messages.

Engines never leak raw yt-dlp/requests exceptions: they raise ``PlatformError``
whose ``user_message`` can be shown as-is, while ``detail`` keeps the technical
text for the log file.
"""

from __future__ import annotations

import errno
from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_LINK = "invalid_link"
    UNSUPPORTED = "unsupported"
    EXPIRED_LINK = "expired_link"
    NOT_FOUND = "not_found"
    PRIVATE = "private"
    LOGIN_REQUIRED = "login_required"
    AGE_RESTRICTED = "age_restricted"
    GEO_BLOCKED = "geo_blocked"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NO_MEDIA = "no_media"
    TIMEOUT = "timeout"
    NETWORK = "network"
    FFMPEG_MISSING = "ffmpeg_missing"
    PERMISSION = "permission"
    DISK_FULL = "disk_full"
    PATH_MISSING = "path_missing"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_LINK: "Bağlantı tanınmadı. Linki kontrol edin.",
    ErrorCode.UNSUPPORTED: "Bu site veya bağlantı türü desteklenmiyor.",
    ErrorCode.EXPIRED_LINK: "Kısa bağlantı geçersiz veya süresi dolmuş. Uygulamadan linki yeniden kopyalayın.",
    ErrorCode.NOT_FOUND: "İçerik bulunamadı veya kaldırılmış.",
    ErrorCode.PRIVATE: "Bu içerik gizli, indirilemez.",
    ErrorCode.LOGIN_REQUIRED: "Bu içeriğe erişmek için giriş yapmak gerekiyor.",
    ErrorCode.AGE_RESTRICTED: "Bu içerik yaş sınırlaması nedeniyle indirilemiyor.",
    ErrorCode.GEO_BLOCKED: "Bu içerik bulunduğunuz bölgede erişilemiyor.",
    ErrorCode.RATE_LIMITED: "Site çok fazla istek algıladı. Biraz bekleyip tekrar deneyin.",
    ErrorCode.FORBIDDEN: "Site bu içeriğe erişimi reddetti. Biraz sonra tekrar deneyin.",
    ErrorCode.NO_MEDIA: "Bu bağlantıda indirilebilir bir medya bulunamadı.",
    ErrorCode.TIMEOUT: "Bağlantı zaman aşımına uğradı. Tekrar deneyin.",
    ErrorCode.NETWORK: "İnternet bağlantısı sorunu tespit edildi.",
    ErrorCode.FFMPEG_MISSING: "Dönüştürme aracı (ffmpeg) bulunamadı. Uygulamayı yeniden kurmayı deneyin.",
    ErrorCode.PERMISSION: "Seçilen klasöre yazma izni yok. Başka bir klasör seçin.",
    ErrorCode.DISK_FULL: "Diskte yeterli boş alan yok.",
    ErrorCode.PATH_MISSING: "Seçilen indirme klasörü bulunamadı.",
    ErrorCode.CANCELLED: "İndirme iptal edildi.",
    ErrorCode.UNKNOWN: "Bir hata oluştu. Lütfen bağlantıyı kontrol edip tekrar deneyin.",
}


class PlatformError(Exception):
    def __init__(self, code: ErrorCode, detail: str = "", user_message: str | None = None):
        self.code = code
        self.detail = detail
        self.user_message = user_message or MESSAGES[code]
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


class DownloadCancelled(PlatformError):
    def __init__(self, detail: str = ""):
        super().__init__(ErrorCode.CANCELLED, detail)


# Ordered: the first matching rule wins, so more specific phrases come first.
_RULES: tuple[tuple[ErrorCode, tuple[str, ...]], ...] = (
    (ErrorCode.CANCELLED, ("downloadcancelled", "cancelled by user", "iptal edildi")),
    (ErrorCode.FFMPEG_MISSING, ("ffmpeg not found", "ffprobe not found", "ffmpeg is not installed",
                                "ffprobe and ffmpeg not found")),
    (ErrorCode.AGE_RESTRICTED, ("age-restricted", "age restricted", "confirm your age", "inappropriate for some users")),
    (ErrorCode.PRIVATE, ("private video", "this video is private", "is private", "private post",
                         "private account", "permission to view this post")),
    (ErrorCode.GEO_BLOCKED, ("available in your country", "geo restrict", "geo-restrict",
                             "ip address is blocked", "not available in your region", "blocked it in your country")),
    (ErrorCode.RATE_LIMITED, ("http error 429", "too many requests", "rate limit", "ratelimit")),
    (ErrorCode.LOGIN_REQUIRED, ("sign in", "login required", "log in", "logged-in", "requiring login",
                                "use --cookies", "account credentials", "members-only", "join this channel")),
    (ErrorCode.UNSUPPORTED, ("unsupported url", "is not a valid url", "no suitable extractor")),
    (ErrorCode.NO_MEDIA, ("no video could be found", "no video formats found", "requested format is not available",
                          "no media found", "does not contain any video")),
    (ErrorCode.NOT_FOUND, ("http error 404", "video unavailable", "not found", "has been removed", "does not exist",
                           "no longer available", "is unavailable", "video not available", "deleted")),
    (ErrorCode.FORBIDDEN, ("http error 403", "403 forbidden", "403 client error")),
    (ErrorCode.DISK_FULL, ("no space left", "errno 28", "winerror 112", "not enough space")),
    (ErrorCode.PERMISSION, ("permission denied", "winerror 5", "errno 13", "access is denied")),
    (ErrorCode.PATH_MISSING, ("no such file or directory", "cannot find the path", "winerror 3")),
    (ErrorCode.TIMEOUT, ("timed out", "timeout")),
    (ErrorCode.NETWORK, ("network", "connection", "resolve host", "getaddrinfo", "name or service not known",
                         "temporary failure in name resolution", "ssl", "remote end closed", "http error 5")),
)


def classify_message(message: str) -> ErrorCode:
    low = message.lower()
    for code, needles in _RULES:
        if any(n in low for n in needles):
            return code
    return ErrorCode.UNKNOWN


def to_platform_error(exc: BaseException) -> PlatformError:
    """Map any exception raised while resolving/downloading to a ``PlatformError``."""
    if isinstance(exc, PlatformError):
        return exc
    if exc.__class__.__name__ == "DownloadCancelled":
        return DownloadCancelled(str(exc))
    if isinstance(exc, OSError) and exc.errno is not None:
        by_errno = {
            errno.ENOSPC: ErrorCode.DISK_FULL,
            errno.EACCES: ErrorCode.PERMISSION,
            errno.EPERM: ErrorCode.PERMISSION,
            errno.ENOENT: ErrorCode.PATH_MISSING,
        }
        if exc.errno in by_errno:
            return PlatformError(by_errno[exc.errno], str(exc))
    detail = f"{exc.__class__.__name__}: {exc}"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        by_status = {403: ErrorCode.FORBIDDEN, 404: ErrorCode.NOT_FOUND, 410: ErrorCode.NOT_FOUND,
                     429: ErrorCode.RATE_LIMITED}
        if status in by_status:
            return PlatformError(by_status[status], detail)
        if status >= 500:
            return PlatformError(ErrorCode.NETWORK, detail)
    return PlatformError(classify_message(str(exc)), detail)
