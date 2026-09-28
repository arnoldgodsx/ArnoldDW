"""Exceptions shared by the engine and user-facing (Turkish) error messages."""

import math


class DownloadCancelled(Exception):
    """The user cancelled a running download (raised from inside the worker)."""


class InstagramRateLimited(Exception):
    """Instagram answered 429 / "please wait a few minutes": stop, no fallback method, no retry yet."""

    def __init__(self, retry_after_seconds: float = 0.0):
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(f"instagram rate limited, retry after {self.retry_after_seconds:.0f}s")


class InstagramCookieError(Exception):
    """A browser's Instagram session could not be read for ``cookiesfrombrowser``."""

    def __init__(self, browser: str, detail: str = ""):
        self.browser = browser
        super().__init__(detail or f"could not read {browser} cookies")


class InstagramSessionRequired(Exception):
    """Bulk profile download (posts/reels) needs the user's opted-in browser session."""


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "private video" in low:
        return "Bu video gizli, indirilemez."
    if "video unavailable" in low:
        return "Video artık mevcut değil."
    if "age" in low and "restrict" in low:
        return "Bu video yaş sınırlaması nedeniyle indirilemiyor."
    if "sign in" in low or "login" in low:
        return "Bu videoya erişim için giriş gerekiyor."
    if "unable to extract" in low or "unsupported url" in low:
        return "Bağlantı çözümlenemedi. Linki kontrol edin."
    if "timed out" in low or "timeout" in low:
        return "Bağlantı zaman aşımına uğradı. Tekrar deneyin."
    if "permission denied" in low or "winerror 5" in low:
        return "Seçilen klasöre yazma izni yok. Başka bir klasör seçin."
    if "no such file or directory" in low or "cannot find the path" in low or "winerror 3" in low:
        return "Seçilen indirme klasörü bulunamadı."
    if "no space left" in low or "winerror 112" in low:
        return "Diskte yeterli boş alan yok."
    if "network" in low or "connection" in low or "resolve host" in low:
        return "İnternet bağlantısı sorunu tespit edildi."
    return "Bir hata oluştu. Lütfen bağlantıyı kontrol edip tekrar deneyin."


def instagram_friendly_error(exc: Exception) -> str:
    # Typed first: these carry structured context a plain message match can't recover.
    if isinstance(exc, InstagramRateLimited):
        minutes = max(1, math.ceil(exc.retry_after_seconds / 60)) if exc.retry_after_seconds else 5
        return f"Instagram geçici olarak çok fazla istek algıladı. Yaklaşık {minutes} dakika sonra tekrar deneyin."
    if isinstance(exc, InstagramCookieError):
        if exc.browser == "chrome":
            return "Chrome oturumu okunamadı — Firefox veya Edge deneyin."
        name = {"firefox": "Firefox", "edge": "Edge", "brave": "Brave"}.get(exc.browser, exc.browser)
        return f"{name} tarayıcı oturumu okunamadı. Başka bir tarayıcı deneyin."
    if isinstance(exc, InstagramSessionRequired):
        return ("Bu içerik için tarayıcı oturumu gerekiyor. Profil ekranında "
                "\"Tarayıcı oturumumu kullan\" seçeneğini açın.")

    low = str(exc).lower()
    if "profile does not exist" in low or "not found" in low:
        return "Instagram kullanıcısı veya gönderisi bulunamadı."
    if "private" in low and ("not followed" in low or "is private" in low):
        return "Bu hesap gizli. Bu hesabı takip etmiyorsanız içerik indirilemez."
    # Rate limiting first: Instagram also sends it as `401 ... "Please wait a few minutes"`.
    if (
        "429" in low
        or "too many requests" in low
        or "please wait a few minutes" in low
    ):
        return "Instagram geçici olarak çok fazla istek algıladı. Biraz sonra deneyin."
    if "login" in low or "401" in low or "403" in low:
        return "Bu içeriğe oturum açmadan erişilemiyor."
    if "connection" in low or "network" in low or "timeout" in low:
        return "Instagram bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin."
    return "Instagram içeriği alınamadı. Linki veya kullanıcı adını kontrol edin."
