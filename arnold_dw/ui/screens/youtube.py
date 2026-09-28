"""YouTube screen: paste a link -> preview -> MP4/MP3 + quality -> queue the download."""

import logging

import customtkinter as ctk

from arnold_dw.core import formats, runners, youtube
from arnold_dw.core.errors import friendly_error
from arnold_dw.core.jobs import DownloadJob
from arnold_dw.core.text import fmt_duration
from arnold_dw.ui.imaging import job_thumbnail, make_rounded, spinner_sprite
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    ERROR,
    FONT_FAMILY,
    PREVIEW_H,
    PREVIEW_W,
    SPINNER_INTERVAL,
    SPINNER_STEP,
    SUCCESS,
    SURFACE,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)
from arnold_dw.ui.widgets.dropdown import ThemedDropdown
from arnold_dw.ui.widgets.inputs import InputRow, SaveLocation
from arnold_dw.ui.widgets.jobviews import JobStrip

log = logging.getLogger(__name__)

PREVIEW_DEBOUNCE_MS = 550


class YouTubeScreen(Screen):
    name = "youtube"
    tab = "home"

    def __init__(self, app):
        super().__init__(app)
        self.current_info = None
        self.current_url = None
        self.request_id = 0
        self.debounce_job = None
        self._last_url = ""
        self.thumb_ctk_image = None
        self._thumb_pil_image = None

        self._preview_spin_job = None
        self._preview_spin_angle = 0
        self._spinner_images = {}

        self._job_thumb = None  # small PIL cover handed to the queued job

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self):
        self._build_url_section()
        self._build_preview()
        self._build_options()
        self.save_location = SaveLocation(self, self.app)
        self.save_location.pack(fill="x", pady=(0, 12))
        self._build_download_button()
        self.strip = JobStrip(self, self.app)
        self.strip.refresh()

    def _build_url_section(self):
        self.input_row = InputRow(
            self,
            placeholder="YouTube video bağlantısını yapıştırın...",
            on_back=self._go_home,
            on_change=self._on_url_changed,
            on_clear=self._on_clear_clicked,
        )
        self.input_row.pack(fill="x", pady=(0, 4))
        self.url_entry = self.input_row.entry

        self.status_label = ctk.CTkLabel(
            self, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="w", justify="left",
        )
        self.status_label.pack(fill="x", pady=(0, 4))

    def _build_preview(self):
        self.preview_card = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=10,
            border_width=1, border_color=BORDER,
            height=PREVIEW_H + 78, width=PREVIEW_W + 16,
        )
        self.preview_card.pack(fill="x", pady=(0, 10))
        self.preview_card.pack_propagate(False)

        # Empty state
        self.empty_state = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        self.empty_state.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            self.empty_state, text="🎬", font=(FONT_FAMILY, 34),
            text_color=TEXT_FAINT,
        ).pack()
        ctk.CTkLabel(
            self.empty_state, text="Video önizlemesi burada görünecek",
            text_color=TEXT_FAINT, font=(FONT_FAMILY, 13),
        ).pack(pady=(6, 0))

        # Loading state (spinning circle while metadata is fetched)
        self.loading_state = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        self.loading_icon_label = ctk.CTkLabel(self.loading_state, text="")
        self.loading_icon_label.pack()
        ctk.CTkLabel(
            self.loading_state, text="Yükleniyor…",
            text_color=TEXT_FAINT, font=(FONT_FAMILY, 13),
        ).pack(pady=(8, 0))

        # Filled state (built but not placed until needed)
        self.filled_state = ctk.CTkFrame(self.preview_card, fg_color="transparent")

        self.thumb_label = ctk.CTkLabel(self.filled_state, text="")
        self.thumb_label.pack(pady=(8, 10))

        self.title_label = ctk.CTkLabel(
            self.filled_state, text="", text_color=TEXT,
            font=(FONT_FAMILY, 14, "bold"), wraplength=PREVIEW_W + 60,
            justify="left", anchor="w",
        )
        self.title_label.pack(fill="x", padx=16)

        self.meta_label = ctk.CTkLabel(
            self.filled_state, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="w", justify="left",
        )
        self.meta_label.pack(fill="x", padx=16, pady=(3, 8))

    def _build_options(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        # `uniform` locks both columns to the same width always, so swapping
        # MP4 <-> MP3 (which changes the label text length) can never make one
        # side shrink to make room for the other - that was the source of the
        # quality bar visibly shifting left/right.
        row.grid_columnconfigure(0, weight=1, uniform="opt_cols")
        row.grid_columnconfigure(1, weight=1, uniform="opt_cols")

        # Format
        fmt_col = ctk.CTkFrame(row, fg_color="transparent")
        fmt_col.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(
            fmt_col, text="FORMAT", text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=(8, 0), pady=(0, 6))

        self.format_var = ctk.StringVar(value=formats.FORMAT_MP4)
        self.format_seg = ctk.CTkSegmentedButton(
            fmt_col, values=formats.FORMATS, variable=self.format_var,
            command=self._on_format_changed,
            fg_color=SURFACE, selected_color=SURFACE_3,
            selected_hover_color=SURFACE_3, unselected_color=SURFACE,
            unselected_hover_color=SURFACE_3, text_color=TEXT,
            text_color_disabled=TEXT_MUTED,
            font=(FONT_FAMILY, 13, "bold"), height=40, corner_radius=10,
            state="disabled",
        )
        self.format_seg.pack(fill="x")

        # Quality
        qual_col = ctk.CTkFrame(row, fg_color="transparent")
        qual_col.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.quality_title = ctk.CTkLabel(
            qual_col, text="VİDEO KALİTESİ", text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        )
        self.quality_title.pack(fill="x", padx=(8, 0), pady=(0, 6))

        self.quality_var = ctk.StringVar(value="1080p")
        self.quality_menu = ThemedDropdown(
            qual_col, values=formats.QUALITY_OPTIONS, variable=self.quality_var,
            height=40, corner_radius=10, font=(FONT_FAMILY, 13, "bold"), state="disabled",
        )
        self.quality_menu.pack(fill="x")

    def _build_download_button(self):
        self.download_btn = ctk.CTkButton(
            self, text="İndir", command=self._on_download_btn_clicked,
            height=46, corner_radius=12, state="disabled",
            fg_color=SURFACE_3, hover_color=ACCENT_HOVER,
            text_color=TEXT, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.download_btn.pack(fill="x", pady=(0, 8))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_job_event(self, kind, payload):
        self.strip.refresh()

    def _go_home(self):
        self.app.show_screen("home")

    # ------------------------------------------------------------------
    # Status / button-state helpers
    # ------------------------------------------------------------------

    def _set_status(self, text, color=TEXT_MUTED):
        self.status_label.configure(text=text, text_color=color)

    def _set_cta_enabled(self, btn, enabled, text=None):
        kwargs = {
            "state": "normal" if enabled else "disabled",
            "fg_color": ACCENT if enabled else SURFACE_3,
            "hover_color": ACCENT_HOVER,
        }
        if text is not None:
            kwargs["text"] = text
        btn.configure(**kwargs)

    def _set_format_seg_enabled(self, enabled):
        self.format_seg.configure(
            state="normal" if enabled else "disabled",
            selected_color=ACCENT if enabled else SURFACE_3,
            selected_hover_color=ACCENT_HOVER if enabled else SURFACE_3,
        )

    def _show_filled_preview(self):
        self._stop_preview_spinner()
        self.empty_state.place_forget()
        self.loading_state.place_forget()
        self.filled_state.pack(fill="both", expand=True)

    def _show_empty_preview(self):
        self._stop_preview_spinner()
        self.filled_state.pack_forget()
        self.loading_state.place_forget()
        self.empty_state.place(relx=0.5, rely=0.5, anchor="center")

    def _show_loading_preview(self):
        self.empty_state.place_forget()
        self.filled_state.pack_forget()
        self.loading_state.place(relx=0.5, rely=0.5, anchor="center")

    def _update_clear_btn_visibility(self):
        has_content = bool(self.url_entry.get().strip()) or self.current_info is not None
        self.input_row.set_clear_visible(has_content)

    # ------------------------------------------------------------------
    # Clear button
    # ------------------------------------------------------------------

    def _on_clear_clicked(self):
        self.debounce_job = self.cancel_job(self.debounce_job)
        self.request_id += 1  # invalidate any in-flight fetch
        self._reset_preview(clear_url=True)

    # ------------------------------------------------------------------
    # URL change / preview fetching
    # ------------------------------------------------------------------

    def _on_url_changed(self):
        url = self.url_entry.get().strip()
        # Key releases that don't edit the link (arrows, Ctrl+C, ...) change nothing.
        if url == self._last_url:
            return
        self._last_url = url

        self.debounce_job = self.cancel_job(self.debounce_job)
        # A fetch still running for the previous text must not land on this one.
        self.request_id += 1

        if self.current_info is not None:
            self._reset_preview(clear_url=False)
        elif self._preview_spin_job is not None:
            self._show_empty_preview()

        # Any earlier warning (e.g. "invalid link") is stale the moment the
        # text changes - clear it immediately instead of leaving it stuck
        # until a fresh fetch happens to overwrite it.
        self._set_status("")
        self._update_clear_btn_visibility()

        if not url:
            return

        self.debounce_job = self.schedule(PREVIEW_DEBOUNCE_MS, self._try_fetch_preview)

    def _try_fetch_preview(self):
        self.debounce_job = None
        url = self.url_entry.get().strip()
        if not url:
            return
        if not youtube.is_youtube_url(url):
            self._set_status("Geçerli bir YouTube bağlantısı girin", ERROR)
            return

        self.request_id += 1
        rid = self.request_id
        self._start_preview_spinner()
        self.start_worker(self._fetch_preview_worker, url, rid)

    def _fetch_preview_worker(self, url, rid):
        # Worker thread: network + PIL work only, results go through post().
        try:
            preview = youtube.fetch_preview(url)
            rounded = job_thumb = None
            if preview.thumbnail is not None:
                rounded = make_rounded(preview.thumbnail, (PREVIEW_W, PREVIEW_H), radius=32)
                job_thumb = job_thumbnail(preview.thumbnail)
            self.post("preview_ok", rid, preview, rounded, job_thumb)
        except Exception as exc:
            log.warning("YouTube preview failed for %s", url, exc_info=True)
            self.post("preview_err", rid, friendly_error(exc))

    def on_preview_ok(self, rid, preview, rounded_thumb, job_thumb):
        if rid == self.request_id and preview.url == self.url_entry.get().strip():
            self._job_thumb = job_thumb
            self._apply_preview(preview.url, preview.info, rounded_thumb)

    def on_preview_err(self, rid, err):
        if rid == self.request_id:
            self._show_empty_preview()
            self._set_status(err, ERROR)
            self._update_clear_btn_visibility()

    def _apply_preview(self, url, info, rounded_thumb):
        self.current_info = info
        self.current_url = url

        title = info.get("title") or "Bilinmeyen başlık"
        uploader = info.get("uploader") or info.get("channel") or ""
        duration = fmt_duration(info.get("duration"))

        meta_parts = [p for p in (uploader, duration) if p]
        meta_text = "  •  ".join(meta_parts)

        self.title_label.configure(text=title)
        self.meta_label.configure(text=meta_text)

        if rounded_thumb is not None:
            self._thumb_pil_image = rounded_thumb
            self.thumb_ctk_image = ctk.CTkImage(rounded_thumb, size=(PREVIEW_W, PREVIEW_H))
            self.thumb_label.configure(image=self.thumb_ctk_image, text="")
        else:
            self._thumb_pil_image = None
            self.thumb_ctk_image = None
            self.thumb_label.configure(
                image=None, text="Kapak yüklenemedi",
                text_color=TEXT_FAINT, font=(FONT_FAMILY, 12),
            )

        self._show_filled_preview()
        self._update_clear_btn_visibility()
        self._set_status("")

        self.quality_menu.configure(state="normal")
        self._set_format_seg_enabled(True)
        self._set_cta_enabled(self.download_btn, True)

        if self.format_var.get() == formats.FORMAT_MP4:
            max_h = formats.max_available_height(info)
            self.quality_menu.configure(values=formats.available_quality_options(max_h))
            self.quality_var.set(formats.pick_default_quality(max_h))

    def _reset_preview(self, clear_url=True):
        self.current_info = None
        self.current_url = None
        self.thumb_ctk_image = None
        self._thumb_pil_image = None
        self._job_thumb = None
        self._show_empty_preview()
        self._set_cta_enabled(self.download_btn, False, text="İndir")
        self.quality_menu.configure(state="disabled")
        self._set_format_seg_enabled(False)
        if clear_url:
            self.url_entry.delete(0, "end")
            self._last_url = ""
            self.app.focus_set()
        self._set_status("")
        self._update_clear_btn_visibility()

    # ------------------------------------------------------------------
    # Preview-loading spinner
    # ------------------------------------------------------------------

    def _start_preview_spinner(self):
        self._stop_preview_spinner()
        self._preview_spin_angle = 0
        self._show_loading_preview()
        self._tick_preview_spinner()

    def _tick_preview_spinner(self):
        angle = self._preview_spin_angle
        image = self._spinner_images.get(angle)
        if image is None:
            sprite = spinner_sprite(angle)
            image = self._spinner_images[angle] = ctk.CTkImage(sprite, size=sprite.size)
        self.loading_icon_label.configure(image=image, text="")
        self._preview_spin_angle = (angle + SPINNER_STEP) % 360
        self._preview_spin_job = self.schedule(SPINNER_INTERVAL, self._tick_preview_spinner)

    def _stop_preview_spinner(self):
        self._preview_spin_job = self.cancel_job(self._preview_spin_job)

    # ------------------------------------------------------------------
    # Format change
    # ------------------------------------------------------------------

    def _on_format_changed(self, value):
        if value == formats.FORMAT_MP3:
            self.quality_title.configure(text="SES KALİTESİ")
            self.quality_menu.configure(values=formats.AUDIO_OPTIONS)
            self.quality_var.set(formats.DEFAULT_AUDIO_OPTION)
        else:
            self.quality_title.configure(text="VİDEO KALİTESİ")
            max_h = formats.max_available_height(self.current_info) if self.current_info else 0
            self.quality_menu.configure(values=formats.available_quality_options(max_h))
            self.quality_var.set(formats.pick_default_quality(max_h))

    # ------------------------------------------------------------------
    # Download (queued in the app's DownloadManager)
    # ------------------------------------------------------------------

    def _on_download_btn_clicked(self):
        if not self.current_info or not self.current_url:
            return
        fmt, quality = self.format_var.get(), self.quality_var.get()
        options = runners.youtube_options(fmt, quality)
        manager = self.app.downloads
        if manager.find_active(runners.PLATFORM_YOUTUBE, self.current_url, options) is not None:
            self._set_status("Bu video bu ayarlarla zaten indiriliyor.", TEXT_MUTED)
            return
        title = self.current_info.get("title") or self.current_url
        manager.enqueue(DownloadJob(
            platform=runners.PLATFORM_YOUTUBE, url=self.current_url, title=title,
            download_dir=self.app.download_dir, options=options, thumbnail_image=self._job_thumb,
        ))
        log.info("YouTube download queued: %s (%s %s)", self.current_url, fmt, quality)
        # Ready for the next link right away; the format choice stays for the next video.
        self._reset_preview(clear_url=True)
        self._set_status(f"İndirmelere eklendi ({fmt} · {quality}). Yeni bir bağlantı yapıştırabilirsiniz.",
                         SUCCESS)
        self.url_entry.focus_set()
