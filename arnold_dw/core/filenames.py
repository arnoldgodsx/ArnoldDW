"""Output file naming (Windows-safe)."""

import os
import re

# yt-dlp output template: title capped at 150 bytes so long titles stay under MAX_PATH.
YOUTUBE_OUTTMPL = "%(title).150B [%(id)s].%(ext)s"

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename_part(value, fallback="instagram"):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:100].rstrip(" .")
    if value.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        value = f"_{value}"
    return value or fallback


def youtube_outtmpl(download_dir, label=None):
    """Output template; `label` (e.g. "720p", "192kbps") keeps each quality in its own file."""
    if not label:
        return os.path.join(download_dir, YOUTUBE_OUTTMPL)
    label = safe_filename_part(label, fallback="").replace("%", "%%")
    stem, ext = YOUTUBE_OUTTMPL.rsplit(".", 1)
    return os.path.join(download_dir, f"{stem} {label}.{ext}")


def instagram_post_basename(owner_username, shortcode, index):
    return f"instagram_{owner_username}_{shortcode}_{index:02d}"


def instagram_profile_pic_basename(username):
    return f"instagram_{username}_profil"


def media_path(folder, basename, is_video):
    extension = ".mp4" if is_video else ".jpg"
    return os.path.join(folder, f"{safe_filename_part(basename)}{extension}")
