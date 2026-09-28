"""Exceptions shared by the engine and user-facing (Turkish) error messages."""


class DownloadCancelled(Exception):
    """The user cancelled a running download (raised from inside the worker)."""


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
    low = str(exc).lower()
    if "profile does not exist" in low or "not found" in low:
        return "Instagram kullanıcısı veya gönderisi bulunamadı."
    if "private profile" in low or "is private" in low:
        return "Bu hesap gizli. Yalnızca profil fotoğrafı kullanılabilir."
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
