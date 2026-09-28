"""Instagram post/profile resolution and media download (Instaloader + public pages).

UI-independent: every function runs synchronously in the caller's worker
thread; long operations take a threading.Event for cancellation and report
progress through a callback.
"""

import html
import logging
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

import instaloader
import requests

from arnold_dw.core import filenames, http
from arnold_dw.core.errors import DownloadCancelled

log = logging.getLogger(__name__)

INSTAGRAM_POST_RE = re.compile(
    r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
INSTAGRAM_PROFILE_RE = re.compile(
    r"instagram\.com/([A-Za-z0-9._]+)",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"[A-Za-z0-9._]+")
# Instagram only serves the public profile page / meta tags to known crawlers
# without a login. See the CX-3-T06 audit (finding 4) - kept pending a decision.
INSTAGRAM_CRAWLER_USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
# GraphQL persisted query for a profile's timeline; Instagram may rotate it.
PROFILE_TIMELINE_DOC_ID = "7950326061742207"

REQUEST_TIMEOUT = 15
MEDIA_TIMEOUT = 30
_CHUNK = 256 * 1024

# Profile download categories.
CATEGORY_POSTS = "posts"
CATEGORY_REELS = "reels"
CATEGORY_PROFILE_PIC = "profile_pic"

# Progress stages passed to on_progress(stage, index, total).
STAGE_POST_ITEM = "post_item"      # index/total within the selected post media
STAGE_PROFILE_PIC = "profile_pic"
STAGE_POST = "post"                # index = n-th profile post, total None
STAGE_REEL = "reel"                # index = n-th profile video, total None


def progress_text(stage, index, total):
    """User-facing (Turkish) text for an on_progress(stage, index, total) report."""
    if stage == STAGE_POST_ITEM:
        return f"{index}/{total} indiriliyor..."
    if stage == STAGE_PROFILE_PIC:
        return "Profil fotoğrafı indiriliyor..."
    if stage == STAGE_POST:
        return f"Gönderi {index} indiriliyor..."
    if stage == STAGE_REEL:
        return f"Reels/video {index} indiriliyor..."
    return "İndiriliyor..."


def post_url(shortcode):
    return f"https://www.instagram.com/p/{shortcode}/"


def profile_url(username):
    return f"https://www.instagram.com/{username}/"


def parse_input(value):
    """Classify user input: ("post", shortcode) or ("profile", username).

    Raises ValueError when it's neither a post link nor a valid username.
    """
    value = (value or "").strip()
    post_match = INSTAGRAM_POST_RE.search(value)
    if post_match:
        return "post", post_match.group(1)
    profile_match = INSTAGRAM_PROFILE_RE.search(value)
    username = profile_match.group(1) if profile_match else value
    username = username.strip().lstrip("@").strip("/")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Invalid Instagram username")
    return "profile", username


def new_loader():
    return instaloader.Instaloader(
        sleep=False,
        max_connection_attempts=1,
        request_timeout=REQUEST_TIMEOUT,
        user_agent=INSTAGRAM_CRAWLER_USER_AGENT,
        iphone_support=False,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )


def post_media(post):
    """Return original media URLs represented by an Instaloader Post."""
    media = []
    if post.typename == "GraphSidecar":
        for index, node in enumerate(post.get_sidecar_nodes(), start=1):
            media.append({
                "index": index,
                "is_video": bool(node.is_video),
                "url": node.video_url if node.is_video else node.display_url,
                "thumbnail_url": node.display_url,
            })
    else:
        media.append({
            "index": 1,
            "is_video": bool(post.is_video),
            "url": post.video_url if post.is_video else post.url,
            "thumbnail_url": post.url,
        })
    return media


def _meta_content(page, property_name):
    match = re.search(
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\']'
        rf'[^>]+content=["\']([^"\']+)',
        page,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+'
            rf'property=["\']{re.escape(property_name)}["\']',
            page,
            re.IGNORECASE,
        )
    return html.unescape(match.group(1)) if match else ""


def fetch_public_profile(loader, username):
    """Build an Instaloader Profile from the public profile page + timeline query."""
    profile_url = f"https://www.instagram.com/{username}/"
    page = http.get_text(
        profile_url,
        headers={"User-Agent": INSTAGRAM_CRAWLER_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )

    user_id_match = re.search(r"profilePage_([0-9]+)", page)
    if user_id_match is None:
        user_id_match = re.search(r'"user_id":"?([0-9]+)', page)
    if user_id_match is None:
        raise instaloader.ProfileNotExistsException(
            f"Profile does not exist: {username}"
        )

    title = _meta_content(page, "og:title")
    full_name = title.split("(@", 1)[0].strip() if "(@" in title else username
    profile_pic_url = _meta_content(page, "og:image")
    user_id = user_id_match.group(1)

    variables = {
        "data": {
            "count": 12,
            "include_relationship_info": True,
            "latest_besties_reel_media": True,
            "latest_reel_media": True,
        },
        "id": int(user_id),
        "after": None,
        "first": 12,
    }
    result = loader.context.doc_id_graphql_query(
        PROFILE_TIMELINE_DOC_ID,
        variables,
        referer=profile_url,
    )
    user_data = (result.get("data") or {}).get("user") or {}
    timeline = user_data.get("edge_owner_to_timeline_media")
    is_private = timeline is None
    if timeline is None:
        timeline = {
            "count": 0,
            "page_info": {"has_next_page": False, "end_cursor": None},
            "edges": [],
        }

    node = {
        "id": user_id,
        "username": username,
        "full_name": full_name,
        "is_private": is_private,
        "profile_pic_url": profile_pic_url,
        "profile_pic_url_hd": profile_pic_url,
        "edge_owner_to_timeline_media": timeline,
        "edge_followed_by": {"count": 0},
        "edge_follow": {"count": 0},
    }
    profile = instaloader.Profile(loader.context, node)
    profile._has_full_metadata = True
    return profile


@dataclass
class PostPreview:
    loader: object
    post: object
    media: list
    thumbnails: list  # PIL images (or None), parallel to `media`


@dataclass
class ProfilePreview:
    loader: object
    profile: object
    avatar: object  # PIL image or None


@dataclass
class ProfileCache:
    """Thread-safe LRU of resolved profiles (bounded: each entry holds a session + avatar)."""

    maxsize: int = 16
    _items: OrderedDict = field(default_factory=OrderedDict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, username):
        key = username.lower()
        with self._lock:
            entry = self._items.get(key)
            if entry is not None:
                self._items.move_to_end(key)
            return entry

    def put(self, username, entry):
        key = username.lower()
        with self._lock:
            self._items[key] = entry
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)

    def __len__(self):
        with self._lock:
            return len(self._items)


def resolve(value, cache=None):
    """Resolve a post link or a username/profile link to a preview (blocking, network)."""
    kind, key = parse_input(value)
    loader = new_loader()
    if kind == "post":
        post = instaloader.Post.from_shortcode(loader.context, key)
        media = post_media(post)
        thumbnails = [http.fetch_image(item["thumbnail_url"], timeout=REQUEST_TIMEOUT) for item in media]
        return PostPreview(loader, post, media, thumbnails)

    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    profile = fetch_public_profile(loader, key)
    avatar = http.fetch_image(str(profile.profile_pic_url), timeout=REQUEST_TIMEOUT)
    preview = ProfilePreview(loader, profile, avatar)
    if cache is not None:
        cache.put(key, preview)
    return preview


def download_media(item, folder, basename, cancel_event):
    """Stream one media file to `folder`. Returns False if it already exists.

    Writes to a `.part` file first and renames on success, so an interrupted
    transfer never leaves a truncated file that later runs would skip.
    """
    if cancel_event.is_set():
        raise DownloadCancelled()
    path = filenames.media_path(folder, basename, item["is_video"])
    if os.path.exists(path):
        return False

    part_path = path + ".part"
    try:
        with requests.get(item["url"], stream=True, timeout=MEDIA_TIMEOUT) as response:
            response.raise_for_status()
            with open(part_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=_CHUNK):
                    if cancel_event.is_set():
                        raise DownloadCancelled()
                    if chunk:
                        output.write(chunk)
        os.replace(part_path, path)
    except BaseException:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise
    return True


def _fetch_file(item, folder, basename, cancel_event, on_file):
    """download_media + report the final path. Returns 1 if a new file was written."""
    created = download_media(item, folder, basename, cancel_event)
    if on_file is not None:
        on_file(filenames.media_path(folder, basename, item["is_video"]), created)
    return 1 if created else 0


def _download_post_items(post, folder, cancel_event, seen_shortcodes, on_file=None):
    if post.shortcode in seen_shortcodes:
        return 0
    seen_shortcodes.add(post.shortcode)
    count = 0
    for item in post_media(post):
        if not item["url"]:
            continue
        basename = filenames.instagram_post_basename(post.owner_username, post.shortcode, item["index"])
        count += _fetch_file(item, folder, basename, cancel_event, on_file)
    return count


def download_post(post, items, folder, cancel_event, on_progress=None, on_file=None):
    """Download the selected `items` (from post_media) of one post. Returns files written.

    on_file(path, created) is called for every selected file: created=False
    when it already existed and was left untouched.
    """
    os.makedirs(folder, exist_ok=True)
    downloaded = 0
    for position, item in enumerate(items, start=1):
        if on_progress is not None:
            on_progress(STAGE_POST_ITEM, position, len(items))
        if not item["url"]:
            continue
        basename = filenames.instagram_post_basename(post.owner_username, post.shortcode, item["index"])
        downloaded += _fetch_file(item, folder, basename, cancel_event, on_file)
    return downloaded


def download_profile(profile, categories, folder, cancel_event, on_progress=None, on_file=None):
    """Download the chosen categories of a profile. Returns files written (see download_post)."""
    os.makedirs(folder, exist_ok=True)
    downloaded = 0
    seen_shortcodes = set()

    def report(stage, index=None):
        if on_progress is not None:
            on_progress(stage, index, None)

    if CATEGORY_PROFILE_PIC in categories:
        report(STAGE_PROFILE_PIC)
        profile_item = {"is_video": False, "url": str(profile.profile_pic_url)}
        downloaded += _fetch_file(profile_item, folder,
                                  filenames.instagram_profile_pic_basename(profile.username),
                                  cancel_event, on_file)

    if CATEGORY_POSTS in categories:
        for index, post in enumerate(profile.get_posts(), start=1):
            if cancel_event.is_set():
                raise DownloadCancelled()
            if post.is_video and post.typename != "GraphSidecar":
                continue
            report(STAGE_POST, index)
            downloaded += _download_post_items(post, folder, cancel_event, seen_shortcodes, on_file)

    if CATEGORY_REELS in categories:
        video_index = 0
        for post in profile.get_posts():
            if cancel_event.is_set():
                raise DownloadCancelled()
            if not post.is_video:
                continue
            video_index += 1
            report(STAGE_REEL, video_index)
            downloaded += _download_post_items(post, folder, cancel_event, seen_shortcodes, on_file)

    return downloaded
