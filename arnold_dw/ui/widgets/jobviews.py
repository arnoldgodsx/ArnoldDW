"""Widgets that show download jobs: a row of the Downloads list and the compact strip."""

import customtkinter as ctk
from PIL import Image

from arnold_dw.core import jobs
from arnold_dw.ui import jobtext
from arnold_dw.ui.imaging import make_rounded
from arnold_dw.ui.textfit import fit_text
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    FONT_FAMILY,
    ICON_FONT,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)

ROW_THUMB = (64, 36)
STRIP_THUMB = (56, 32)


class ImageCache:
    """CTkImages for job covers and platform logos, created once per owner widget."""

    def __init__(self):
        self._thumbs = {}
        self._logos = {}

    def thumb(self, job, size):
        key = (job.id, size)
        image = self._thumbs.get(key)
        if image is None and job.thumbnail_image is not None:
            scale = 2  # render at 2x so it stays crisp when Tk scaling is > 1
            rounded = make_rounded(job.thumbnail_image, (size[0] * scale, size[1] * scale), radius=7 * scale)
            image = self._thumbs[key] = ctk.CTkImage(rounded, size=size)
        return image

    def logo(self, platform, size=14):
        key = (platform, size)
        if key not in self._logos:
            path = jobtext.platform_logo(platform)
            image = None
            if path:
                try:
                    logo = Image.open(path).convert("RGBA")
                    image = ctk.CTkImage(logo, size=(size, size))
                except OSError:
                    image = None
            self._logos[key] = image
        return self._logos[key]

    def forget(self, job_id):
        for key in [k for k in self._thumbs if k[0] == job_id]:
            del self._thumbs[key]


def _small_button(parent, text, command, primary=False, width=None):
    return ctk.CTkButton(
        parent, text=text, command=command, height=26, width=width or 10, corner_radius=7,
        fg_color=ACCENT if primary else SURFACE_2, hover_color=ACCENT_HOVER if primary else SURFACE_3,
        text_color=TEXT, font=(FONT_FAMILY, 11, "bold"), border_spacing=0,
    )


class _Thumb(ctk.CTkLabel):
    def __init__(self, parent, images, job, size):
        super().__init__(parent, text="", width=size[0], height=size[1], fg_color=SURFACE_2,
                         corner_radius=7)
        self._images, self._size = images, size
        self.set_job(job)

    def set_job(self, job):
        image = self._images.thumb(job, self._size)
        if image is not None:
            self.configure(image=image, fg_color="transparent")
        else:
            self.configure(image=self._images.logo(job.platform, 18), fg_color=SURFACE_2)


class _Bar(ctk.CTkProgressBar):
    """Progress bar that animates only while the fraction is unknown."""

    def __init__(self, parent, height=5):
        super().__init__(parent, height=height, corner_radius=3, fg_color=SURFACE_2, progress_color=ACCENT)
        self.set(0)
        self._bouncing = False

    def show(self, job):
        fraction = job.progress.fraction
        busy = job.status == jobs.PROCESSING or (job.status == jobs.RUNNING and fraction is None)
        if busy and not self._bouncing:
            self._bouncing = True
            self.configure(mode="indeterminate")
            self.start()
        elif not busy:
            if self._bouncing:
                self._bouncing = False
                self.stop()
                self.configure(mode="determinate")
            self.set(min(max(fraction or 0, 0), 1))

    def destroy(self):
        self.stop()  # the indeterminate loop runs on its own `after` timer
        super().destroy()


