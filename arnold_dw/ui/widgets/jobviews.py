"""Widgets that show download jobs: a row of the Downloads list and the compact strip.

Finished rows are built from plain Tk widgets (labels showing cached rounded
images) instead of CTk ones: every CTk widget owns a canvas and costs several
ms to create, which made a 40-row page of the history take ~3 s to appear.
They follow CTk's widget scaling so both kinds look the same.
"""

import tkinter as tk
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from arnold_dw.core import jobs
from arnold_dw.ui import jobtext
from arnold_dw.ui.imaging import hex_rgb, make_rounded
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
        self._photos = {}  # PhotoImages for the plain Tk widgets

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
        for key in [k for k in self._photos if k[1] == job_id]:
            del self._photos[key]

    def thumb_photo(self, job, size, scale):
        """Rounded cover (or the platform logo on a placeholder) as one opaque Tk image."""
        key = ("thumb", job.id, size, scale)
        if key not in self._photos:
            pixels = (round(size[0] * scale), round(size[1] * scale))
            radius = round(7 * scale)
            if job.thumbnail_image is not None:
                image = _on_background(make_rounded(job.thumbnail_image, pixels, radius=radius), SURFACE)
            else:
                image = _pill_image(pixels, radius, SURFACE_2, SURFACE).copy()
                logo = _logo_image(jobtext.platform_logo(job.platform), round(18 * scale))
                if logo is not None:
                    image.paste(logo, ((pixels[0] - logo.width) // 2, (pixels[1] - logo.height) // 2), logo)
            self._photos[key] = ImageTk.PhotoImage(image)
        return self._photos[key]

    def logo_photo(self, platform, size, scale):
        key = ("logo", platform, size, scale)
        if key not in self._photos:
            logo = _logo_image(jobtext.platform_logo(platform), round(size * scale))
            self._photos[key] = ImageTk.PhotoImage(_on_background(logo, SURFACE)) if logo else None
        return self._photos[key]

    def pill_photo(self, pixels, radius, color):
        key = ("pill", None, pixels, radius, color)
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(_pill_image(pixels, radius, color, SURFACE))
        return self._photos[key]


@lru_cache(maxsize=32)
def _pill_image(pixels, radius, color, background):
    """Anti-aliased rounded rectangle on an opaque background (drawn 4x, then scaled down)."""
    k = 4
    image = Image.new("RGB", (pixels[0] * k, pixels[1] * k), hex_rgb(background))
    ImageDraw.Draw(image).rounded_rectangle([(0, 0), (pixels[0] * k - 1, pixels[1] * k - 1)],
                                            radius=radius * k, fill=hex_rgb(color))
    return image.resize(pixels, Image.LANCZOS)


@lru_cache(maxsize=16)
def _logo_image(path, pixels):
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA").resize((pixels, pixels), Image.LANCZOS)
    except OSError:
        return None


def _on_background(image, color):
    out = Image.new("RGB", image.size, hex_rgb(color))
    out.paste(image, (0, 0), image)
    return out


def _scaling(widget):
    return ctk.ScalingTracker.get_widget_scaling(widget)


def _font(widget, size, weight="normal"):
    # A negative size is in pixels - what CTk uses - so these match the CTk labels.
    return (FONT_FAMILY, -round(size * _scaling(widget)), weight)


def _px(widget, value):
    if isinstance(value, tuple):
        return tuple(_px(widget, v) for v in value)
    return round(value * _scaling(widget))


class _Pill(tk.Label):
    """Looks like `_small_button` but is a label showing a cached rounded image (~0.3 ms to build)."""

    def __init__(self, parent, images, text, command, primary=False, width=60, height=26):
        scale = _scaling(parent)
        pixels, radius = (round(width * scale), round(height * scale)), round(7 * scale)
        colors = (ACCENT, ACCENT_HOVER) if primary else (SURFACE_2, SURFACE_3)
        self._normal, self._hover = (images.pill_photo(pixels, radius, c) for c in colors)
        super().__init__(parent, text=text, image=self._normal, compound="center", fg=TEXT, bg=SURFACE,
                         font=_font(parent, 11, "bold"), bd=0, highlightthickness=0, padx=0, pady=0,
                         cursor="hand2")
        self._command = command
        self.bind("<Enter>", lambda _e: self.configure(image=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(image=self._normal))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_release(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self._command()

    def invoke(self):
        self._command()


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
        super().__init__(parent, height=height, corner_radius=3, fg_color=SURFACE_2, progress_color=SURFACE_2)
        self.set(0)
        self._bouncing = False
        self._empty = True  # CTk draws a rounded cap even at 0: hide it with the track color

    def show(self, job):
        fraction = job.progress.fraction
        busy = job.status == jobs.PROCESSING or (job.status == jobs.RUNNING and fraction is None)
        if busy and not self._bouncing:
            self._bouncing = True
            self._set_empty(False)
            self.configure(mode="indeterminate")
            self.start()
        elif not busy:
            if self._bouncing:
                self._bouncing = False
                self.stop()
                self.configure(mode="determinate")
            value = min(max(fraction or 0, 0), 1)
            self._set_empty(value <= 0)
            self.set(value)

    def _set_empty(self, empty):
        if empty != self._empty:
            self._empty = empty
            self.configure(progress_color=SURFACE_2 if empty else ACCENT)

    def destroy(self):
        self.stop()  # the indeterminate loop runs on its own `after` timer
        super().destroy()


class JobRow(ctk.CTkFrame):
    """One job in the Downloads list. `actions` provides cancel/retry/remove/open/reveal(job_id).

    A row is either active (progress bar, İptal) or finished (detail line and
    action buttons); the list replaces the row when a job moves between them.
    """

    TITLE_WIDTH = 282

    def __init__(self, parent, job, images, actions):
        super().__init__(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        self.job_id = job.id
        self.active = job.is_active
        self._images = images
        self._actions = actions
        self._file_exists = True
        self._job = job
        self._shown_key = None
        self._action_key = None
        self.grid_columnconfigure(1, weight=1)
        if self.active:
            self._build_active(job)
        else:
            self._build_finished(job)
        self.update_job(job)

    def _build_active(self, job):
        self.thumb = _Thumb(self, self._images, job, ROW_THUMB)
        self.thumb.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(10, 10), pady=10)
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))
        logo = self._images.logo(job.platform)
        if logo is not None:
            ctk.CTkLabel(title_row, text="", image=logo, width=14).pack(side="left", padx=(0, 6))
        self.title_label = ctk.CTkLabel(title_row, text="", text_color=TEXT, font=(FONT_FAMILY, 12, "bold"),
                                        anchor="w", height=20)
        self.title_label.pack(side="left", fill="x", expand=True)
        self.bar = _Bar(self)
        self.bar.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(6, 2))
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
        self.status_label = ctk.CTkLabel(bottom, text="", text_color=TEXT_MUTED, font=(FONT_FAMILY, 11),
                                         anchor="w", height=26)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.cancel_btn = _small_button(bottom, "İptal", lambda: self._actions.cancel(self.job_id), width=58)
        self.cancel_btn.pack(side="right")

    def _build_finished(self, job):
        # Plain Tk widgets on the CTk frame: grid paddings are scaled by hand here.
        scale = _scaling(self)
        self.thumb = tk.Label(self, image=self._images.thumb_photo(job, ROW_THUMB, scale), bg=SURFACE, bd=0)
        self.thumb.grid(row=0, column=0, rowspan=3, sticky="nw", padx=_px(self, (10, 10)), pady=_px(self, 10))
        title_row = tk.Frame(self, bg=SURFACE)
        title_row.grid(row=0, column=1, sticky="ew", padx=_px(self, (0, 10)), pady=_px(self, (9, 0)))
        logo = self._images.logo_photo(job.platform, 14, scale)
        if logo is not None:
            tk.Label(title_row, image=logo, bg=SURFACE, bd=0).pack(side="left", padx=_px(self, (0, 6)))
        self.title_label = tk.Label(title_row, text="", fg=TEXT, bg=SURFACE, font=_font(self, 12, "bold"),
                                    anchor="w", bd=0, padx=0, pady=0)
        self.title_label.pack(side="left", fill="x", expand=True)
        self.detail_label = tk.Label(self, text="", bg=SURFACE, font=_font(self, 11), anchor="w",
                                     bd=0, padx=0, pady=0)
        self.detail_label.grid(row=1, column=1, sticky="ew", padx=_px(self, (0, 10)), pady=_px(self, (3, 0)))
        self.buttons = tk.Frame(self, bg=SURFACE)
        self.buttons.grid(row=2, column=1, sticky="ew", padx=_px(self, (0, 10)), pady=_px(self, (6, 10)))

    def update_job(self, job):
        self._job = job
        if self.active:
            self.title_label.configure(
                text=fit_text(job.title or job.url, self.TITLE_WIDTH, FONT_FAMILY, 12, "bold"))
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
        # The list re-sends every row on each change; skip the ones that look the same.
        key = (job.title, job.url, job.status, tuple(job.files), job.already_existed, job.size, job.error,
               job.finished_at, self._file_exists)
        if key == self._shown_key:
            return
        self._shown_key = key
        self.title_label.configure(
            text=fit_text(job.title or job.url, self.TITLE_WIDTH, FONT_FAMILY, 12, "bold"))
        text, color = jobtext.finished_status(job, self._file_exists)
        extra = jobtext.options_text(job)
        if extra and job.status != jobs.FAILED:
            text = f"{extra}  ·  {text}"
        self.detail_label.configure(text=fit_text(text, self.TITLE_WIDTH + 14, FONT_FAMILY, 11), fg=color)
        if job.status == jobs.DONE and job.files and self._file_exists:
            action = "open"
        elif job.status == jobs.DONE and job.files:
            action = "missing"
        else:
            action = "retry"
        if action == self._action_key:
            return
        self._action_key = action
        for child in self.buttons.winfo_children():
            child.destroy()
        a, job_id = self._actions, job.id
        if action == "open":
            specs = [("Aç", lambda: a.open(job_id), True, 44),
                     ("Klasörde göster", lambda: a.reveal(job_id), False, 112)]
        elif action == "missing":
            specs = [("Tekrar indir", lambda: a.retry(job_id), True, 92)]
        else:
            specs = [("Tekrar dene", lambda: a.retry(job_id), True, 90)]
        specs.append(("Listeden kaldır", lambda: a.remove(job_id), False, 108))
        for text, command, primary, width in specs:
            _Pill(self.buttons, self._images, text, command, primary, width).pack(
                side="left", padx=_px(self, (0, 6)))


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
