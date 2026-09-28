"""yt-dlp format selectors and post-processor chains.

Why "compat" is the default: YouTube's best streams are usually VP9/AV1 video with Opus
audio. Muxed into MP4 they play silently or show a black picture in the players that ship
with Windows. H.264 (avc1) + AAC (mp4a) plays everywhere, so compat mode prefers that
pairing and only falls back to other codecs when a site offers nothing else. Note that
YouTube serves H.264 only up to 1080p, so compat mode caps out there by design.

Tagging is done by ffmpeg only. The app deliberately does not ship mutagen (GPL), so
yt-dlp's EmbedThumbnail takes its ffmpeg path:

* MP3: ffmpeg alone is enough.
* MP4 / M4A: needs ffprobe next to ffmpeg; without it the cover is skipped. For M4A the
  chapters are left out when a cover is embedded (see :func:`embed_postprocessors`).
* Opus (Ogg): not possible without mutagen; the cover is always skipped.

Metadata (title, artist, chapters...) is written in every case. :func:`cover_supported`
holds this rule so the settings screen can grey the option out instead of failing.
"""

from __future__ import annotations

import logging
from typing import Literal

log = logging.getLogger(__name__)

VideoPreference = Literal["compat", "quality"]
AudioCodec = Literal["mp3", "m4a", "opus"]

AUDIO_CODECS: tuple[str, ...] = ("mp3", "m4a", "opus")
# Output extensions whose cover ffmpeg can embed, and whether that also needs ffprobe.
_COVER_NEEDS_FFPROBE = {"mp3": False, "m4a": True, "mp4": True}
MIN_AUDIO_BITRATE = 32
MAX_AUDIO_BITRATE = 320

# Regex filters (yt-dlp "~=" operator). Codec names differ per site: YouTube reports
# "avc1.4d401e" / "mp4a.40.2", others use "h264" / "aac".
H264 = "[vcodec~='^(avc|h264)']"
AAC = "[acodec~='^(mp4a|aac)']"
# Codecs ffmpeg can mux into an MP4 container without re-encoding.
MP4_VIDEO = "[vcodec~='^(avc|h264|hev|hvc|h265|vp0?9|av0?1)']"
MP4_AUDIO = "[acodec~='^(mp4a|aac|opus|mp3|ac-?3|ec-?3|flac)']"


def resolution_sort(max_height: int | None = None) -> list[str]:
    """yt-dlp ``format_sort`` key that caps resolution by the shorter frame side.

    The canonical resolution cap for every format selector in the app - used directly here
    and by :func:`core.platforms._ytdlp.format_sort`, so both modules cap resolution the same
    way (codec preference is a separate concern each module handles on its own: this one
    through the codec filters baked into :func:`video_selector`, ``_ytdlp`` through extra
    ``format_sort`` keys, since its selector has no codec filters of its own).

    A hard ``[height<=N]`` filter (the old approach) is wrong on two counts: a portrait video
    (TikTok, Shorts, Reels) reports its height as the *long* side, so "720p" 720x1280 content
    fails a ``height<=720`` test and the selector falls through to an unbounded alternative -
    the user picks 720p and gets 1080p instead; and a format with no ``height`` at all (some
    audio-only or oddly reported formats) is excluded outright instead of just ranked last.

    ``res:N`` sorts by ``min(width, height)`` - yt-dlp's own definition of the "res" field -
    so it naturally caps by the short side and never excludes anything: formats at or under
    the cap are preferred, a missing height sorts to the bottom, and if nothing fits under the
    cap the closest rung above it still wins instead of the selector failing.
    """
    if max_height is not None and int(max_height) <= 0:
        raise ValueError(f"max_height must be positive, got {max_height!r}")
    return [f"res:{max_height}" if max_height else "res"]


def video_selector(prefer: VideoPreference = "compat") -> str:
    """Codec-preference format selector for a video download that is merged into MP4.

    Resolution is capped separately, via :func:`resolution_sort`'s ``res:N`` key (short-side,
    never excludes a format outright - see its docstring) passed as the yt-dlp
    ``format_sort`` option alongside this selector's ``format`` string.
    """
    if prefer == "compat":
        alternatives = [
            f"bv{H264}+ba{AAC}",   # separate H.264 + AAC streams (YouTube DASH)
            f"b{H264}{AAC}",       # single progressive H.264/AAC file
            f"bv+ba{AAC}",         # keep AAC even if the video codec differs
            "bv+ba",
            "b",
        ]
    elif prefer == "quality":
        alternatives = [
            f"bv{MP4_VIDEO}+ba{MP4_AUDIO}",  # best streams that mux into MP4 losslessly
            "bv+ba",
            "b",
        ]
    else:
        raise ValueError(f"prefer must be 'compat' or 'quality', got {prefer!r}")
    return "/".join(alternatives)


