"""Settings screen: download preferences, the yt-dlp engine (update / restart) and about."""

import logging
import os
import threading
import time

import customtkinter as ctk
from PIL import Image

from arnold_dw import APP_NAME, __version__, paths
from arnold_dw.config import save_settings
from arnold_dw.core.runtime import autocheck, binaries, restart, selectors, ytdlp_updater
from arnold_dw.core.text import fmt_bytes
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BG,
    BORDER,
    ERROR,
    FONT_FAMILY,
    SUCCESS,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)
from arnold_dw.ui.widgets.dropdown import ThemedDropdown
from arnold_dw.ui.widgets.inputs import SaveLocation

log = logging.getLogger(__name__)

VIDEO_MODE_LABELS = {
    "compat": "Maksimum uyumluluk (H.264)",
    "quality": "En yüksek kalite",
}
VIDEO_MODE_HINTS = {
    "compat": "Her oynatıcıda ve telefonda sesli, görüntülü açılır (H.264 + AAC). "
              "YouTube bu biçimi en fazla 1080p sunar.",
    "quality": "Kaynağın en iyi akışları, 4K'ya kadar (VP9/AV1). "
               "Bazı eski oynatıcılar bu dosyaları açamayabilir.",
}
CHANNEL_LABELS = {
    "stable": "Kararlı",
    "nightly": "Nightly (erken düzeltmeler)",
}
CHANNEL_HINT = ("Nightly sürümler YouTube düzeltmelerini birkaç gün önce getirir; "
                "sorun çıkarsa uygulama önceki motora döner.")

PROGRESS_POST_INTERVAL = 0.1  # seconds between install progress messages
WRAP = 330  # px, wrap length of explanatory text inside a card


# ----------------------------------------------------------------------
# Pure helpers (unit tested)
# ----------------------------------------------------------------------

def label_to_key(labels, label, default):
    for key, text in labels.items():
        if text == label:
            return key
    return default


def cover_status(has_ffmpeg, has_ffprobe):
    """(tagging switches enabled, cover note or None) for this machine's ffmpeg setup."""
    if not has_ffmpeg:
        return False, "ffmpeg bulunamadı; bilgi ve kapak gömülemez."
    if not selectors.cover_supported("mp4", has_ffprobe):
        if selectors.cover_supported("mp3", has_ffprobe):
            return True, "MP4'e kapak eklemek için ffprobe gerekli; kapak yalnızca MP3 dosyalarına eklenir."
        return True, "Kapak görseli bu sistemde eklenemiyor."
    return True, None


def engine_summary(version, source):
    origin = "güncellenmiş sürüm" if source == "engine" else "uygulamayla gelen sürüm"
    return f"yt-dlp {version or 'bilinmiyor'} · {origin}"


def tool_line(name, version, found, missing_note=""):
    if not found:
        return f"{name}: bulunamadı{(' — ' + missing_note) if missing_note else ''}", False
    return f"{name}: {version or 'bulundu'}", True


def install_progress_text(done, total):
    if total:
        return f"İndiriliyor… {fmt_bytes(done)} / {fmt_bytes(total)}"
    return f"İndiriliyor… {fmt_bytes(done)}"


# ----------------------------------------------------------------------
# Screen
# ----------------------------------------------------------------------

