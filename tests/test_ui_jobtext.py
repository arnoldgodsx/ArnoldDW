"""Status lines of the downloads list (pure text, no Tk)."""

import time

from arnold_dw.core import jobs
from arnold_dw.core.jobs import DownloadJob, Progress
from arnold_dw.ui import jobtext
from arnold_dw.ui.theme import ERROR, SUCCESS

NOW = time.mktime((2026, 9, 28, 15, 0, 0, 0, 0, -1))


def job(status=jobs.DONE, **kw):
    j = DownloadJob(platform="youtube", url="u", title="t", download_dir="d",
                    options={"format": "MP4", "quality": "720p"})
    j.status = status
    j.finished_at = NOW - 60
    for key, value in kw.items():
        setattr(j, key, value)
    return j


def test_active_status_lines():
    assert jobtext.active_status(job(jobs.QUEUED)) == "Sırada bekliyor"
    assert jobtext.active_status(job(jobs.PROCESSING, progress=Progress(stage="Birleştiriliyor"))) == \
        "Birleştiriliyor"
    running = job(jobs.RUNNING, progress=Progress(downloaded=5_000_000, fraction=0.45, speed=2.4e6, eta=17))
    line = jobtext.active_status(running)
    assert line.startswith("%45") and "Kalan" in line
    assert jobtext.active_status(job(jobs.RUNNING, progress=Progress(stage="Hazırlanıyor"))) == "Hazırlanıyor"
    cancelling = job(jobs.RUNNING, progress=Progress(downloaded=10, fraction=0.1, stage=jobs.CANCELLING))
    assert jobtext.active_status(cancelling) == jobs.CANCELLING


def test_finished_status_lines():
    assert jobtext.finished_status(job(jobs.FAILED, error="Ağ hatası"), now=NOW) == ("Ağ hatası", ERROR)
    assert jobtext.finished_status(job(jobs.CANCELLED), now=NOW)[0].startswith("İptal edildi")
    assert jobtext.finished_status(job(files=[]), now=NOW)[0].startswith("İndirilecek yeni dosya yoktu")
    text, color = jobtext.finished_status(job(files=["a.mp4"], size=2048), now=NOW)
    assert text.startswith("Tamamlandı") and color == SUCCESS
    assert jobtext.finished_status(job(files=["a.mp4"], already_existed=True), now=NOW)[0] \
        .startswith("Zaten indirilmişti")
    assert jobtext.finished_status(job(files=["a.mp4"]), file_exists=False, now=NOW)[0] \
        .startswith("Dosya bulunamadı")


def test_options_text_and_platform_names():
    assert jobtext.options_text(job()) == "MP4 · 720p"
    post = DownloadJob(platform="instagram", url="u", title="t", download_dir="d",
                       options={"mode": "post", "items": [1, 2, 3]})
    assert jobtext.options_text(post) == "3 medya"
    profile = DownloadJob(platform="instagram", url="u", title="t", download_dir="d",
                          options={"mode": "profile", "categories": ["posts", "reels"]})
    assert jobtext.options_text(profile) == "Gönderiler, Reels"
    assert jobtext.platform_name("youtube") == "YouTube"
    assert jobtext.platform_name("vimeo") == "Vimeo" and jobtext.platform_logo("vimeo") is None


def test_fmt_when():
    assert jobtext.fmt_when(NOW - 60, NOW) == "14:59"
    assert jobtext.fmt_when(NOW - 86400, NOW).startswith("Dün")
    assert jobtext.fmt_when(NOW - 10 * 86400, NOW) == "18.09.2026"
    assert jobtext.fmt_when(None, NOW) == ""
