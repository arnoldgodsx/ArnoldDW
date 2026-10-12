"""Detect which platform a pasted link belongs to.

``analyze(text)`` works offline: it pulls the first link out of whatever the
user pasted (share texts, missing scheme, stray punctuation), classifies it and
returns a canonical URL.
"""

from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .models import Platform

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Detection:
    platform: Platform
    url: str | None = None  # cleaned, canonical URL (None when no link was found)
    media_id: str | None = None  # video id / playlist id / shortcode / username / short code
    subtype: str | None = None  # e.g. "shorts", "live", "music", "p", "reel", channel tab
    playlist_url: str | None = None  # watch?v=..&list=.. -> the playlist, offered as an alternative
    extractor: str | None = None  # yt-dlp extractor key for GENERIC

    @property
    def supported(self) -> bool:
        return self.platform is not Platform.UNKNOWN


# --------------------------------------------------------------------------
# Pulling a URL out of free text
# --------------------------------------------------------------------------

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_SCHEME_URL_RE = re.compile(r"""(?:https?://|www\.)[^\s<>"'`{}|\\^\[\]]+""", re.IGNORECASE)
# Scheme-less "domain.tld/path" (a slash is required so plain words like "e.g." never match).
_BARE_URL_RE = re.compile(
    r"""(?<![\w@./:-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}/[^\s<>"'`{}|\\^\[\]]*)""",
    re.IGNORECASE,
)
_TRAILING = ".,;:!?…'\"”’»)]}>"
_OPENERS = {")": "(", "]": "[", "}": "{"}


def _strip_trailing(url: str) -> str:
    while url and url[-1] in _TRAILING:
        last = url[-1]
        # Keep a closing bracket that balances one inside the URL (e.g. Wikipedia-style links).
        if last in _OPENERS and url.count(_OPENERS[last]) >= url.count(last):
            break
        url = url[:-1]
    return url


def extract_url(text: str | None) -> str | None:
    """Return the first http(s) link found in ``text`` (scheme added if missing), or None."""
    if not text:
        return None
    text = text.translate(_INVISIBLE).strip()
    match = _SCHEME_URL_RE.search(text) or _BARE_URL_RE.search(text)
    if not match:
        return None
    url = _strip_trailing(match.group(0))
    if not re.match(r"https?://", url, re.IGNORECASE):
        url = "https://" + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").rstrip(".")
    if "." not in host:
        return None
    return url


def _host(parts) -> str:
    host = (parts.hostname or "").lower().rstrip(".")
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    return host


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _first(query: dict, key: str) -> str | None:
    values = query.get(key)
    return values[0].strip() if values else None


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------

_YT_HOSTS = {"youtube.com", "music.youtube.com", "gaming.youtube.com", "youtube-nocookie.com", "youtu.be"}
_YT_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_YT_LIST_ID = re.compile(r"[A-Za-z0-9_-]{2,64}")
_YT_PRIVATE_LISTS = {"WL", "LL", "LM"}  # Watch later / liked: need the owner's login
_YT_CHANNEL_TABS = {"videos", "shorts", "streams", "playlists", "featured", "releases", "podcasts"}
_YT_VIDEO_PATHS = {"shorts": "shorts", "embed": None, "live": "live", "v": None, "e": None}


def _youtube(parts, host: str) -> Detection | None:
    query = parse_qs(parts.query)
    segs = _segments(parts.path)
    video_id = subtype = None
    channel_path = None

    if host == "youtu.be":
        video_id = segs[0] if segs else None
    elif segs and segs[0] == "watch":
        video_id = _first(query, "v")
    elif len(segs) >= 2 and segs[0] in _YT_VIDEO_PATHS:
        video_id, subtype = segs[1], _YT_VIDEO_PATHS[segs[0]]
    elif segs and segs[0].startswith("@") and len(segs[0]) > 1:
        channel_path = segs[:2]
    elif len(segs) >= 2 and segs[0] in ("channel", "c", "user"):
        channel_path = segs[:3]

    if host == "music.youtube.com" and subtype is None:
        subtype = "music"

    list_id = _first(query, "list")
    if list_id and not _YT_LIST_ID.fullmatch(list_id):
        list_id = None
    playlist_url = (
        f"https://www.youtube.com/playlist?list={list_id}"
        if list_id and list_id not in _YT_PRIVATE_LISTS
        else None
    )

    if video_id and _YT_VIDEO_ID.fullmatch(video_id):
        url = f"https://www.youtube.com/watch?v={video_id}"
        if subtype == "shorts":
            url = f"https://www.youtube.com/shorts/{video_id}"
        return Detection(Platform.YOUTUBE, url, video_id, subtype, playlist_url=playlist_url)

    if video_id is None and list_id and (not segs or segs[0] in ("playlist", "watch")):
        if playlist_url is None:  # the user's own Watch later / Liked list
            return Detection(Platform.UNKNOWN, parts.geturl(), list_id, "private_list")
        return Detection(Platform.YOUTUBE_PLAYLIST, playlist_url, list_id)

    if channel_path:
        tab = None
        base = channel_path
        if channel_path[0].startswith("@"):
            base = channel_path[:1]
            tab = channel_path[1] if len(channel_path) > 1 else None
        else:
            base = channel_path[:2]
            tab = channel_path[2] if len(channel_path) > 2 else None
        tab = tab.lower() if tab and tab.lower() in _YT_CHANNEL_TABS else None
        url = "https://www.youtube.com/" + "/".join(base + ([tab] if tab else []))
        return Detection(Platform.YOUTUBE_CHANNEL, url, base[-1], tab)

    return None


