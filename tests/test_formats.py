import pytest

from arnold_dw.core import formats


def _info(*heights):
    return {"formats": [{"height": h} for h in heights]}


@pytest.mark.parametrize("info, expected", [
    (None, 0),
    ({}, 0),
    ({"formats": []}, 0),
    ({"formats": None}, 0),
    (_info(None, 144, 360), 360),
    (_info(1080, 2160, 720), 2160),
    ({"formats": [{"acodec": "mp4a"}, {"height": 480}]}, 480),
])
def test_max_available_height(info, expected):
    assert formats.max_available_height(info) == expected


def test_available_quality_options_unknown_height_offers_everything():
    assert formats.available_quality_options(0) == formats.QUALITY_OPTIONS
    assert formats.available_quality_options(0) is not formats.QUALITY_OPTIONS


@pytest.mark.parametrize("max_height, expected", [
    (2160, formats.QUALITY_OPTIONS),
    (1080, ["1080p", "720p", "480p", "360p", "240p", "144p"]),
    (720, ["720p", "480p", "360p", "240p", "144p"]),
    (500, ["480p", "360p", "240p", "144p"]),
    (144, ["144p"]),
    (100, ["144p"]),  # below the lowest rung: still offer the smallest one
])
def test_available_quality_options(max_height, expected):
    assert formats.available_quality_options(max_height) == expected


@pytest.mark.parametrize("max_height, expected", [
    (0, "1080p"),
    (2160, "1080p"),
    (1440, "1080p"),
    (1080, "1080p"),
    (720, "720p"),
    (400, "360p"),
    (100, "144p"),
])
def test_pick_default_quality(max_height, expected):
    assert formats.pick_default_quality(max_height) == expected


def test_build_video_format_prefers_m4a_audio_and_caps_height():
    selector = formats.build_video_format(720)
    alternatives = selector.split("/")
    assert alternatives[0] == "bestvideo[height<=720]+bestaudio[ext=m4a]"
    assert alternatives[1] == "bestvideo[height<=720]+bestaudio"
    assert alternatives[2] == "best[height<=720]"


def test_build_format_options_mp4():
    opts = formats.build_format_options("MP4", "480p")
    assert opts["format"] == formats.build_video_format(480)
    assert opts["merge_output_format"] == "mp4"
    assert "postprocessors" not in opts


def test_build_format_options_mp4_unknown_quality_falls_back_to_1080():
    assert formats.build_format_options("MP4", "bogus")["format"] == formats.build_video_format(1080)


@pytest.mark.parametrize("label, bitrate", [("320 kbps", "320"), ("192 kbps", "192"),
                                            ("128 kbps", "128"), ("bogus", "192")])
def test_build_format_options_mp3(label, bitrate):
    opts = formats.build_format_options("MP3", label)
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"] == [{
        "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate,
    }]
    assert "merge_output_format" not in opts


def test_every_quality_label_has_a_height_and_every_audio_label_a_bitrate():
    assert set(formats.QUALITY_OPTIONS) == set(formats.QUALITY_HEIGHTS)
    assert set(formats.AUDIO_OPTIONS) == set(formats.AUDIO_BITRATE)
    assert formats.DEFAULT_AUDIO_OPTION in formats.AUDIO_OPTIONS
