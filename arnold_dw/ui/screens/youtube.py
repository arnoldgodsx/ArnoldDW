"""YouTube screen: paste a link -> preview -> MP4/MP3 + quality -> download."""

import logging
import threading

import customtkinter as ctk

from arnold_dw.core import formats, youtube
from arnold_dw.core.errors import DownloadCancelled, friendly_error
from arnold_dw.core.text import fmt_bytes, fmt_duration, fmt_eta, fmt_speed
from arnold_dw.ui.imaging import compose_spinner_frame, dim_image, make_rounded, spinner_sprite
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
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)
from arnold_dw.ui.widgets.dropdown import ThemedDropdown
from arnold_dw.ui.widgets.inputs import InputRow, SaveLocation

log = logging.getLogger(__name__)

PREVIEW_DEBOUNCE_MS = 550
FINISH_DELAY_MS = 1800


class YouTubeScreen(Screen):
    name = "youtube"

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

        self._processing_active = False
        self._processing_job = None
        self._processing_angle = 0
        self._processing_tick_count = 0
        self._processing_dots = 0
        self._processing_base_img = None
        self._processing_images = {}

        self._progress_indeterminate = False
        self._is_downloading = False
        self.cancel_event = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self):
        self._build_url_section()
        self._build_preview()
        self._build_options()
        self.save_location = SaveLocation(self, self.app)
        self.save_location.pack(fill="x", pady=(0, 18))
        self._build_download_button()
        self._build_progress()

        self._prepare_progress_layout()

    def _prepare_progress_layout(self):
        # Measure the progress widgets once without changing the fixed 1:1.5
        # application window, then hide them until a download starts.
        self.progress_frame.pack(fill="x", pady=(0, 6))
        self._show_progress_info_row()
        self.update_idletasks()
        self.progress_info_row.pack_forget()
        self.progress_frame.pack_forget()

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
            height=PREVIEW_H + 84, width=PREVIEW_W + 16,
        )
        self.preview_card.pack(fill="x", pady=(0, 14))
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
            font=(FONT_FAMILY, 14, "bold"), wraplength=PREVIEW_W,
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
        row.pack(fill="x", pady=(0, 14))
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
            height=50, corner_radius=12, state="disabled",
            fg_color=SURFACE_3, hover_color=ACCENT_HOVER,
            text_color=TEXT, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.download_btn.pack(fill="x", pady=(0, 14))

    def _build_progress(self):
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame, height=8, corner_radius=6,
            fg_color=SURFACE_2, progress_color=ACCENT,
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        # Shown while actively downloading: percent (left) / speed (center) /
        # remaining time (right). Swapped out for progress_label below during
        # every other phase (starting, processing, done, cancelled, error).
        self.progress_info_row = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.progress_info_row.grid_columnconfigure(0, weight=1, uniform="prog")
        self.progress_info_row.grid_columnconfigure(1, weight=1, uniform="prog")
        self.progress_info_row.grid_columnconfigure(2, weight=1, uniform="prog")

        self.progress_percent_label = ctk.CTkLabel(
            self.progress_info_row, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="w",
        )
        self.progress_percent_label.grid(row=0, column=0, sticky="ew")

        self.progress_speed_label = ctk.CTkLabel(
            self.progress_info_row, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="center",
        )
        self.progress_speed_label.grid(row=0, column=1, sticky="ew")

        self.progress_eta_label = ctk.CTkLabel(
            self.progress_info_row, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="e",
        )
        self.progress_eta_label.grid(row=0, column=2, sticky="ew")

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="w",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_busy(self):
        return self._is_downloading or self._processing_active

    def shutdown(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
        return super().shutdown()

    def destroy(self):
        # CTkProgressBar's indeterminate loop runs on its own `after` timer.
        progress_bar = getattr(self, "progress_bar", None)
        if progress_bar is not None:
            progress_bar.stop()
        super().destroy()

    def _go_home(self):
        if self.is_busy():
            return
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

    def _show_progress_info_row(self):
        self.progress_label.pack_forget()
        if not self.progress_info_row.winfo_ismapped():
            self.progress_info_row.pack(fill="x", pady=(6, 0))

    def _show_progress_message(self, text, color=TEXT_MUTED):
        self.progress_info_row.pack_forget()
        self.progress_label.configure(text=text, text_color=color)
        if not self.progress_label.winfo_ismapped():
            self.progress_label.pack(fill="x", pady=(6, 0))

    def _set_progress_indeterminate(self, indeterminate):
        """Bouncing bar while the download size is unknown; a real fraction otherwise."""
        if indeterminate == self._progress_indeterminate:
            return
        self._progress_indeterminate = indeterminate
        if indeterminate:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")

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
            rounded = None
            if preview.thumbnail is not None:
                rounded = make_rounded(preview.thumbnail, (PREVIEW_W, PREVIEW_H), radius=32)
            self.post("preview_ok", rid, preview, rounded)
        except Exception as exc:
            log.warning("YouTube preview failed for %s", url, exc_info=True)
            self.post("preview_err", rid, friendly_error(exc))

    def on_preview_ok(self, rid, preview, rounded_thumb):
        if rid == self.request_id and preview.url == self.url_entry.get().strip():
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
        self._stop_processing_animation()
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
    # Processing (post-download) animation
    # ------------------------------------------------------------------

    def _start_processing_animation(self):
        self._set_progress_indeterminate(False)
        self._processing_active = True
        self._processing_angle = 0
        self._processing_tick_count = 0
        self._processing_dots = 0
        self._processing_images = {}
        self._processing_base_img = (
            dim_image(self._thumb_pil_image) if self._thumb_pil_image is not None else None
        )
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self._tick_processing()

    def _tick_processing(self):
        if not self._processing_active:
            return

        self._processing_tick_count += 1
        if self._processing_tick_count % 4 == 0:
            self._processing_dots = (self._processing_dots + 1) % 4
            self.progress_label.configure(text="İşleniyor" + "." * self._processing_dots)

        if self._processing_base_img is not None:
            angle = self._processing_angle
            image = self._processing_images.get(angle)
            if image is None:
                frame = compose_spinner_frame(self._processing_base_img, angle)
                image = self._processing_images[angle] = ctk.CTkImage(frame, size=(PREVIEW_W, PREVIEW_H))
            self.thumb_label.configure(image=image)
            self._processing_angle = (angle + SPINNER_STEP) % 360

        self._processing_job = self.schedule(SPINNER_INTERVAL, self._tick_processing)

    def _stop_processing_animation(self):
        self._processing_active = False
        self._processing_job = self.cancel_job(self._processing_job)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self._progress_indeterminate = False
        self._processing_base_img = None
        self._processing_images = {}
        if self.thumb_ctk_image is not None:
            self.thumb_label.configure(image=self.thumb_ctk_image)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _on_download_btn_clicked(self):
        if self._is_downloading:
            self._cancel_download()
        else:
            self._start_download()

    def _start_download(self):
        if not self.current_info or not self.current_url:
            return

        self._is_downloading = True
        self.cancel_event = threading.Event()

        self.download_btn.configure(
            state="normal", fg_color=SURFACE_2, hover_color=SURFACE_3, text="İptal Et",
        )
        self.input_row.set_locked(True)
        self._set_format_seg_enabled(False)
        self.quality_menu.configure(state="disabled")
        self.save_location.set_enabled(False)

        self.progress_bar.set(0)
        self.progress_frame.pack(fill="x", pady=(0, 6))
        self._show_progress_message("İndirme başlatılıyor...")

        self.start_worker(
            self._download_worker,
            self.current_url, self.format_var.get(), self.quality_var.get(),
            self.app.download_dir, self.cancel_event,
            track=True,
        )

    def _cancel_download(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.download_btn.configure(state="disabled", fg_color=SURFACE_3, text="İptal ediliyor...")

    def _download_worker(self, url, fmt, quality, download_dir, cancel_event):
        try:
            youtube.download(
                url, fmt, quality, download_dir, cancel_event,
                on_progress=lambda *progress: self.post("progress", *progress),
                on_processing=lambda: self.post("processing"),
            )
            self.post("done")
        except DownloadCancelled:
            self.post("cancelled")
        except Exception as exc:
            log.exception("YouTube download failed: %s (%s %s)", url, fmt, quality)
            self.post("download_err", friendly_error(exc))

    def on_progress(self, fraction, downloaded, speed, eta):
        if self._processing_active:
            return
        self._show_progress_info_row()
        if fraction is None:
            self._set_progress_indeterminate(True)
            self.progress_percent_label.configure(text=fmt_bytes(downloaded))
        else:
            self._set_progress_indeterminate(False)
            self.progress_bar.set(min(max(fraction, 0), 1))
            self.progress_percent_label.configure(text=f"%{fraction * 100:.0f}")
        self.progress_speed_label.configure(text=fmt_speed(speed))
        self.progress_eta_label.configure(text=f"Kalan: {fmt_eta(eta)}" if eta else "")

    def on_processing(self):
        self._is_downloading = False
        self.download_btn.configure(state="disabled", fg_color=SURFACE_3, text="İşleniyor...")
        self._show_progress_message("İşleniyor")
        self._start_processing_animation()

    def on_done(self):
        self._is_downloading = False
        self._stop_processing_animation()
        self.progress_bar.set(1)
        self._show_progress_message("Tamamlandı", SUCCESS)
        self.schedule(FINISH_DELAY_MS, self._finish_download_ui)

    def on_cancelled(self):
        self._is_downloading = False
        self._stop_processing_animation()
        self.progress_bar.set(0)
        self._show_progress_message("İndirme iptal edildi")
        self._restore_inputs()

    def on_download_err(self, err):
        self._is_downloading = False
        self._stop_processing_animation()
        self.progress_bar.set(0)
        self._show_progress_message(err, ERROR)
        self._restore_inputs()

    def _finish_download_ui(self):
        self._restore_inputs()
        self.progress_frame.pack_forget()
        self.progress_bar.set(0)
        self.format_var.set(formats.FORMAT_MP4)
        self._on_format_changed(formats.FORMAT_MP4)
        self._reset_preview(clear_url=True)

    def _restore_inputs(self):
        has_preview = self.current_info is not None
        self._is_downloading = False
        self.cancel_event = None
        self._set_cta_enabled(self.download_btn, has_preview, text="İndir")
        self.input_row.set_locked(False)
        self._set_format_seg_enabled(has_preview)
        self.quality_menu.configure(state="normal" if has_preview else "disabled")
        self.save_location.set_enabled(True)
        self._update_clear_btn_visibility()