# --------------------------------------------------------------------------
# Instagram
# --------------------------------------------------------------------------

_IG_HOSTS = {"instagram.com", "instagr.am"}
_IG_POST_KINDS = {"p", "reel", "reels", "tv"}
_IG_SHORTCODE = re.compile(r"[A-Za-z0-9_-]{5,64}")
_IG_USERNAME = re.compile(r"[A-Za-z0-9._]{1,30}")
_IG_RESERVED = {
    "explore", "accounts", "about", "developer", "developers", "legal", "direct", "stories", "p", "reel",
    "reels", "tv", "web", "api", "challenge", "emails", "privacy", "terms", "session", "oauth", "graphql",
    "static", "press", "blog", "help", "lite", "nametag", "download", "directory", "topics", "ar",
    "your_activity", "archive", "saved", "business", "creators",
}
_IG_PROFILE_TABS = {"reels", "tagged", "saved", "guides", "feed", "igtv"}


def _instagram(parts) -> Detection:
    segs = _segments(parts.path)
    # /p/CODE, /reel/CODE, also the newer /<username>/p/CODE form
    for i in (0, 1):
        if len(segs) > i + 1 and segs[i].lower() in _IG_POST_KINDS and _IG_SHORTCODE.fullmatch(segs[i + 1]):
            if i == 1 and not _IG_USERNAME.fullmatch(segs[0]):
                break
            kind = "reel" if segs[i].lower() in ("reel", "reels") else segs[i].lower()
            code = segs[i + 1]
            return Detection(Platform.INSTAGRAM_POST, f"https://www.instagram.com/{kind}/{code}/", code, kind)
    if segs and _IG_USERNAME.fullmatch(segs[0]) and segs[0].lower() not in _IG_RESERVED:
        if len(segs) == 1 or (len(segs) == 2 and segs[1].lower() in _IG_PROFILE_TABS):
            name = segs[0]
            if not (name.startswith(".") or name.endswith(".") or ".." in name):
                return Detection(Platform.INSTAGRAM_PROFILE, f"https://www.instagram.com/{name}/", name)
    return Detection(Platform.UNKNOWN, parts.geturl())


# --------------------------------------------------------------------------
# Generic (any other yt-dlp supported site)
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _extractor_classes() -> tuple:
    from yt_dlp.extractor import gen_extractor_classes

    return tuple(ie for ie in gen_extractor_classes() if ie.ie_key() != "Generic")


@functools.lru_cache(maxsize=512)
def find_extractor(url: str) -> str | None:
    """Key of the yt-dlp extractor that would handle ``url`` (offline; the catch-all Generic IE is ignored).

    Extractors that yt-dlp itself marks as broken are treated as unsupported.
    """
    for ie in _extractor_classes():
        try:
            if ie.suitable(url):
                key = ie.ie_key()
                # "Truncated" extractors only exist to raise a "your link is cut off" error.
                return key if ie.working() and "Truncated" not in key else None
        except Exception:  # a buggy _VALID_URL in one extractor must not break detection
            continue
    return None


def warm_up() -> None:
    """Pre-compile every extractor pattern (~1 s). Call once from a background thread at startup."""
    find_extractor("https://warm-up.invalid/")


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def analyze(text: str | None) -> Detection:
    """Classify pasted text without touching the network."""
    url = extract_url(text)
    if not url:
        return Detection(Platform.UNKNOWN)
    parts = urlsplit(url)
    host = _host(parts)

    if host in _YT_HOSTS or host.endswith(".youtube.com"):
        det = _youtube(parts, host)
        if det:
            return det
    elif host in _IG_HOSTS:
        return _instagram(parts)

    key = find_extractor(url)
    if key:
        return Detection(Platform.GENERIC, url, extractor=key)
    return Detection(Platform.UNKNOWN, url)


def detect(text: str | None) -> Platform:
    return analyze(text).platform
