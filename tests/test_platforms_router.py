import pytest

from arnold_dw.core.platforms import router
from arnold_dw.core.platforms.models import Platform

YT = Platform.YOUTUBE
YTP = Platform.YOUTUBE_PLAYLIST
YTC = Platform.YOUTUBE_CHANNEL
IGP = Platform.INSTAGRAM_POST
IGU = Platform.INSTAGRAM_PROFILE
GEN = Platform.GENERIC
UNK = Platform.UNKNOWN

VID = "dQw4w9WgXcQ"
WATCH = f"https://www.youtube.com/watch?v={VID}"
PL = "PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG"
PL_URL = f"https://www.youtube.com/playlist?list={PL}"

# (pasted text, expected platform, expected canonical url or None to skip, expected media_id or None to skip)
CASES = [
    # --- YouTube single videos ---------------------------------------------------------
    (WATCH, YT, WATCH, VID),
    (f"https://youtube.com/watch?v={VID}", YT, WATCH, VID),
    (f"http://m.youtube.com/watch?v={VID}&feature=share", YT, WATCH, VID),
    (f"youtube.com/watch?v={VID}", YT, WATCH, VID),
    (f"www.youtube.com/watch?v={VID}", YT, WATCH, VID),
    (f"https://youtu.be/{VID}", YT, WATCH, VID),
    (f"https://youtu.be/{VID}?si=AbCdEfGh123&t=42", YT, WATCH, VID),
    (f"youtu.be/{VID}", YT, WATCH, VID),
    (f"https://www.youtube.com/shorts/{VID}", YT, f"https://www.youtube.com/shorts/{VID}", VID),
    (f"https://youtube.com/shorts/{VID}?feature=share", YT, f"https://www.youtube.com/shorts/{VID}", VID),
    (f"https://www.youtube.com/live/{VID}?si=x", YT, WATCH, VID),
    (f"https://www.youtube.com/embed/{VID}", YT, WATCH, VID),
    (f"https://www.youtube-nocookie.com/embed/{VID}?rel=0", YT, WATCH, VID),
    (f"https://music.youtube.com/watch?v={VID}&feature=share", YT, WATCH, VID),
    (f"https://www.youtube.com/watch?feature=youtu.be&v={VID}", YT, WATCH, VID),
    (f"HTTPS://WWW.YOUTUBE.COM/watch?v={VID}", YT, WATCH, VID),
    # --- dirty input ------------------------------------------------------------------
    (f"   {WATCH}   ", YT, WATCH, VID),
    (f"\n\t{WATCH}\n", YT, WATCH, VID),
    (f"Şu videoya bak https://youtu.be/{VID} çok iyi!", YT, WATCH, VID),
    (f"Şu videoya bak: https://youtu.be/{VID}!", YT, WATCH, VID),
    (f"({WATCH})", YT, WATCH, VID),
    (f"<{WATCH}>", YT, WATCH, VID),
    (f'"{WATCH}"', YT, WATCH, VID),
    (f"{WATCH}.", YT, WATCH, VID),
    (f"​{WATCH}﻿", YT, WATCH, VID),
    (f"izle→youtu.be/{VID} (harika)", YT, WATCH, VID),
    (f"first {WATCH} then https://vimeo.com/1", YT, WATCH, VID),
    # --- YouTube playlists / channels -----------------------------------------------------
    (PL_URL, YTP, PL_URL, PL),
    (f"https://m.youtube.com/playlist?list={PL}&si=abc", YTP, PL_URL, PL),
    (f"https://www.youtube.com/watch?list={PL}", YTP, PL_URL, PL),
    ("https://music.youtube.com/playlist?list=OLAK5uy_kX5bDfdHg3bdfXRwEqwbxZ6oQ1pl3Ci0A", YTP,
     "https://www.youtube.com/playlist?list=OLAK5uy_kX5bDfdHg3bdfXRwEqwbxZ6oQ1pl3Ci0A", None),
    ("https://www.youtube.com/@NASA", YTC, "https://www.youtube.com/@NASA", "@NASA"),
    ("https://youtube.com/@NASA/videos", YTC, "https://www.youtube.com/@NASA/videos", "@NASA"),
    ("https://www.youtube.com/@NASA/shorts?view=0", YTC, "https://www.youtube.com/@NASA/shorts", "@NASA"),
    ("https://www.youtube.com/@NASA/community", YTC, "https://www.youtube.com/@NASA", "@NASA"),
    ("https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ", YTC,
     "https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ", "UCLA_DiR1FfKNvjuUpBHmylQ"),
    ("https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ/streams", YTC,
     "https://www.youtube.com/channel/UCLA_DiR1FfKNvjuUpBHmylQ/streams", None),
    ("https://www.youtube.com/c/NASA", YTC, "https://www.youtube.com/c/NASA", "NASA"),
    ("https://www.youtube.com/user/NASAtelevision/videos", YTC,
     "https://www.youtube.com/user/NASAtelevision/videos", "NASAtelevision"),
    # --- YouTube invalid / private -------------------------------------------------------
    ("https://www.youtube.com/watch?v=short", UNK, None, None),
    ("https://www.youtube.com/playlist?list=WL", UNK, None, None),
    ("https://www.youtube.com/playlist?list=LL", UNK, None, None),
    ("https://youtu.be/", UNK, None, None),
    # --- Instagram ------------------------------------------------------------------------
    ("https://www.instagram.com/p/C1a2B3c4D5e/", IGP, "https://www.instagram.com/p/C1a2B3c4D5e/", "C1a2B3c4D5e"),
    ("https://instagram.com/reel/C1a2B3c4D5e/?igsh=MWQ1ZGUxMzBkMA==", IGP,
     "https://www.instagram.com/reel/C1a2B3c4D5e/", "C1a2B3c4D5e"),
    ("https://www.instagram.com/reels/C1a2B3c4D5e/", IGP, "https://www.instagram.com/reel/C1a2B3c4D5e/", None),
    ("https://www.instagram.com/tv/C1a2B3c4D5e", IGP, "https://www.instagram.com/tv/C1a2B3c4D5e/", None),
    ("https://www.instagram.com/natgeo/p/C1a2B3c4D5e/", IGP, "https://www.instagram.com/p/C1a2B3c4D5e/", None),
    ("instagram.com/p/C1a2B3c4D5e", IGP, None, "C1a2B3c4D5e"),
    ("https://www.instagram.com/natgeo/", IGU, "https://www.instagram.com/natgeo/", "natgeo"),
    ("https://instagram.com/nat.geo_tr?igshid=abc", IGU, "https://www.instagram.com/nat.geo_tr/", "nat.geo_tr"),
    ("https://www.instagram.com/natgeo/reels/", IGU, "https://www.instagram.com/natgeo/", "natgeo"),
    ("https://www.instagram.com/explore/", UNK, None, None),
    ("https://www.instagram.com/stories/natgeo/3456789012345678901/", UNK, None, None),
    ("https://www.instagram.com/accounts/login/", UNK, None, None),
    ("https://www.instagram.com/", UNK, None, None),
    # --- generic (yt-dlp extractors) --------------------------------------------------------
    ("https://x.com/SpaceX/status/2080804682918764619", GEN, "https://x.com/SpaceX/status/2080804682918764619", None),
    ("https://twitter.com/SpaceX/status/2080804682918764619", GEN, None, None),
    ("https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/", GEN, None, None),
    ("https://soundcloud.com/the80m/the-following", GEN, None, None),
    ("https://clips.twitch.tv/FaintLightGullWholeWheat", GEN, None, None),
    ("https://www.twitch.tv/xqc/clip/CulturedAmazingKuduDatSheffy-TiZ_-ixAGYR3y2Uy", GEN, None, None),
    ("https://www.dailymotion.com/video/x5kesuj", GEN, None, None),
    ("https://vimeo.com/76979871", GEN, None, None),
    ("https://www.facebook.com/watch/?v=274175099429670", GEN, None, None),
    ("Bunu indir: https://x.com/SpaceX/status/2080804682918764619?s=46&t=abc,", GEN,
     "https://x.com/SpaceX/status/2080804682918764619?s=46&t=abc", None),
    # --- not links / unsupported ---------------------------------------------------------------
    ("", UNK, None, None),
    ("   ", UNK, None, None),
    ("merhaba dünya", UNK, None, None),
    ("örn. bu bir cümle.", UNK, None, None),
    ("dQw4w9WgXcQ", UNK, None, None),
    ("ftp://example.com/video.mp4", UNK, None, None),
    ("https://example.com/", UNK, None, None),
    ("https://localhost/video", UNK, None, None),
    ("mailto:someone@example.com", UNK, None, None),
    ("javascript:alert(1)", UNK, None, None),
]


