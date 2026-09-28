"""Platform runners for the DownloadManager: platform name -> Runner.

Adding a platform = writing `run_<platform>(job, ctx) -> RunResult` and one
line in `default_runners()`. A runner must work from `job.url` +
`job.options` alone (a retry after an app restart has nothing else);
`job.context` may carry an already resolved object to skip the lookup.
"""

from arnold_dw.core import errors, formats, instagram, youtube
from arnold_dw.core.jobs import Runner, RunResult

PLATFORM_YOUTUBE = "youtube"
PLATFORM_INSTAGRAM = "instagram"


# --- YouTube ----------------------------------------------------------------

def youtube_options(fmt, quality):
    return {"format": fmt, "quality": quality}


def youtube_title_suffix(options):
    """"MP4 · 720p" / "MP3 · 192 kbps" for list rows."""
    return f"{options.get('format', formats.FORMAT_MP4)} · {options.get('quality', '')}".strip(" ·")


def run_youtube(job, ctx):
    fmt = job.options.get("format", formats.FORMAT_MP4)
    quality = job.options.get("quality", "")

    def on_progress(fraction, downloaded, speed, eta):
        ctx.progress(downloaded=downloaded, fraction=fraction, speed=speed, eta=eta, stage="İndiriliyor")

    result = youtube.download(job.url, fmt, quality, job.download_dir, ctx.cancel_event,
                              on_progress=on_progress, on_processing=ctx.processing)
    return RunResult(files=[result.path], already_existed=result.already_existed)


# --- Instagram --------------------------------------------------------------

def instagram_post_options(shortcode, item_indexes):
    return {"mode": "post", "shortcode": shortcode, "items": sorted(item_indexes)}


def instagram_profile_options(username, categories, browser=None):
    return {"mode": "profile", "username": username, "categories": list(categories), "browser": browser}


def run_instagram(job, ctx):
    options = job.options
    preview = job.context
    files, created = [], []

    def on_file(path, was_created):
        files.append(path)
        if was_created:
            created.append(path)

    def on_progress(stage, index, total):
        fraction = (index - 1) / total if total else None
        ctx.progress(fraction=fraction, stage=instagram.progress_text(stage, index, total))

    if options.get("mode") == "post":
        if not isinstance(preview, instagram.PostPreview):
            preview = instagram.resolve(instagram.post_url(options["shortcode"]))
        ctx.check_cancelled()
        wanted = set(options.get("items") or [])
        items = [item for item in preview.media if not wanted or item["index"] in wanted]
        instagram.download_post(preview.post, items, job.download_dir, ctx.cancel_event,
                                on_progress, on_file=on_file)
    else:
        if not isinstance(preview, instagram.ProfilePreview):
            preview = instagram.resolve(instagram.profile_url(options["username"]))
        ctx.check_cancelled()
        instagram.download_profile(preview.profile, options.get("categories") or [], job.download_dir,
                                   ctx.cancel_event, on_progress, on_file=on_file,
                                   browser=options.get("browser"))
    return RunResult(files=files, already_existed=bool(files) and not created)


def default_runners():
    return {
        PLATFORM_YOUTUBE: Runner(run_youtube, errors.friendly_error),
        PLATFORM_INSTAGRAM: Runner(run_instagram, errors.instagram_friendly_error),
    }
