"""Instagram screen: post link (single/carousel) or username/profile link -> download."""

import logging
import threading

import customtkinter as ctk

from arnold_dw.config import save_settings
from arnold_dw.core import instagram
from arnold_dw.core.errors import DownloadCancelled, instagram_friendly_error
from arnold_dw.ui.imaging import make_rounded
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    ERROR,
    FONT_FAMILY,
    HOME_CARD,
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

RESOLVE_DEBOUNCE_MS = 1200
FINISH_DELAY_MS = 1800

SINGLE_PREVIEW_SIZE = (300, 230)
TILE_PREVIEW_SIZE = (104, 120)
AVATAR_SIZE = (72, 72)

PROFILE_CATEGORIES = (
    (instagram.CATEGORY_POSTS, "Gönderiler / Fotoğraflar"),
    (instagram.CATEGORY_REELS, "Reels / Videolar"),
    (instagram.CATEGORY_PROFILE_PIC, "Profil Fotoğrafı"),
)

# Display name for each arnold_dw.core.instagram.SUPPORTED_BROWSERS entry.
BROWSER_LABELS = {"firefox": "Firefox", "edge": "Edge", "chrome": "Chrome", "brave": "Brave"}
BROWSER_BY_LABEL = {label: key for key, label in BROWSER_LABELS.items()}


def progress_text(stage, index, total):
    if stage == instagram.STAGE_POST_ITEM:
        return f"{index}/{total} indiriliyor..."
    if stage == instagram.STAGE_PROFILE_PIC:
        return "Profil fotoğrafı indiriliyor..."
    if stage == instagram.STAGE_POST:
        return f"Gönderi {index} indiriliyor..."
    if stage == instagram.STAGE_REEL:
        return f"Reels/video {index} indiriliyor..."
    return "İndiriliyor..."


