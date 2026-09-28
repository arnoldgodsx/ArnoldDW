import errno

import pytest

from arnold_dw.core.platforms.errors import (
    MESSAGES,
    DownloadCancelled,
    ErrorCode,
    PlatformError,
    classify_message,
    to_platform_error,
)


@pytest.mark.parametrize(
    "message,code",
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", ErrorCode.PRIVATE),
        ("ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate for some users.",
         ErrorCode.AGE_RESTRICTED),
        ("ERROR: [TikTok] 123: Your IP address is blocked from accessing this post", ErrorCode.GEO_BLOCKED),
        ("The uploader has not made this video available in your country", ErrorCode.GEO_BLOCKED),
        ("ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies", ErrorCode.LOGIN_REQUIRED),
        ("TikTok is requiring login for access to this content", ErrorCode.LOGIN_REQUIRED),
        ("ERROR: Unsupported URL: https://example.com/", ErrorCode.UNSUPPORTED),
        ("ERROR: [twitter] 1: No video could be found in this tweet", ErrorCode.NO_MEDIA),
        ("ERROR: [youtube] abc: Video unavailable", ErrorCode.NOT_FOUND),
        ("ERROR: [dailymotion] x: Not found.", ErrorCode.NOT_FOUND),
        ("HTTP Error 404: Not Found", ErrorCode.NOT_FOUND),
        ("HTTP Error 429: Too Many Requests", ErrorCode.RATE_LIMITED),
        ("Read timed out. (read timeout=15)", ErrorCode.TIMEOUT),
        ("Failed to resolve 'player.vimeo.com' ([Errno 11001] getaddrinfo failed)", ErrorCode.NETWORK),
        ("HTTP Error 503: Service Unavailable", ErrorCode.NETWORK),
        ("ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install", ErrorCode.FFMPEG_MISSING),
        ("[WinError 5] Access is denied: 'C:\\\\Windows\\\\x.mp4'", ErrorCode.PERMISSION),
        ("[Errno 28] No space left on device", ErrorCode.DISK_FULL),
        ("[WinError 3] The system cannot find the path specified", ErrorCode.PATH_MISSING),
        ("ERROR: unable to download video data: HTTP Error 403: Forbidden", ErrorCode.FORBIDDEN),
        ("something completely different", ErrorCode.UNKNOWN),
    ],
)
def test_classify_message(message, code):
    assert classify_message(message) is code


def test_every_code_has_a_turkish_message():
    assert set(MESSAGES) == set(ErrorCode)
    assert all(msg.strip() for msg in MESSAGES.values())


def test_platform_error_passthrough_and_fields():
    err = PlatformError(ErrorCode.PRIVATE, "detail text")
    assert to_platform_error(err) is err
    assert err.user_message == MESSAGES[ErrorCode.PRIVATE]
    assert "detail text" in str(err)
    custom = PlatformError(ErrorCode.UNKNOWN, user_message="Özel mesaj")
    assert custom.user_message == "Özel mesaj"


def test_ytdlp_download_cancelled_maps_to_cancelled():
    import yt_dlp

    mapped = to_platform_error(yt_dlp.utils.DownloadCancelled("user"))
    assert isinstance(mapped, DownloadCancelled)
    assert mapped.code is ErrorCode.CANCELLED


@pytest.mark.parametrize(
    "err_no,code",
    [(errno.ENOSPC, ErrorCode.DISK_FULL), (errno.EACCES, ErrorCode.PERMISSION), (errno.ENOENT, ErrorCode.PATH_MISSING)],
)
def test_oserror_by_errno(err_no, code):
    assert to_platform_error(OSError(err_no, "x")).code is code


def test_generic_exception_keeps_detail():
    mapped = to_platform_error(ValueError("weird"))
    assert mapped.code is ErrorCode.UNKNOWN
    assert "ValueError" in mapped.detail


@pytest.mark.parametrize(
    "status,code",
    [(403, ErrorCode.FORBIDDEN), (404, ErrorCode.NOT_FOUND), (410, ErrorCode.NOT_FOUND),
     (429, ErrorCode.RATE_LIMITED), (502, ErrorCode.NETWORK)],
)
def test_http_status_codes(status, code):
    class Resp:
        status_code = status

    class HTTPError(Exception):
        response = Resp()

    assert to_platform_error(HTTPError("boom")).code is code
