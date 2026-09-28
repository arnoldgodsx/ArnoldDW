"""Instagram screen: post link (single/carousel) or username/profile link -> queue the download."""

import logging

import customtkinter as ctk

from arnold_dw.core import instagram, runners
from arnold_dw.core.errors import instagram_friendly_error
from arnold_dw.core.jobs import DownloadJob
from arnold_dw.ui.imaging import job_thumbnail, make_rounded
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
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)
from arnold_dw.ui.widgets.inputs import InputRow, SaveLocation
from arnold_dw.ui.widgets.jobviews import JobStrip

log = logging.getLogger(__name__)

RESOLVE_DEBOUNCE_MS = 1200

SINGLE_PREVIEW_SIZE = (300, 230)
TILE_PREVIEW_SIZE = (104, 120)
AVATAR_SIZE = (72, 72)

PROFILE_CATEGORIES = (
    (instagram.CATEGORY_POSTS, "Gönderiler / Fotoğraflar"),
    (instagram.CATEGORY_REELS, "Reels / Videolar"),
    (instagram.CATEGORY_PROFILE_PIC, "Profil Fotoğrafı"),
)


class InstagramScreen(Screen):
    name = "instagram"
    tab = "home"

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
        self.instagram_media = []
        self.instagram_media_vars = []
        self.instagram_category_vars = {}
        self.instagram_preview_images = []
        self._preview = None     # the resolved PostPreview / ProfilePreview (reused by the job)
        self._job_thumb = None   # small PIL cover handed to the queued job

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
            height=330,
        )
        self.preview_card.pack(fill="x", pady=(0, 14))
        self.preview_card.pack_propagate(False)

        self.preview_content = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        self.preview_content.pack(fill="both", expand=True, padx=14, pady=14)
        self._show_empty()

        self.save_location = SaveLocation(self, self.app)
        self.save_location.pack(fill="x", pady=(0, 12))

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
        self.download_btn.pack(fill="x", pady=(0, 12))

        self.strip = JobStrip(self, self.app)
        self.strip.refresh()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_job_event(self, kind, payload):
        self.strip.refresh()

    def _go_home(self):
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
        self.instagram_media = []
        self.instagram_category_vars = {}
        self._preview = None
        self._job_thumb = None
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
                cover = next((img for img in preview.thumbnails if img is not None), None)
                job_thumb = job_thumbnail(cover) if cover is not None else None
                self.post("post_ok", rid, preview, images, job_thumb)
            else:
                avatar = None
                if preview.avatar is not None:
                    avatar = make_rounded(preview.avatar, AVATAR_SIZE, radius=36)
                job_thumb = job_thumbnail(preview.avatar) if preview.avatar is not None else None
                self.post("profile_ok", rid, preview, avatar, job_thumb)
        except Exception as exc:
            log.warning("Instagram resolve failed for %r", value, exc_info=True)
            self.post("resolve_err", rid, instagram_friendly_error(exc))

    def on_post_ok(self, rid, preview, images, job_thumb):
        if rid == self.request_id:
            self._preview, self._job_thumb = preview, job_thumb
            self._apply_post(preview.post, preview.media, images)

    def on_profile_ok(self, rid, preview, avatar, job_thumb):
        if rid == self.request_id:
            self._preview, self._job_thumb = preview, job_thumb
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

    def _apply_profile(self, profile, avatar):
        self.instagram_mode = "profile"
        self.instagram_profile = profile
        self.instagram_post = None
        self.instagram_media = []
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

        ctk.CTkLabel(
            self.preview_content,
            text="İNDİRİLEBİLİR KATEGORİLER",
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self.instagram_category_vars = {}
        for key, label in PROFILE_CATEGORIES:
            var = ctk.BooleanVar(value=False)
            self.instagram_category_vars[key] = var
            private_only_pic = profile.is_private and key != instagram.CATEGORY_PROFILE_PIC
            ctk.CTkCheckBox(
                self.preview_content,
                text=label,
                variable=var,
                command=self._update_download_state,
                state="disabled" if private_only_pic else "normal",
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

        if profile.is_private:
            self._set_status("Gizli hesaplarda yalnızca profil fotoğrafı indirilebilir.", TEXT_MUTED)
        else:
            self._set_status("")
        self._update_download_state()

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
        if self.instagram_mode == "post":
            selected = [
                item
                for item, var in zip(self.instagram_media, self.instagram_media_vars, strict=False)
                if var.get()
            ]
            if not selected:
                return
            post = self.instagram_post
            options = runners.instagram_post_options(post.shortcode, [item["index"] for item in selected])
            url = instagram.post_url(post.shortcode)
            kind = "Carousel" if len(self.instagram_media) > 1 else (
                "Video" if self.instagram_media[0]["is_video"] else "Fotoğraf")
            title = f"@{post.owner_username} · {kind}"
        elif self.instagram_mode == "profile":
            categories = [key for key, var in self.instagram_category_vars.items() if var.get()]
            if not categories:
                return
            profile = self.instagram_profile
            options = runners.instagram_profile_options(profile.username, categories)
            url = instagram.profile_url(profile.username)
            title = f"@{profile.username} · Profil"
        else:
            return

        manager = self.app.downloads
        if manager.find_active(runners.PLATFORM_INSTAGRAM, url, options) is not None:
            self._set_status("Bu seçim zaten indiriliyor.", TEXT_MUTED)
            return
        manager.enqueue(DownloadJob(
            platform=runners.PLATFORM_INSTAGRAM, url=url, title=title, download_dir=self.app.download_dir,
            options=options, context=self._preview, thumbnail_image=self._job_thumb,
        ))
        log.info("Instagram download queued: %s %s", url, options)
        # Ready for the next link right away.
        self._clear_input()
        self._set_status("İndirmelere eklendi. Yeni bir bağlantı yapıştırabilirsiniz.", SUCCESS)