class SettingsScreen(Screen):
    name = "settings"

    def __init__(self, app):
        super().__init__(app)
        self._engine_state = "idle"
        self._update_info = None
        self._install_cancel = None
        self._last_progress_post = 0.0

    # --- construction -------------------------------------------------

    def build(self):
        self._build_header()
        self.body = ctk.CTkScrollableFrame(
            self, fg_color=BG, corner_radius=0,
            scrollbar_button_color=SURFACE_3, scrollbar_button_hover_color=BORDER,
        )
        self.body.pack(fill="both", expand=True)
        self._build_download_section()
        self._build_engine_section()
        self._build_about_section()
        self._restore_engine_state()
        self.start_worker(self._probe_tools)

    def _build_header(self):
        row = ctk.CTkFrame(self, fg_color="transparent", height=46)
        row.pack(fill="x", pady=(0, 14))
        row.pack_propagate(False)
        back_icon = Image.open(paths.BACK_ICON_PATH).convert("RGBA")
        self.back_icon_image = ctk.CTkImage(light_image=back_icon, dark_image=back_icon, size=(22, 22))
        self.back_btn = ctk.CTkButton(
            row, text="", image=self.back_icon_image, command=self._go_home,
            width=46, height=46, corner_radius=10, border_width=1, border_color=BORDER,
            fg_color=SURFACE, hover_color=SURFACE_2,
        )
        self.back_btn.pack(side="left", padx=(0, 14))
        ctk.CTkLabel(
            row, text="Ayarlar", text_color=TEXT, font=(FONT_FAMILY, 20, "bold"), anchor="w",
        ).pack(side="left")

    def _section(self, title):
        ctk.CTkLabel(
            self.body, text=title, text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=(8, 0), pady=(4, 6))
        card = ctk.CTkFrame(self.body, fg_color=SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, 18), padx=(0, 6))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        return inner

    def _field_title(self, parent, text, top=0):
        # Same look as SaveLocation's "KAYIT KONUMU" title.
        ctk.CTkLabel(
            parent, text=text, text_color=TEXT_FAINT, font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=(8, 0), pady=(top, 6))

    def _note(self, parent, text="", color=TEXT_FAINT, top=6):
        label = ctk.CTkLabel(
            parent, text=text, text_color=color, font=(FONT_FAMILY, 11),
            anchor="w", justify="left", wraplength=WRAP,
        )
        label.pack(fill="x", pady=(top, 0))
        return label

    def _switch(self, parent, text, value, command, top=14):
        var = ctk.BooleanVar(value=value)
        switch = ctk.CTkSwitch(
            parent, text=text, variable=var, command=command,
            progress_color=ACCENT, button_color=TEXT, button_hover_color=TEXT_MUTED,
            fg_color=SURFACE_3, text_color=TEXT, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
        )
        switch.pack(fill="x", pady=(top, 0))
        return var, switch

    def _build_download_section(self):
        s = self.app.settings
        box = self._section("İNDİRME")

        self.save_location = SaveLocation(box, self.app)
        self.save_location.pack(fill="x")

        self._field_title(box, "VİDEO MODU", top=16)
        self.video_mode_var = ctk.StringVar(value=VIDEO_MODE_LABELS[s.video_mode])
        self.video_mode_menu = ThemedDropdown(
            box, values=list(VIDEO_MODE_LABELS.values()), variable=self.video_mode_var,
            command=self._on_video_mode, height=40, corner_radius=10, font=(FONT_FAMILY, 13, "bold"),
            border_width=1, border_color=BORDER,
        )
        self.video_mode_menu.pack(fill="x")
        self.video_mode_hint = self._note(box, VIDEO_MODE_HINTS[s.video_mode])

        enabled, cover_note = cover_status(binaries.ffmpeg_path() is not None,
                                           binaries.ffprobe_path() is not None)
        state = "normal" if enabled else "disabled"
        self.metadata_var, self.metadata_switch = self._switch(
            box, "Bilgileri göm (başlık, sanatçı, bölümler)", s.embed_metadata and enabled,
            self._on_embed_metadata, top=16)
        self.thumbnail_var, self.thumbnail_switch = self._switch(
            box, "Kapak görselini göm", s.embed_thumbnail and enabled, self._on_embed_thumbnail)
        self.metadata_switch.configure(state=state)
        self.thumbnail_switch.configure(state=state)
        if cover_note:
            self._note(box, cover_note)

    def _build_engine_section(self):
        s = self.app.settings
        box = self._section("İNDİRME MOTORU")

        self.engine_label = ctk.CTkLabel(
            box, text=engine_summary(ytdlp_updater.current_version(), ytdlp_updater.engine_source()),
            text_color=TEXT, font=(FONT_FAMILY, 14, "bold"), anchor="w",
        )
        self.engine_label.pack(fill="x")
        self.engine_status = self._note(box, "", color=TEXT_MUTED)

        self.engine_progress = ctk.CTkProgressBar(
            box, height=8, corner_radius=6, fg_color=SURFACE_2, progress_color=ACCENT,
        )
        self.engine_progress.set(0)

        self.engine_actions = ctk.CTkFrame(box, fg_color="transparent")
        self.engine_actions.pack(fill="x", pady=(10, 0))
        self.engine_primary = ctk.CTkButton(
            self.engine_actions, text="", height=38, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            text_color_disabled=TEXT_FAINT, font=(FONT_FAMILY, 13, "bold"),
        )
        self.engine_primary.pack(side="left", fill="x", expand=True)
        self.engine_secondary = ctk.CTkButton(
            self.engine_actions, text="", width=96, height=38, corner_radius=10,
            fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
            font=(FONT_FAMILY, 13, "bold"),
        )

        self._field_title(box, "GÜNCELLEME KANALI", top=16)
        self.channel_var = ctk.StringVar(value=CHANNEL_LABELS[s.engine_channel])
        self.channel_menu = ThemedDropdown(
            box, values=list(CHANNEL_LABELS.values()), variable=self.channel_var,
            command=self._on_channel, height=40, corner_radius=10, font=(FONT_FAMILY, 13, "bold"),
            border_width=1, border_color=BORDER,
        )
        self.channel_menu.pack(fill="x")
        self._note(box, CHANNEL_HINT)

        self.auto_check_var, self.auto_check_switch = self._switch(
            box, "Günde bir kez güncellemeleri denetle", s.engine_auto_check, self._on_auto_check, top=16)
        self._note(box, "Yeni sürüm bulunursa ana ekranda haber verilir; kurulum her zaman onayınızla yapılır.")

        self._field_title(box, "YARDIMCI ARAÇLAR", top=16)
        self.tool_labels = {}
        for key in ("js", "ffmpeg", "ffprobe"):
            label = ctk.CTkLabel(box, text="Denetleniyor…", text_color=TEXT_FAINT,
                                 font=(FONT_FAMILY, 12), anchor="w", justify="left", wraplength=WRAP)
            label.pack(fill="x")
            self.tool_labels[key] = label

    def _build_about_section(self):
        box = self._section("HAKKINDA")
        ctk.CTkLabel(
            box, text=f"{APP_NAME} {__version__}", text_color=TEXT,
            font=(FONT_FAMILY, 14, "bold"), anchor="w",
        ).pack(fill="x")
        ctk.CTkButton(
            box, text="Log klasörünü aç", height=38, corner_radius=10,
            fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
            font=(FONT_FAMILY, 13, "bold"), command=self._open_log_dir,
        ).pack(fill="x", pady=(10, 0))
        self.about_status = self._note(box, "", color=ERROR)
        self.about_status.pack_forget()

    # --- download preferences -------------------------------------------

    def _save(self):
        if not save_settings(self.app.settings):
            log.warning("settings could not be saved")

    def _on_video_mode(self, label):
        mode = label_to_key(VIDEO_MODE_LABELS, label, "compat")
        self.app.settings.video_mode = mode
        self.video_mode_hint.configure(text=VIDEO_MODE_HINTS[mode])
        self._save()

    def _on_embed_metadata(self):
        self.app.settings.embed_metadata = bool(self.metadata_var.get())
        self._save()

    def _on_embed_thumbnail(self):
        self.app.settings.embed_thumbnail = bool(self.thumbnail_var.get())
        self._save()

    def _on_channel(self, label):
        channel = label_to_key(CHANNEL_LABELS, label, "stable")
        if channel == self.app.settings.engine_channel:
            return
        self.app.settings.engine_channel = channel
        self._save()
        # An update found on the other channel no longer applies.
        autocheck.notifier.clear()
        if self._engine_state in ("available", "idle", "error"):
            self._update_info = None
            self._set_engine_state("idle")

    def _on_auto_check(self):
        self.app.settings.engine_auto_check = bool(self.auto_check_var.get())
        self._save()

    # --- tools ----------------------------------------------------------

    def _probe_tools(self):
        # Runs `--version` of each tool: seconds on a cold start, so off the UI thread.
        runtime = binaries.find_js_runtime()
        ffmpeg = binaries.ffmpeg_path()
        lines = {
            "js": tool_line(
                "JavaScript çalışma zamanı",
                runtime and f"{runtime.name} {runtime.version}", runtime is not None,
                "YouTube bazı kaliteleri sunmayabilir"),
            "ffmpeg": tool_line("ffmpeg", ffmpeg and binaries.ffmpeg_version(ffmpeg), ffmpeg is not None,
                                "birleştirme ve MP3 dönüştürme çalışmaz"),
            "ffprobe": tool_line("ffprobe", None, binaries.ffprobe_path() is not None,
                                 "MP4'e kapak eklenemez"),
        }
        self.post("tools", lines)

    def on_tools(self, lines):
        for key, (text, ok) in lines.items():
            self.tool_labels[key].configure(text=("✓  " if ok else "✕  ") + text,
                                            text_color=TEXT_MUTED if ok else ERROR)

    # --- engine update ----------------------------------------------------

    def _restore_engine_state(self):
        if ytdlp_updater.restart_required():
            self._set_engine_state("installed", version=ytdlp_updater.installed_version())
        elif autocheck.notifier.result is not None:
            self._update_info = autocheck.notifier.result
            self._set_engine_state("available")
        else:
            self._set_engine_state("idle")

    def _set_buttons(self, primary, primary_cmd, secondary=None, secondary_cmd=None,
                     primary_enabled=True, accent=True):
        self.engine_primary.configure(
            text=primary, command=primary_cmd, state="normal" if primary_enabled else "disabled",
            fg_color=ACCENT if accent and primary_enabled else SURFACE_2,
            hover_color=ACCENT_HOVER if accent else SURFACE_3,
        )
        if secondary:
            self.engine_secondary.configure(text=secondary, command=secondary_cmd)
            if not self.engine_secondary.winfo_ismapped():
                self.engine_secondary.pack(side="left", padx=(8, 0))
        else:
            self.engine_secondary.pack_forget()

    def _set_status(self, text, color=TEXT_MUTED):
        self.engine_status.configure(text=text, text_color=color)
        if text:
            self.engine_status.pack(fill="x", pady=(6, 0), after=self.engine_label)
        else:
            self.engine_status.pack_forget()

    def _set_engine_state(self, state, **kw):
        self._engine_state = state
        installing = state == "installing"
        if installing:
            if not self.engine_progress.winfo_ismapped():
                self.engine_progress.pack(fill="x", pady=(10, 0), before=self.engine_actions)
        else:
            self.engine_progress.pack_forget()
        self.back_btn.configure(state="disabled" if installing else "normal")
        self.channel_menu.configure(state="disabled" if installing else "normal")

        if state == "idle":
            self._set_status(kw.get("message", ""), kw.get("color", TEXT_MUTED))
            self._set_buttons("Güncellemeleri denetle", self._check_updates, accent=False)
        elif state == "checking":
            self._set_status("PyPI'de yeni sürüm aranıyor…")
            self._set_buttons("Denetleniyor…", None, primary_enabled=False)
        elif state == "available":
            info = self._update_info
            self._set_status(f"Yeni sürüm var: yt-dlp {info.version} ({fmt_bytes(info.total_size)}). "
                             "İndirilip kurulsun mu?", TEXT)
            self._set_buttons("İndir ve kur", self._install_update, "Vazgeç", self._dismiss_update)
        elif state == "installing":
            self.engine_progress.set(0)
            self._set_status("İndirme başlıyor…")
            self._set_buttons("İptal", self._cancel_install, accent=False)
        elif state == "installed":
            self._set_status(f"yt-dlp {kw.get('version') or ''} kuruldu. Yeniden başlatınca etkin olacak.",
                             SUCCESS)
            self._set_buttons("Şimdi yeniden başlat", self._restart_now)
        elif state == "confirm_restart":
            self._set_status("Devam eden indirmeler var; yeniden başlatmak onları iptal eder.", ERROR)
            self._set_buttons("Yine de yeniden başlat", self._do_restart, "Vazgeç",
                              lambda: self._set_engine_state("installed", version=kw.get("version")))
        elif state == "error":
            self._set_status(kw.get("message", "Bir hata oluştu."), ERROR)
            self._set_buttons("Tekrar dene", self._check_updates, accent=False)

    def _check_updates(self):
        self._set_engine_state("checking")
        self.start_worker(self._check_worker, self.app.settings.engine_channel)

    def _check_worker(self, channel):
        try:
            info = ytdlp_updater.check_for_update(channel, raise_errors=True)
        except ytdlp_updater.UpdateError as exc:
            self.post("engine_error", exc.user_message)
            return
        except Exception:
            log.exception("engine update check failed")
            self.post("engine_error", "Güncellemeler denetlenemedi.")
            return
        self.post("engine_checked", info)

    def on_engine_checked(self, info):
        self.app.settings.last_engine_check = time.time()
        self._save()
        autocheck.notifier.result = info
        self._update_info = info
        if info is None:
            self._set_engine_state("idle", message="Motor güncel.", color=SUCCESS)
        else:
            self._set_engine_state("available")

    def on_engine_error(self, message):
        self._set_engine_state("error", message=message)

    def _dismiss_update(self):
        self._set_engine_state("idle")

    def _install_update(self):
        info = self._update_info
        if info is None:
            return
        self._install_cancel = threading.Event()
        self._set_engine_state("installing")
        self.start_worker(self._install_worker, info, self._install_cancel, track=True)

    def _install_worker(self, info, cancel_event):
        def progress(done, total):
            now = time.monotonic()
            if done >= total or now - self._last_progress_post >= PROGRESS_POST_INTERVAL:
                self._last_progress_post = now
                self.post("engine_progress", done, total)

        try:
            version = ytdlp_updater.download_and_install(info, progress, cancel_event)
        except ytdlp_updater.UpdateCancelled:
            self.post("engine_install_cancelled")
        except ytdlp_updater.UpdateError as exc:
            log.warning("engine install failed: %s", exc)
            self.post("engine_error", exc.user_message)
        except Exception:
            log.exception("engine install failed")
            self.post("engine_error", "Motor güncellemesi başarısız oldu.")
        else:
            self.post("engine_installed", version)

    def on_engine_progress(self, done, total):
        if self._engine_state != "installing":
            return
        self.engine_progress.set(min(done / total, 1.0) if total else 0)
        self._set_status(install_progress_text(done, total))

    def _cancel_install(self):
        if self._install_cancel is not None:
            self._install_cancel.set()
        self.engine_primary.configure(state="disabled", text="İptal ediliyor…")

    def on_engine_install_cancelled(self):
        self._install_cancel = None
        self._set_engine_state("available")
        self._set_status("Güncelleme iptal edildi. Motor değişmedi.")

    def on_engine_installed(self, version):
        self._install_cancel = None
        autocheck.notifier.clear()
        self._set_engine_state("installed", version=version)

    def _has_active_downloads(self):
        # The download manager (queue screen) exposes this; screens that lock
        # navigation while downloading never leave a download running here.
        check = getattr(self.app, "has_active_downloads", None)
        try:
            return bool(check()) if callable(check) else False
        except Exception:
            log.exception("has_active_downloads failed")
            return False

    def _restart_now(self):
        if self._has_active_downloads():
            self._set_engine_state("confirm_restart", version=ytdlp_updater.installed_version())
            return
        self._do_restart()

    def _do_restart(self):
        log.info("restart requested from settings")
        restart.request()
        # The window's normal close path: stops running work, then main() relaunches.
        # Running downloads were already confirmed above, so don't ask again.
        self.app._on_close(force=True)

    # --- about --------------------------------------------------------------

    def _open_log_dir(self):
        directory = paths.log_dir()
        try:
            os.makedirs(directory, exist_ok=True)
            os.startfile(directory)
        except OSError:
            log.exception("could not open log dir %s", directory)
            self.about_status.configure(text="Log klasörü açılamadı.")
            self.about_status.pack(fill="x", pady=(6, 0))

    # --- lifecycle ------------------------------------------------------------

    def _go_home(self):
        if self.is_busy():
            return
        self.app.show_screen("home")

    def is_busy(self):
        return self._engine_state == "installing"

    def shutdown(self):
        if self._install_cancel is not None:
            self._install_cancel.set()
        return super().shutdown()