class JobRow(ctk.CTkFrame):
    """One job in the Downloads list. `actions` provides cancel/retry/remove/open/reveal(job_id)."""

    TITLE_WIDTH = 282

    def __init__(self, parent, job, images, actions):
        super().__init__(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        self.job_id = job.id
        self.active = job.is_active
        self._images = images
        self._actions = actions
        self._file_exists = True
        self._job = job
        self._action_key = None

        self.grid_columnconfigure(1, weight=1)
        self.thumb = _Thumb(self, images, job, ROW_THUMB)
        self.thumb.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(10, 10), pady=10)

        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))
        logo = images.logo(job.platform)
        if logo is not None:
            ctk.CTkLabel(title_row, text="", image=logo, width=14).pack(side="left", padx=(0, 6))
        self.title_label = ctk.CTkLabel(title_row, text="", text_color=TEXT, font=(FONT_FAMILY, 12, "bold"),
                                        anchor="w", height=20)
        self.title_label.pack(side="left", fill="x", expand=True)

        if self.active:
            self.bar = _Bar(self)
            self.bar.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(6, 2))
            bottom = ctk.CTkFrame(self, fg_color="transparent")
            bottom.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
            self.status_label = ctk.CTkLabel(bottom, text="", text_color=TEXT_MUTED, font=(FONT_FAMILY, 11),
                                             anchor="w", height=26)
            self.status_label.pack(side="left", fill="x", expand=True)
            self.cancel_btn = _small_button(bottom, "İptal", lambda: actions.cancel(self.job_id), width=58)
            self.cancel_btn.pack(side="right")
        else:
            self.detail_label = ctk.CTkLabel(self, text="", font=(FONT_FAMILY, 11), anchor="w", height=18)
            self.detail_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(1, 0))
            self.buttons = ctk.CTkFrame(self, fg_color="transparent")
            self.buttons.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(4, 9))
        self.update_job(job)

    def update_job(self, job):
        self._job = job
        self.title_label.configure(
            text=fit_text(job.title or job.url, self.TITLE_WIDTH, FONT_FAMILY, 12, "bold"))
        if self.active:
            self.bar.show(job)
            self.status_label.configure(text=jobtext.active_status(job))
            cancelling = job.progress.stage == jobs.CANCELLING or job.status == jobs.PROCESSING
            self.cancel_btn.configure(state="disabled" if cancelling else "normal",
                                      text_color_disabled=TEXT_FAINT)
        else:
            self._update_finished()

    def set_file_exists(self, exists):
        if exists != self._file_exists:
            self._file_exists = exists
            if not self.active:
                self._update_finished()

    def _update_finished(self):
        job = self._job
        text, color = jobtext.finished_status(job, self._file_exists)
        extra = jobtext.options_text(job)
        if extra and job.status != jobs.FAILED:
            text = f"{extra}  ·  {text}"
        self.detail_label.configure(text=fit_text(text, self.TITLE_WIDTH + 14, FONT_FAMILY, 11),
                                    text_color=color)
        if job.status == jobs.DONE and job.files and self._file_exists:
            key = "open"
        elif job.status == jobs.DONE and job.files:
            key = "missing"
        else:
            key = "retry"
        if key == self._action_key:
            return
        self._action_key = key
        for child in self.buttons.winfo_children():
            child.destroy()
        a, job_id = self._actions, job.id
        if key == "open":
            specs = [("Aç", lambda: a.open(job_id), True, 44),
                     ("Klasörde göster", lambda: a.reveal(job_id), False, 112)]
        elif key == "missing":
            specs = [("Tekrar indir", lambda: a.retry(job_id), True, 92)]
        else:
            specs = [("Tekrar dene", lambda: a.retry(job_id), True, 90)]
        specs.append(("Listeden kaldır", lambda: a.remove(job_id), False, 108))
        for text, command, primary, width in specs:
            _small_button(self.buttons, text, command, primary, width).pack(side="left", padx=(0, 6))


class JobStrip(ctk.CTkFrame):
    """Compact view of the most recent download at the bottom of a platform screen.

    Clicking it opens the Downloads screen.
    """

    HEIGHT = 54

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER,
                         height=self.HEIGHT, cursor="hand2")
        self.grid_propagate(False)
        self.app = app
        self._images = ImageCache()
        self._job_id = None
        self._shown = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.thumb = None
        self.thumb_slot = ctk.CTkFrame(self, fg_color="transparent", width=STRIP_THUMB[0],
                                       height=STRIP_THUMB[1])
        self.thumb_slot.grid(row=0, column=0, rowspan=4, padx=(10, 10))
        self.title_label = ctk.CTkLabel(self, text="", text_color=TEXT, font=(FONT_FAMILY, 12, "bold"),
                                        anchor="w", height=18)
        self.title_label.grid(row=1, column=1, sticky="ew")
        self.status_label = ctk.CTkLabel(self, text="", text_color=TEXT_MUTED, font=(FONT_FAMILY, 11),
                                         anchor="w", height=16)
        self.status_label.grid(row=2, column=1, sticky="ew")
        self.bar = _Bar(self, height=3)
        self.bar.grid(row=3, column=1, sticky="new", pady=(3, 0))
        self.chevron = ctk.CTkLabel(self, text="", font=(ICON_FONT, 12), text_color=TEXT_FAINT, width=20)
        self.chevron.grid(row=0, column=2, rowspan=4, padx=(6, 12))
        self._bind_click(self)

    def _bind_click(self, widget):
        widget.bind("<Button-1>", lambda _e: self.app.show_screen("downloads"), add="+")
        for child in widget.winfo_children():
            self._bind_click(child)

    def refresh(self):
        """Show the latest job (hidden while there is none)."""
        job = self.app.downloads.latest()
        if job is None:
            if self._shown:
                self._shown = False
                self.pack_forget()
            self._job_id = None
            return
        if job.id != self._job_id:
            self._job_id = job.id
            if self.thumb is not None:
                self.thumb.destroy()
            self.thumb = _Thumb(self.thumb_slot, self._images, job, STRIP_THUMB)
            self.thumb.place(relx=0.5, rely=0.5, anchor="center")
            self._bind_click(self.thumb)
        self.title_label.configure(text=fit_text(job.title or job.url, 300, FONT_FAMILY, 12, "bold"))
        others = self.app.downloads.active_count() - (1 if job.is_active else 0)
        if job.is_active:
            text, color = jobtext.active_status(job), TEXT_MUTED
            self.bar.show(job)
            self.bar.grid()
        else:
            text, color = jobtext.finished_status(job)
            self.bar.grid_remove()
        if others > 0:
            text = f"{text}  ·  +{others} indirme"
        self.status_label.configure(text=fit_text(text, 300, FONT_FAMILY, 11), text_color=color)
        if not self._shown:
            self._shown = True
            self.pack(side="bottom", fill="x")