@pytest.mark.parametrize("text,platform,url,media_id", CASES, ids=[repr(c[0])[:60] for c in CASES])
def test_analyze(text, platform, url, media_id):
    det = router.analyze(text)
    assert det.platform is platform, det
    assert router.detect(text) is platform
    if url is not None:
        assert det.url == url
    if media_id is not None:
        assert det.media_id == media_id


def test_table_is_big_enough():
    assert len(CASES) >= 40


def test_none_input():
    assert router.analyze(None).platform is UNK
    assert router.extract_url(None) is None


def test_watch_with_list_offers_both():
    det = router.analyze(f"https://www.youtube.com/watch?v={VID}&list={PL}&index=3")
    assert det.platform is YT
    assert det.url == WATCH
    assert det.playlist_url == PL_URL


def test_watch_with_private_list_offers_no_playlist():
    det = router.analyze(f"https://www.youtube.com/watch?v={VID}&list=WL")
    assert det.platform is YT
    assert det.playlist_url is None


def test_youtube_subtypes():
    assert router.analyze(f"https://youtube.com/shorts/{VID}").subtype == "shorts"
    assert router.analyze(f"https://youtube.com/live/{VID}").subtype == "live"
    assert router.analyze(f"https://music.youtube.com/watch?v={VID}").subtype == "music"
    assert router.analyze(WATCH).subtype is None


def test_generic_reports_extractor():
    det = router.analyze("https://x.com/SpaceX/status/2080804682918764619")
    assert det.extractor == "Twitter"
    assert router.analyze("https://clips.twitch.tv/FaintLightGullWholeWheat").extractor == "TwitchClips"


def test_truncated_youtube_id_is_not_generic():
    assert router.find_extractor("https://www.youtube.com/watch?v=abc") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("see https://a.example.org/x?y=1).", "https://a.example.org/x?y=1"),
        ("https://en.wikipedia.org/wiki/Foo_(bar)", "https://en.wikipedia.org/wiki/Foo_(bar)"),
        ("(https://en.wikipedia.org/wiki/Foo_(bar))", "https://en.wikipedia.org/wiki/Foo_(bar)"),
        ("link: example.com/path, ok", "https://example.com/path"),
        ("www.example.com", "https://www.example.com"),
        ("e-posta: ali@example.com/abc", None),
        ("sadece metin", None),
        ("https://nodot/path", None),
    ],
)
def test_extract_url(text, expected):
    assert router.extract_url(text) == expected