def audio_selector(codec: AudioCodec = "mp3") -> str:
    """Source stream for an audio download; picks one that avoids re-encoding when possible."""
    _check_codec(codec)
    if codec == "m4a":
        return f"ba{AAC}/ba/b"
    if codec == "opus":
        return "ba[acodec=opus]/ba/b"
    return "ba/b"


def _check_codec(codec: str) -> None:
    if codec not in AUDIO_CODECS:
        raise ValueError(f"codec must be one of {AUDIO_CODECS}, got {codec!r}")


def audio_postprocessors(codec: AudioCodec = "mp3", bitrate: int | str = 192) -> list[dict]:
    """``FFmpegExtractAudio`` step converting the download to ``codec`` at ``bitrate`` kbit/s."""
    _check_codec(codec)
    kbps = int(bitrate)
    if not MIN_AUDIO_BITRATE <= kbps <= MAX_AUDIO_BITRATE:
        raise ValueError(f"bitrate must be {MIN_AUDIO_BITRATE}-{MAX_AUDIO_BITRATE} kbit/s, got {bitrate!r}")
    return [{"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": str(kbps)}]


def embed_postprocessors(ext: str, metadata: bool = True, thumbnail: bool = True) -> list[dict]:
    """Steps that embed tags/chapters and the cover image into the final ``ext`` file.

    Must run after conversion steps. Thumbnail embedding also needs ``writethumbnail=True``
    (see :func:`embed_options`) and must be allowed by :func:`cover_supported`.

    The order matters on yt-dlp's ffmpeg-only path (verified with ffmpeg 7.1 and 9.0):

    * MP4: the chapter text track written by FFmpegMetadata makes the cover step fail, so the
      cover goes in first; FFmpegMetadata then keeps it as an attached picture.
    * M4A: FFmpegMetadata runs with ``-vn`` for M4A and would drop the cover, so it runs
      first - without chapters, which would again break the cover step.
    * MP3: either order works; tags first.
    """
    meta = {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True}
    cover = {"key": "EmbedThumbnail", "already_have_thumbnail": False}
    if not thumbnail:
        return [meta] if metadata else []
    if not metadata:
        return [cover]
    if ext == "mp4":
        return [cover, meta]
    if ext == "m4a":
        return [{**meta, "add_chapters": False}, cover]
    return [meta, cover]


def cover_supported(ext: str, ffprobe: bool) -> bool:
    """Whether a cover image can be embedded into an ``ext`` file with this ffmpeg setup."""
    needs_ffprobe = _COVER_NEEDS_FFPROBE.get(ext)
    if needs_ffprobe is None:
        return False
    return ffprobe or not needs_ffprobe


def _resolve_cover(ext: str, wanted: bool, ffprobe: bool | None) -> bool:
    if not wanted:
        return False
    if ffprobe is None:
        from . import binaries

        ffprobe = binaries.ffprobe_path() is not None
    if cover_supported(ext, ffprobe):
        return True
    log.info("cover embedding into .%s is not possible here (ffprobe: %s); skipping it", ext, ffprobe)
    return False


def embed_options(thumbnail: bool = True) -> dict:
    """Extra top-level params required by :func:`embed_postprocessors`."""
    if not thumbnail:
        return {}
    return {
        "writethumbnail": True,
        "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}],
    }


def video_download_options(
    max_height: int | None,
    prefer: VideoPreference = "compat",
    *,
    embed_metadata: bool = False,
    embed_thumbnail: bool = False,
    ffprobe: bool | None = None,
) -> dict:
    """Complete format/merge/post-processing params for an MP4 video download.

    ``embed_thumbnail`` is dropped when :func:`cover_supported` says no. ``ffprobe=None``
    asks :mod:`binaries` whether ffprobe is available.
    """
    return _compose(
        {"format": video_selector(prefer), "format_sort": resolution_sort(max_height), "merge_output_format": "mp4"},
        [],
        "mp4",
        embed_metadata,
        _resolve_cover("mp4", embed_thumbnail, ffprobe),
    )


def audio_download_options(
    codec: AudioCodec = "mp3",
    bitrate: int | str = 192,
    *,
    embed_metadata: bool = False,
    embed_thumbnail: bool = False,
    ffprobe: bool | None = None,
) -> dict:
    """Complete format/post-processing params for an audio-only download.

    ``embed_thumbnail`` is dropped when :func:`cover_supported` says no (always for Opus);
    metadata is still written. ``ffprobe=None`` asks :mod:`binaries`.
    """
    return _compose(
        {"format": audio_selector(codec)},
        audio_postprocessors(codec, bitrate),
        codec,
        embed_metadata,
        _resolve_cover(codec, embed_thumbnail, ffprobe),
    )


def _compose(base: dict, convert_steps: list[dict], ext: str, metadata: bool, thumbnail: bool) -> dict:
    extra = embed_options(thumbnail)
    postprocessors = [*extra.get("postprocessors", []), *convert_steps, *embed_postprocessors(ext, metadata, thumbnail)]
    opts = {**base, **{k: v for k, v in extra.items() if k != "postprocessors"}}
    opts["postprocessors"] = postprocessors
    return opts
