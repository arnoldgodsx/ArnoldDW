"""First-launch setup screen: downloads the runtime components (ffmpeg, Deno) the installer leaves out."""

import logging
import threading
import time

import customtkinter as ctk
from PIL import Image

from arnold_dw import APP_NAME, paths
from arnold_dw.core.runtime import binaries, components
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    ERROR,
    FONT_FAMILY,
    HOME_CARD,
    SUCCESS,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)

log = logging.getLogger(__name__)

DONE_DELAY_MS = 900  # "Hazır" stays on screen this long before the home screen opens
SPEED_WINDOW = 3.0  # seconds of samples behind the speed readout
DOT_FRAMES = ("", ".", "..", "...")


def fmt_mb(count):
    return f"{count / 1_000_000:.1f} MB".replace(".", ",")


def progress_text(done, total, speed):
    """'12,3 / 31,0 MB · 4,2 MB/s' (total and speed optional)."""
    text = fmt_mb(done) if not total else f"{fmt_mb(done).removesuffix(' MB')} / {fmt_mb(total)}"
    if speed:
        text += f"  ·  {fmt_mb(speed)}/s"
    return text


class _ComponentRow(ctk.CTkFrame):
    def __init__(self, master, component):
        super().__init__(master, fg_color=HOME_CARD, corner_radius=12, border_width=1, border_color=BORDER)
        self.component = component
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(top, text=component.title, font=(FONT_FAMILY, 15, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left")
        self.state = ctk.CTkLabel(top, text="Sırada", font=(FONT_FAMILY, 12, "bold"),
                                  text_color=TEXT_FAINT, anchor="e")
        self.state.pack(side="right")
        ctk.CTkLabel(self, text=component.description, font=(FONT_FAMILY, 12),
                     text_color=TEXT_MUTED, anchor="w").pack(fill="x", padx=16, pady=(2, 8))
        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3, fg_color=SURFACE_3,
                                      progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=16)
        self.detail = ctk.CTkLabel(self, text=" ", font=(FONT_FAMILY, 11), text_color=TEXT_FAINT, anchor="w")
        self.detail.pack(fill="x", padx=16, pady=(4, 10))

    def set_state(self, state, detail=None):
        text, color = {
            "queued": ("Sırada", TEXT_FAINT),
            "downloading": ("İndiriliyor", ACCENT),
            "verifying": ("Doğrulanıyor", TEXT_MUTED),
            "done": ("Hazır  ✓", SUCCESS),
            "failed": ("Hata", ERROR),
        }[state]
        self.state.configure(text=text, text_color=color)
        if state == "verifying":
            self.bar.configure(mode="indeterminate")
            self.bar.start()
        else:
            self.bar.stop()
            self.bar.configure(mode="determinate")
        if state == "done":
            self.bar.configure(progress_color=SUCCESS)
            self.bar.set(1)
        elif state in ("queued", "failed"):
            self.bar.configure(progress_color=ACCENT)
            self.bar.set(0)
        if detail is not None:
            self.detail.configure(text=detail or " ", text_color=ERROR if state == "failed" else TEXT_FAINT)


class SetupScreen(Screen):
    """Shown instead of the home screen until every runtime component is installed."""

    name = "setup"

    def build(self):
        self._cancel = threading.Event()
        self._rows = {}
        self._samples = []
        self._dots = 0

        logo = Image.open(paths.APP_LOGO_PATH).convert("RGBA")
        self._logo = ctk.CTkImage(light_image=logo, dark_image=logo, size=(96, 96))
        ctk.CTkLabel(self, text="", image=self._logo).pack(pady=(26, 0))
        ctk.CTkLabel(self, text=APP_NAME, font=(FONT_FAMILY, 27, "bold"), text_color=TEXT).pack(pady=(8, 0))
        self.heading = ctk.CTkLabel(self, text="Hazırlanıyor", font=(FONT_FAMILY, 14, "bold"),
                                  text_color=ACCENT)
        self.heading.pack(pady=(2, 0))

        todo = components.missing()
        size = components.download_size_hint(todo)
        intro = ("İlk açılışa özel: video ve ses işlemleri için gereken bileşenler indiriliyor"
                 + (f" (yaklaşık {size // 1_000_000} MB)" if size else "")
                 + ". Bu işlem yalnızca bir kez yapılır.")
        ctk.CTkLabel(self, text=intro, font=(FONT_FAMILY, 13), text_color=TEXT_MUTED,
                     wraplength=400, justify="center").pack(pady=(14, 18))

        for component in todo:
            row = _ComponentRow(self, component)
            row.pack(fill="x", pady=(0, 12))
            self._rows[component.name] = row

        self.message = ctk.CTkLabel(self, text="", font=(FONT_FAMILY, 12), text_color=ERROR,
                                    wraplength=400, justify="center")
        self.message.pack(pady=(4, 0))
        self.retry_btn = ctk.CTkButton(
            self, text="Tekrar dene", height=40, corner_radius=10, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=TEXT, font=(FONT_FAMILY, 14, "bold"),
            command=self._start,
        )
        self.footer = ctk.CTkLabel(self, text="Kurulum klasörü: " + components.root_dir(),
                                   font=(FONT_FAMILY, 10), text_color=TEXT_FAINT, wraplength=420)
        self.footer.pack(side="bottom", pady=(0, 4))

        self._start()
        self._animate()

    # --- work -------------------------------------------------------------

    def _start(self):
        self.retry_btn.pack_forget()
        self.message.configure(text="")
        self.heading.configure(text="Hazırlanıyor", text_color=ACCENT)
        for row in self._rows.values():
            if not components.is_installed(row.component):
                row.set_state("queued", "")
        self.start_worker(self._worker, track=True)

    def _worker(self):
        components.cleanup_staging()
        for component in components.missing():
            if self._cancel.is_set():
                return
            self.post("state", component.name, "downloading", "Bağlanılıyor…")

            def progress(done, total, name=component.name):
                self.post("progress", name, done, total)
                if total and done >= total:
                    self.post("state", name, "verifying", "Dosyalar doğrulanıyor…")

            try:
                components.install(component, progress=progress, cancel_event=self._cancel)
            except components.Cancelled:
                return
            except components.ComponentError as exc:
                self.post("failed", component.name, str(exc))
                return
            except Exception:
                log.exception("Installing %s failed", component.name)
                self.post("failed", component.name, f"{component.title} kurulamadı. Lütfen tekrar deneyin.")
                return
            self.post("state", component.name, "done", f"Sürüm {component.version.split('-')[0]}")
        binaries.refresh()
        self.post("finished")

    # --- messages from the worker ----------------------------------------------

    def on_state(self, name, state, detail):
        row = self._rows.get(name)
        if row is not None:
            if state == "downloading":
                self._samples = []
            row.set_state(state, detail)

    def on_progress(self, name, done, total):
        row = self._rows.get(name)
        if row is None:
            return
        now = time.monotonic()
        self._samples = [(t, d) for t, d in self._samples if now - t <= SPEED_WINDOW] + [(now, done)]
        speed = 0
        if len(self._samples) > 1:
            (t0, d0), (t1, d1) = self._samples[0], self._samples[-1]
            if t1 > t0:
                speed = (d1 - d0) / (t1 - t0)
        if total:
            row.bar.set(min(done / total, 1.0))
        if not (total and done >= total):
            row.detail.configure(text=progress_text(done, total, speed), text_color=TEXT_FAINT)

    def on_failed(self, name, message):
        row = self._rows.get(name)
        if row is not None:
            row.set_state("failed", "")
        self.heading.configure(text="Kurulum tamamlanamadı", text_color=ERROR)
        self.message.configure(text=message)
        self.retry_btn.pack(pady=(10, 0), ipadx=18)

    def on_finished(self):
        self.heading.configure(text="Hazır!", text_color=SUCCESS)
        self.schedule(DONE_DELAY_MS, self.app.finish_setup)

    # --- cosmetics ------------------------------------------------------------

    def _animate(self):
        text = self.heading.cget("text").rstrip(".")
        if text == "Hazırlanıyor":
            self._dots = (self._dots + 1) % len(DOT_FRAMES)
            self.heading.configure(text=text + DOT_FRAMES[self._dots])
        self.schedule(450, self._animate)

    def shutdown(self):
        self._cancel.set()
        return super().shutdown()

    def destroy(self):
        self._cancel.set()
        super().destroy()

