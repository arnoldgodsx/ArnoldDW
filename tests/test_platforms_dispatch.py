import pytest

import arnold_dw.core.platforms as platforms
from arnold_dw.core.platforms import ErrorCode, MediaItem, Platform, PlatformError


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(platforms.youtube_playlist, "open_playlist", lambda url, **kw: seen.append(("pl", url)))
    monkeypatch.setattr(platforms.generic, "resolve", lambda url, **kw: seen.append(("gen", url)))
    monkeypatch.setattr(platforms.generic, "download", lambda t, o, **kw: seen.append(("gen-dl", t)) or ["f"])
    return seen


@pytest.mark.parametrize(
    "text,engine",
    [
        ("https://www.youtube.com/playlist?list=PL590L5WQmH8fJ54F369BLDSqIwcs-TCfs", "pl"),
        ("https://www.youtube.com/@NASA", "pl"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "gen"),
        ("https://clips.twitch.tv/FaintLightGullWholeWheat", "gen"),
    ],
)
def test_resolve_dispatch(calls, text, engine):
    platforms.resolve(text)
    assert calls[0][0] == engine


@pytest.mark.parametrize(
    "text,code",
    [
        ("https://www.instagram.com/p/C1a2B3c4D5e/", ErrorCode.UNSUPPORTED),
        ("https://example.com/", ErrorCode.UNSUPPORTED),
        ("link yok", ErrorCode.INVALID_LINK),
    ],
)
def test_resolve_rejections(calls, text, code):
    with pytest.raises(PlatformError) as err:
        platforms.resolve(text)
    assert err.value.code is code
    assert calls == []


def test_download_dispatch(calls):
    opts = platforms.DownloadOptions(output_dir="out")
    platforms.download(MediaItem(id="1", url="u", platform=Platform.YOUTUBE), opts)
    platforms.download("https://clips.twitch.tv/FaintLightGullWholeWheat", opts)
    assert [c[0] for c in calls] == ["gen-dl", "gen-dl"]
    with pytest.raises(PlatformError):
        platforms.download(MediaItem(id="1", url="u", platform=Platform.INSTAGRAM_POST), opts)