class InstagramScreen(Screen):
    name = "instagram"

    # Shared across visits to the screen, bounded (see core.instagram.ProfileCache).
    profile_cache = instagram.ProfileCache()

    def __init__(self, app):
        super().__init__(app)
        self.request_id = 0
        self.debounce_job = None
        self._last_value = ""
        self.instagram_mode = None
        self.instagram_post = None
        self.instagram_profile = None
        self.instagram_profile_avatar = None
        self.instagram_media = []
        self.instagram_media_vars = []
        self.instagram_category_vars = {}
        self.instagram_preview_images = []
        self.browser_choice_var = ctk.StringVar(value=BROWSER_LABELS[instagram.SUPPORTED_BROWSERS[0]])
        self._is_downloading = False
        self.cancel_event = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self):
        self.input_row = InputRow(
            self,
            placeholder="Instagram linki veya kullanıcı adı...",
            on_back=self._go_home,
            on_change=self._on_input_changed,
            on_clear=self._clear_input,
        )
        self.input_row.pack(fill="x", pady=(0, 4))
        self.entry = self.input_row.entry

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12),
            anchor="w",
            justify="left",
        )
        self.status_label.pack(fill="x", pady=(0, 4))

        self.preview_card = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            height=350,
        )
        self.preview_card.pack(fill="x", pady=(0, 14))
        self.preview_card.pack_propagate(False)

        self.preview_content = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        self.preview_content.pack(fill="both", expand=True, padx=14, pady=14)
        self._show_empty()

        self.save_location = SaveLocation(self, self.app)
        self.save_location.pack(fill="x", pady=(0, 18))

        self.download_btn = ctk.CTkButton(
            self,
            text="İndir",
            command=self._on_download,
            height=50,
            corner_radius=12,
            state="disabled",
            fg_color=SURFACE_3,
            hover_color=ACCENT_HOVER,
            text_color=TEXT,
            text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.download_btn.pack(fill="x")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_busy(self):
        return self._is_downloading

    def shutdown(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
        return super().shutdown()

    def _go_home(self):
        if self.is_busy():
            return
        self.app.show_screen("home")

    # ------------------------------------------------------------------
    # Preview area states
    # ------------------------------------------------------------------

    def _replace_preview(self):
        for child in self.preview_content.winfo_children():
            child.destroy()
        self.instagram_preview_images = []

    def _show_empty(self):
        self._replace_preview()
        empty = ctk.CTkFrame(self.preview_content, fg_color="transparent")
        empty.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            empty,
            text="🎬",
            font=(FONT_FAMILY, 34),
            text_color=TEXT_FAINT,
        ).pack()
        ctk.CTkLabel(
            empty,
            text="Instagram önizlemesi burada görünecek",
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
        ).pack(pady=(8, 0))

    def _show_loading(self):
        self._replace_preview()
        loading = ctk.CTkFrame(self.preview_content, fg_color="transparent")
        loading.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            loading,
            text="Yükleniyor...",
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack()

    def _set_status(self, text, color=TEXT_MUTED):
        self.status_label.configure(text=text, text_color=color)

    def _update_clear_button(self):
        self.input_row.set_clear_visible(bool(self.entry.get().strip()))

    # ------------------------------------------------------------------
    # Input handling / resolving
    # ------------------------------------------------------------------

    def _clear_input(self):
        self.debounce_job = self.cancel_job(self.debounce_job)
        self.request_id += 1
        self.entry.delete(0, "end")
        self._last_value = ""
        self.entry.focus_set()
        self.instagram_mode = None
        self.instagram_profile = None
        self.instagram_profile_avatar = None
        self.instagram_media = []
        self.instagram_category_vars = {}
        self._set_status("")
        self.download_btn.configure(
            state="disabled",
            fg_color=SURFACE_3,
            text="İndir",
        )
        self._show_empty()
        self._update_clear_button()

    def _on_input_changed(self):
        self._update_clear_button()
        value = self.entry.get().strip()
        # Key releases that don't edit the text (arrows, Ctrl+C, ...) change nothing.
        if value == self._last_value:
            return
        self._last_value = value
        self.debounce_job = self.cancel_job(self.debounce_job)

        if not value:
            self._clear_input()
            return

        self.request_id += 1
        rid = self.request_id
        self._set_status("")
        self.download_btn.configure(state="disabled", fg_color=SURFACE_3)
        self._show_loading()
        self.debounce_job = self.schedule(RESOLVE_DEBOUNCE_MS, self._start_resolve, value, rid)

    def _start_resolve(self, value, rid):
        self.debounce_job = None
        self.start_worker(self._resolve_worker, value, rid)

    def _resolve_worker(self, value, rid):
        # Worker thread: network + PIL work only, results go through post().
        try:
            preview = instagram.resolve(value, self.profile_cache)
            if isinstance(preview, instagram.PostPreview):
                if len(preview.media) == 1:
                    size, radius = SINGLE_PREVIEW_SIZE, 10
                else:
                    size, radius = TILE_PREVIEW_SIZE, 8
                images = [
                    make_rounded(img, size, radius=radius) if img is not None else None
                    for img in preview.thumbnails
                ]
                self.post("post_ok", rid, preview, images)
            else:
                avatar = None
                if preview.avatar is not None:
                    avatar = make_rounded(preview.avatar, AVATAR_SIZE, radius=36)
                self.post("profile_ok", rid, preview, avatar)
        except Exception as exc:
            log.warning("Instagram resolve failed for %r", value, exc_info=True)
            self.post("resolve_err", rid, instagram_friendly_error(exc))

    def on_post_ok(self, rid, preview, images):
        if rid == self.request_id:
            self._apply_post(preview.post, preview.media, images)

    def on_profile_ok(self, rid, preview, avatar):
        if rid == self.request_id:
            self._apply_profile(preview.profile, avatar)

    def on_resolve_err(self, rid, err):
        if rid == self.request_id:
            self.instagram_mode = None
            self._show_empty()
            self._set_status(err, ERROR)
            self.download_btn.configure(state="disabled", fg_color=SURFACE_3)

    def _apply_post(self, post, media, images):
        self.instagram_mode = "post"
        self.instagram_post = post
        self.instagram_profile = None
        self.instagram_media = media
        self.instagram_media_vars = []
        self._replace_preview()

        media_type = "Carousel" if len(media) > 1 else ("Video" if media[0]["is_video"] else "Fotoğraf")
        ctk.CTkLabel(
            self.preview_content,
            text=f"@{post.owner_username}  •  {media_type}",
            text_color=TEXT,
            font=(FONT_FAMILY, 14, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        if len(media) == 1:
            image = images[0]
            if image is not None:
                preview_image = ctk.CTkImage(image, size=SINGLE_PREVIEW_SIZE)
                self.instagram_preview_images.append(preview_image)
                ctk.CTkLabel(self.preview_content, text="", image=preview_image).pack()
            else:
                ctk.CTkLabel(
                    self.preview_content,
                    text="Önizleme yüklenemedi",
                    text_color=TEXT_FAINT,
                    font=(FONT_FAMILY, 13),
                ).pack(expand=True)
            self.instagram_media_vars = [ctk.BooleanVar(value=True)]
        else:
            toolbar = ctk.CTkFrame(self.preview_content, fg_color="transparent")
            toolbar.pack(fill="x", pady=(0, 8))
            self.select_all_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                toolbar,
                text=f"Tümünü seç ({len(media)})",
                variable=self.select_all_var,
                command=self._toggle_all_media,
                width=20,
                checkbox_width=19,
                checkbox_height=19,
                corner_radius=5,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=BORDER,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 12),
            ).pack(side="left")

            strip = ctk.CTkScrollableFrame(
                self.preview_content,
                orientation="horizontal",
                fg_color="transparent",
                height=225,
            )
            strip.pack(fill="both", expand=True)

            for index, (item, image) in enumerate(zip(media, images, strict=True), start=1):
                tile = ctk.CTkFrame(
                    strip,
                    fg_color=HOME_CARD,
                    corner_radius=10,
                    border_width=1,
                    border_color=BORDER,
                    width=120,
                    height=185,
                )
                tile.pack(side="left", padx=(0, 10))
                tile.pack_propagate(False)

                if image is not None:
                    thumb_image = ctk.CTkImage(image, size=TILE_PREVIEW_SIZE)
                    self.instagram_preview_images.append(thumb_image)
                    ctk.CTkLabel(tile, text="", image=thumb_image).pack(pady=(8, 4))
                else:
                    ctk.CTkLabel(
                        tile,
                        text="Önizleme yok",
                        text_color=TEXT_FAINT,
                        font=(FONT_FAMILY, 11),
                        width=TILE_PREVIEW_SIZE[0],
                        height=TILE_PREVIEW_SIZE[1],
                    ).pack(pady=(8, 4))

                var = ctk.BooleanVar(value=True)
                self.instagram_media_vars.append(var)
                ctk.CTkCheckBox(
                    tile,
                    text=f"{index}. {'Video' if item['is_video'] else 'Fotoğraf'}",
                    variable=var,
                    command=self._update_download_state,
                    checkbox_width=18,
                    checkbox_height=18,
                    corner_radius=5,
                    fg_color=ACCENT,
                    hover_color=ACCENT_HOVER,
                    border_color=BORDER,
                    text_color=TEXT_MUTED,
                    font=(FONT_FAMILY, 11),
                ).pack(padx=8, pady=(2, 8))

        self._set_status("")
        self._update_download_state()

    def _toggle_all_media(self):
        selected = bool(self.select_all_var.get())
        for var in self.instagram_media_vars:
            var.set(selected)
        self._update_download_state()

    def _has_browser_session(self):
        return bool(self.app.settings.instagram_browser)

    def _apply_profile(self, profile, avatar):
        self.instagram_mode = "profile"
        self.instagram_profile = profile
        self.instagram_profile_avatar = avatar
        self.instagram_post = None
        self.instagram_media = []
        self.instagram_category_vars = {}
        self._replace_preview()

        header = ctk.CTkFrame(self.preview_content, fg_color="transparent")
        header.pack(fill="x", pady=(2, 16))
        if avatar is not None:
            avatar_image = ctk.CTkImage(avatar, size=AVATAR_SIZE)
            self.instagram_preview_images.append(avatar_image)
            ctk.CTkLabel(header, text="", image=avatar_image).pack(side="left", padx=(0, 14))

        text_col = ctk.CTkFrame(header, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            text_col,
            text=f"@{profile.username}",
            text_color=TEXT,
            font=(FONT_FAMILY, 16, "bold"),
            anchor="w",
        ).pack(fill="x")
        if profile.full_name:
            ctk.CTkLabel(
                text_col,
                text=profile.full_name,
                text_color=TEXT_MUTED,
                font=(FONT_FAMILY, 12),
                anchor="w",
            ).pack(fill="x", pady=(3, 0))

        # Private + not (verifiably) followed: try nothing at all, not even the profile picture.
        if profile.is_private:
            self._set_status(
                "Bu hesap gizli. Bu hesabı takip etmiyorsanız hiçbir içerik indirilemez.", TEXT_MUTED
            )
            self._update_download_state()
            return

        # Scrollable: categories + the session-consent box together can run past the card's
        # fixed height, and this content (unlike the carousel strip) doesn't fit a fixed size.
        scroll = ctk.CTkScrollableFrame(self.preview_content, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll,
            text="İNDİRİLEBİLİR KATEGORİLER",
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        has_session = self._has_browser_session()
        for key, label in PROFILE_CATEGORIES:
            needs_session = key != instagram.CATEGORY_PROFILE_PIC
            enabled = has_session or not needs_session
            var = ctk.BooleanVar(value=False)
            self.instagram_category_vars[key] = var
            ctk.CTkCheckBox(
                scroll,
                text=label,
                variable=var,
                command=self._update_download_state,
                state="normal" if enabled else "disabled",
                height=38,
                corner_radius=6,
                checkbox_width=20,
                checkbox_height=20,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=BORDER,
                text_color=TEXT,
                text_color_disabled=TEXT_FAINT,
                font=(FONT_FAMILY, 13, "bold"),
            ).pack(fill="x", pady=(0, 6))

        if has_session:
            self._set_status("")
        else:
            self._build_session_consent(scroll)
            self._set_status("Gönderiler/Reels için tarayıcı oturumu gerekiyor.", TEXT_MUTED)
        self._update_download_state()

    def _build_session_consent(self, parent):
        box = ctk.CTkFrame(
            parent, fg_color=SURFACE_2, corner_radius=10, border_width=1, border_color=BORDER,
        )
        box.pack(fill="x", pady=(4, 0))
        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            inner,
            text="Toplu gönderi/Reels indirme için isteğe bağlı olarak tarayıcı oturumunuzu "
                 "kullanabiliriz. Seçilen tarayıcıdaki Instagram oturumu yalnızca bu indirme için "
                 "okunur; çerezleriniz diske yazılmaz veya günlüğe kaydedilmez.",
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 11),
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(fill="x", pady=(0, 10))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self.browser_menu = ThemedDropdown(
            row,
            values=list(BROWSER_LABELS.values()),
            variable=self.browser_choice_var,
            height=38,
            corner_radius=8,
            font=(FONT_FAMILY, 12, "bold"),
        )
        self.browser_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row,
            text="Onayla ve etkinleştir",
            command=self._enable_browser_session,
            height=38,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT,
            font=(FONT_FAMILY, 12, "bold"),
        ).pack(side="left")

    def _enable_browser_session(self):
        browser = BROWSER_BY_LABEL.get(self.browser_choice_var.get())
        if not browser:
            return
        self.app.settings.instagram_browser = browser
        save_settings(self.app.settings)
        if self.instagram_mode == "profile" and self.instagram_profile is not None:
            self._apply_profile(self.instagram_profile, self.instagram_profile_avatar)

    def _update_download_state(self):
        enabled = False
        if self.instagram_mode == "post":
            enabled = any(var.get() for var in self.instagram_media_vars)
        elif self.instagram_mode == "profile":
            enabled = any(var.get() for var in self.instagram_category_vars.values())

        self.download_btn.configure(
            state="normal" if enabled else "disabled",
            fg_color=ACCENT if enabled else SURFACE_3,
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _on_download(self):
        if self._is_downloading:
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.download_btn.configure(
                state="disabled",
                fg_color=SURFACE_3,
                text="İptal ediliyor...",
            )
            return

        if self.instagram_mode == "post":
            selected_media = [
                item
                for item, var in zip(self.instagram_media, self.instagram_media_vars, strict=False)
                if var.get()
            ]
            if not selected_media:
                return
            job = ("post", self.instagram_post, selected_media, None)
        elif self.instagram_mode == "profile":
            categories = [key for key, var in self.instagram_category_vars.items() if var.get()]
            if not categories:
                return
            job = ("profile", self.instagram_profile, categories, self.app.settings.instagram_browser or None)
        else:
            return

        self._is_downloading = True
        self.cancel_event = threading.Event()
        self.input_row.set_locked(True)
        self.save_location.set_enabled(False)
        self.download_btn.configure(
            state="normal",
            fg_color=SURFACE_2,
            hover_color=SURFACE_3,
            text="İptal Et",
        )
        self._set_status("İndirme başlatılıyor...", TEXT_MUTED)

        self.start_worker(self._download_worker, job, self.app.download_dir, self.cancel_event, track=True)

    def _download_worker(self, job, download_dir, cancel_event):
        mode, target, selection, browser = job

        def on_progress(stage, index, total):
            self.post("progress", progress_text(stage, index, total))

        try:
            if mode == "post":
                downloaded = instagram.download_post(target, selection, download_dir, cancel_event, on_progress)
            else:
                downloaded = instagram.download_profile(target, selection, download_dir, cancel_event,
                                                        on_progress, browser=browser)
            log.info("Instagram %s download finished: %d file(s)", mode, downloaded)
            self.post("download_done", downloaded)
        except DownloadCancelled:
            self.post("download_cancelled")
        except Exception as exc:
            log.exception("Instagram %s download failed", mode)
            self.post("download_err", instagram_friendly_error(exc))

    def on_progress(self, text):
        self._set_status(text, TEXT_MUTED)

    def on_download_done(self, _downloaded):
        self._is_downloading = False
        self.cancel_event = None
        self._set_status("")
        self.download_btn.configure(
            state="disabled",
            text="Tamamlandı",
            fg_color=SUCCESS,
        )
        self.schedule(FINISH_DELAY_MS, self._finish_download_ui)

    def on_download_cancelled(self):
        self._set_status("İndirme iptal edildi", TEXT_MUTED)
        self._restore_inputs()

    def on_download_err(self, err):
        self._set_status(err, ERROR)
        self._restore_inputs()

    def _restore_inputs(self):
        self._is_downloading = False
        self.cancel_event = None
        self.input_row.set_locked(False)
        self.save_location.set_enabled(True)
        self.download_btn.configure(text="İndir")
        self.download_btn.configure(hover_color=ACCENT_HOVER)
        self._update_download_state()

    def _finish_download_ui(self):
        self._restore_inputs()
        self._clear_input()
