import pytest

from arnold_dw.core.errors import (
    InstagramCookieError,
    InstagramRateLimited,
    InstagramSessionRequired,
    friendly_error,
    instagram_friendly_error,
)

GENERIC = "Bir hata oluştu. Lütfen bağlantıyı kontrol edip tekrar deneyin."
IG_GENERIC = "Instagram içeriği alınamadı. Linki veya kullanıcı adını kontrol edin."


@pytest.mark.parametrize("message, expected", [
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access",
     "Bu video gizli, indirilemez."),
    ("ERROR: [youtube] abc: Video unavailable", "Video artık mevcut değil."),
    ("This video is age-restricted", "Bu video yaş sınırlaması nedeniyle indirilemiyor."),
    ("Sign in to confirm you're not a bot", "Bu videoya erişim için giriş gerekiyor."),
    ("login required", "Bu videoya erişim için giriş gerekiyor."),
    ("ERROR: Unsupported URL: https://example.com", "Bağlantı çözümlenemedi. Linki kontrol edin."),
    ("Unable to extract initial player response", "Bağlantı çözümlenemedi. Linki kontrol edin."),
    ("The read operation timed out", "Bağlantı zaman aşımına uğradı. Tekrar deneyin."),
    ("[Errno 13] Permission denied: 'C:\\x'", "Seçilen klasöre yazma izni yok. Başka bir klasör seçin."),
    ("[WinError 5] Access is denied", "Seçilen klasöre yazma izni yok. Başka bir klasör seçin."),
    ("[WinError 3] The system cannot find the path specified", "Seçilen indirme klasörü bulunamadı."),
    ("[Errno 28] No space left on device", "Diskte yeterli boş alan yok."),
    ("[WinError 112] There is not enough space on the disk", "Diskte yeterli boş alan yok."),
    ("Failed to resolve host www.youtube.com", "İnternet bağlantısı sorunu tespit edildi."),
    ("Connection reset by peer", "İnternet bağlantısı sorunu tespit edildi."),
    ("something odd", GENERIC),
    ("", GENERIC),
])
def test_friendly_error(message, expected):
    assert friendly_error(Exception(message)) == expected


@pytest.mark.parametrize("message, expected", [
    ("Profile does not exist: foo", "Instagram kullanıcısı veya gönderisi bulunamadı."),
    ("404 Client Error: Not Found", "Instagram kullanıcısı veya gönderisi bulunamadı."),
    ("Profile foo is private", "Bu hesap gizli. Bu hesabı takip etmiyorsanız içerik indirilemez."),
    ("Profile foo: private but not followed.",
     "Bu hesap gizli. Bu hesabı takip etmiyorsanız içerik indirilemez."),
    ("Login required", "Bu içeriğe oturum açmadan erişilemiyor."),
    ("401 Unauthorized", "Bu içeriğe oturum açmadan erişilemiyor."),
    ("429 Too Many Requests",
     "Instagram geçici olarak çok fazla istek algıladı. Biraz sonra deneyin."),
    ("Please wait a few minutes before you try again.",
     "Instagram geçici olarak çok fazla istek algıladı. Biraz sonra deneyin."),
    ('JSON Query to graphql/query: 401 Unauthorized - "fail" status, message "Please wait a few '
     'minutes before you try again." when accessing https://www.instagram.com/graphql/query',
     "Instagram geçici olarak çok fazla istek algıladı. Biraz sonra deneyin."),
    ("Connection aborted", "Instagram bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin."),
    ("Read timeout", "Instagram bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin."),
    ("Invalid Instagram username", IG_GENERIC),
])
def test_instagram_friendly_error(message, expected):
    assert instagram_friendly_error(Exception(message)) == expected


def test_instagram_rate_limited_reports_minutes_remaining():
    assert instagram_friendly_error(InstagramRateLimited(61)) == (
        "Instagram geçici olarak çok fazla istek algıladı. Yaklaşık 2 dakika sonra tekrar deneyin."
    )
    assert instagram_friendly_error(InstagramRateLimited(300)) == (
        "Instagram geçici olarak çok fazla istek algıladı. Yaklaşık 5 dakika sonra tekrar deneyin."
    )


@pytest.mark.parametrize("browser, expected", [
    ("chrome", "Chrome oturumu okunamadı — Firefox veya Edge deneyin."),
    ("firefox", "Firefox tarayıcı oturumu okunamadı. Başka bir tarayıcı deneyin."),
    ("edge", "Edge tarayıcı oturumu okunamadı. Başka bir tarayıcı deneyin."),
    ("brave", "Brave tarayıcı oturumu okunamadı. Başka bir tarayıcı deneyin."),
])
def test_instagram_cookie_error_by_browser(browser, expected):
    assert instagram_friendly_error(InstagramCookieError(browser)) == expected


def test_instagram_session_required_message():
    assert "Tarayıcı oturumumu kullan" in instagram_friendly_error(InstagramSessionRequired())
