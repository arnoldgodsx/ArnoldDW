"""Quality/format choices and the yt-dlp format options they map to (pure functions)."""

FORMAT_MP4 = "MP4"
FORMAT_MP3 = "MP3"
FORMATS = [FORMAT_MP4, FORMAT_MP3]

QUALITY_OPTIONS = ["4K", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
QUALITY_HEIGHTS = {
    "4K": 2160, "1440p": 1440, "1080p": 1080, "720p": 720,
    "480p": 480, "360p": 360, "240p": 240, "144p": 144,
}
DEFAULT_MAX_HEIGHT = 1080

AUDIO_OPTIONS = ["320 kbps", "192 kbps", "128 kbps"]
AUDIO_BITRATE = {"320 kbps": "320", "192 kbps": "192", "128 kbps": "128"}
DEFAULT_AUDIO_OPTION = AUDIO_OPTIONS[1]


def max_available_height(info):
    """Highest video height actually offered by the source for this video."""
    if not info:
        return 0
    heights = [f.get("height") or 0 for f in (info.get("formats") or [])]
    return max(heights) if heights else 0


def available_quality_options(max_height):
    """Only ever offer quality rungs the source video actually supports."""
    if not max_height:
        return QUALITY_OPTIONS[:]
    opts = [label for label in QUALITY_OPTIONS if QUALITY_HEIGHTS[label] <= max_height]
    return opts or [QUALITY_OPTIONS[-1]]


def pick_default_quality(max_height):
    target = min(DEFAULT_MAX_HEIGHT, max_height) if max_height else DEFAULT_MAX_HEIGHT
    for label in QUALITY_OPTIONS:
        if QUALITY_HEIGHTS[label] <= target:
            return label
    return QUALITY_OPTIONS[-1]


def build_video_format(height):
    # Prefer m4a/AAC audio explicitly: YouTube's plain "bestaudio" is usually
    # Opus, which many common Windows video players can't decode when it's
    # boxed in an MP4 container, so the merged file plays back with no sound.
    # AAC-in-MP4 is universally supported, so ask for that first and only fall
    # back to whatever audio is available if no m4a track exists.
    return (
        f"bestvideo[height<={height}]+bestaudio[ext=m4a]"
        f"/bestvideo[height<={height}]+bestaudio"
        f"/best[height<={height}]"
    )


def build_audio_format():
    return "bestaudio/best"


def mp3_postprocessors(bitrate):
    return [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": bitrate,
    }]


def build_format_options(fmt, quality):
    """yt-dlp options selecting the streams for a format ("MP4"/"MP3") + quality label."""
    if fmt == FORMAT_MP3:
        return {
            "format": build_audio_format(),
            "postprocessors": mp3_postprocessors(AUDIO_BITRATE.get(quality, "192")),
        }
    height = QUALITY_HEIGHTS.get(quality, DEFAULT_MAX_HEIGHT)
    return {
        "format": build_video_format(height),
        "merge_output_format": "mp4",
    }
