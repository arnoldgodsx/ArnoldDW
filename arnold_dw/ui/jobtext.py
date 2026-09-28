"""How a download job is described in the UI: platform names/icons and status lines (no Tk)."""

import time

from arnold_dw import paths
from arnold_dw.core import jobs
from arnold_dw.core.jobs import CANCELLING
from arnold_dw.core.text import fmt_bytes, fmt_eta, fmt_speed
from arnold_dw.ui.theme import ERROR, SUCCESS, TEXT_FAINT, TEXT_MUTED

# Platform name (see core.runners) -> (display name, logo). A platform without
# an entry is shown by its raw name with no icon.
PLATFORMS = {
    "youtube": ("YouTube", paths.YOUTUBE_LOGO_PATH),
    "instagram": ("Instagram", paths.INSTAGRAM_LOGO_PATH),
    "tiktok": ("TikTok", paths.TIKTOK_LOGO_PATH),
}


def platform_name(platform):
    return PLATFORMS.get(platform, (platform.title(), None))[0]


def platform_logo(platform):
    return PLATFORMS.get(platform, (None, None))[1]


def options_text(job):
    """Short description of what was asked for: "MP4 · 720p", "3 medya", "Gönderiler, Reels"."""
    options = job.options or {}
    if job.platform == "youtube":
        return " · ".join(p for p in (options.get("format"), options.get("quality")) if p)
    if job.platform == "instagram":
        if options.get("mode") == "post":
            count = len(options.get("items") or [])
            return f"{count} medya" if count > 1 else "Gönderi"
        names = {"posts": "Gönderiler", "reels": "Reels", "profile_pic": "Profil fotoğrafı"}
        return ", ".join(names.get(c, c) for c in options.get("categories") or [])
    return ""


def fmt_percent(fraction):
    return f"%{min(max(fraction, 0), 1) * 100:.0f}"


def active_status(job):
    """One line under the progress bar of a queued/running job."""
    progress = job.progress
    if job.status == jobs.QUEUED:
        return "Sırada bekliyor"
    if job.status == jobs.PROCESSING:
        return progress.stage or "İşleniyor"
    if progress.stage == CANCELLING or not progress.downloaded:
        # No byte counts (yet): the runner's own stage text says what's going on.
        return progress.stage or "Hazırlanıyor"
    size = fmt_percent(progress.fraction) if progress.fraction is not None else fmt_bytes(progress.downloaded)
    eta = f"Kalan {fmt_eta(progress.eta)}" if progress.eta else ""
    return _join(size, fmt_speed(progress.speed), eta)


def finished_status(job, file_exists=True, now=None):
    """(text, color) for a finished job's detail line."""
    when = fmt_when(job.finished_at, now)
    if job.status == jobs.FAILED:
        return job.error or "İndirme başarısız oldu.", ERROR
    if job.status == jobs.CANCELLED:
        return _join("İptal edildi", when), TEXT_FAINT
    if not job.files:
        return _join("İndirilecek yeni dosya yoktu", when), TEXT_MUTED
    if not file_exists:
        return "Dosya bulunamadı (taşınmış veya silinmiş)", TEXT_FAINT
    size = fmt_bytes(job.size) if job.size else ""
    count = f"{len(job.files)} dosya" if len(job.files) > 1 else ""
    if job.already_existed:
        return _join("Zaten indirilmişti", count, when), TEXT_MUTED
    return _join("Tamamlandı", count, size, when), SUCCESS


def fmt_when(timestamp, now=None):
    """"14:32" today, "Dün 14:32", else "12.09.2026"."""
    if not timestamp:
        return ""
    now = time.time() if now is None else now
    then = time.localtime(timestamp)
    today = time.localtime(now)
    if then[:3] == today[:3]:
        return time.strftime("%H:%M", then)
    yesterday = time.localtime(now - 86400)
    if then[:3] == yesterday[:3]:
        return time.strftime("Dün %H:%M", then)
    return time.strftime("%d.%m.%Y", then)


def _join(*parts):
    return "  ·  ".join(p for p in parts if p)
