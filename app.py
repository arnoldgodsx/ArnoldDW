"""Arnold DW - YouTube Video/Audio Downloader"""
import io
import html
import json
import os
import re
import sys
import queue
import threading
import time
import tkinter
import traceback
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps
import instaloader
import requests
import yt_dlp

# --------------------------------------------------------------------------
# Paths / resources
# --------------------------------------------------------------------------

def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


ICON_PATH = resource_path("logo", "icon.ico")
APP_LOGO_PATH = resource_path("logo", "icons8-fire-96.png")
YOUTUBE_LOGO_PATH = resource_path("logo", "youtube.png")
INSTAGRAM_LOGO_PATH = resource_path("logo", "instagram.png")
TIKTOK_LOGO_PATH = resource_path("logo", "tiktok.png")
BACK_ICON_PATH = resource_path("logo", "back.png")
FFMPEG_PATH = resource_path("bin", "ffmpeg.exe")

APP_NAME = "Arnold DW"
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Arnold DW")
CONFIG_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def load_download_dir():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("download_dir")
        if path:
            return path
    except Exception:
        pass
    return DEFAULT_DOWNLOAD_DIR


def save_download_dir(path):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"download_dir": path}, f)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Style constants
# --------------------------------------------------------------------------

BG = "#000000"
SURFACE = "#131316"
HOME_CARD = "#0C0C0F"
SURFACE_2 = "#1C1C21"
SURFACE_3 = "#26262D"
BORDER = "#2C2C34"
TEXT = "#FFFFFF"
TEXT_MUTED = "#B7B7C0"
TEXT_FAINT = "#75757F"
ACCENT = "#C026D3"
ACCENT_HOVER = "#A21CAF"
ACCENT_PRESS = "#86198F"
SUCCESS = "#30D158"
ERROR = "#FF453A"

FONT_FAMILY = "Segoe UI"
APP_WIDTH = 480
APP_HEIGHT = 720

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|live/)|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)
INSTAGRAM_POST_RE = re.compile(
    r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
INSTAGRAM_PROFILE_RE = re.compile(
    r"instagram\.com/([A-Za-z0-9._]+)",
    re.IGNORECASE,
)
INSTAGRAM_CRAWLER_USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

QUALITY_OPTIONS = ["4K", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
QUALITY_HEIGHTS = {
    "4K": 2160, "1440p": 1440, "1080p": 1080, "720p": 720,
    "480p": 480, "360p": 360, "240p": 240, "144p": 144,
}

AUDIO_OPTIONS = ["320 kbps", "192 kbps", "128 kbps"]
AUDIO_BITRATE = {"320 kbps": "320", "192 kbps": "192", "128 kbps": "128"}

PREVIEW_W, PREVIEW_H = 360, 203
SPINNER_DIAMETER = 48
SPINNER_WIDTH = 5


def _max_available_height(info):
    """Highest video height actually offered by YouTube for this video."""
    if not info:
        return 0
    heights = [f.get("height") or 0 for f in (info.get("formats") or [])]
    return max(heights) if heights else 0


def _available_quality_options(max_height):
    """Only ever offer quality rungs the source video actually supports."""
    if not max_height:
        return QUALITY_OPTIONS[:]
    opts = [label for label in QUALITY_OPTIONS if QUALITY_HEIGHTS[label] <= max_height]
    return opts or [QUALITY_OPTIONS[-1]]


def make_rounded(img: Image.Image, size, radius=14):
    img = ImageOps.fit(img, size, Image.LANCZOS)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255)
    out = Image.new("RGBA", size)
    out.paste(img, (0, 0), mask)
    return out


def _hex_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _set_noactivate(win):
    """Mark a Toplevel as non-activating (Windows only).

    Without this, clicking anywhere on the popup - even just one of its
    option rows - hands OS-level window activation to it, which makes
    Windows immediately render the main app's titlebar in its "inactive"
    gray state for as long as the popup is up. WS_EX_NOACTIVATE stops the
    popup from ever becoming the active window at all; it can still receive
    and act on mouse clicks normally.
    """
    try:
        import ctypes
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
    except Exception:
        pass


def _spinner_sprite(angle, diameter=SPINNER_DIAMETER, width=SPINNER_WIDTH):
    """A small transparent PNG with a faint ring + a bright rotating arc on it."""
    ring_color = _hex_rgb(ACCENT) + (255,)
    track_color = _hex_rgb(TEXT) + (46,)
    size = diameter + width * 2 + 4
    sprite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    pad = width // 2 + 2
    bbox = [pad, pad, size - pad, size - pad]
    draw.arc(bbox, 0, 360, fill=track_color, width=width)
    draw.arc(bbox, angle, angle + 100, fill=ring_color, width=width)
    return sprite


def _dim_image(img, alpha=150, radius=12):
    """Darken a rounded-rect image while keeping its transparent corners transparent."""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle([(0, 0), (base.width - 1, base.height - 1)], radius=radius, fill=(0, 0, 0, alpha))
    return Image.alpha_composite(base, overlay)


def _compose_spinner_frame(base_img, angle, diameter=SPINNER_DIAMETER, width=SPINNER_WIDTH):
    frame = base_img.convert("RGBA").copy()
    sprite = _spinner_sprite(angle, diameter, width)
    x = (frame.width - sprite.width) // 2
    y = (frame.height - sprite.height) // 2
    frame.paste(sprite, (x, y), sprite)
    return frame


def fmt_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_speed(bps):
    if not bps:
        return ""
    mb = bps / 1_000_000
    if mb >= 1:
        return f"{mb:.1f} MB/s"
    return f"{bps / 1000:.0f} KB/s"


def fmt_eta(seconds):
    """Remaining-time display: whole minutes, or whole seconds under a minute - never fractional."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds} sn"
    return f"{round(seconds / 60)} dk"


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "private video" in low:
        return "Bu video gizli, indirilemez."
    if "video unavailable" in low:
        return "Video artık mevcut değil."
    if "age" in low and "restrict" in low:
        return "Bu video yaş sınırlaması nedeniyle indirilemiyor."
    if "sign in" in low or "login" in low:
        return "Bu videoya erişim için giriş gerekiyor."
    if "unable to extract" in low or "unsupported url" in low:
        return "Bağlantı çözümlenemedi. Linki kontrol edin."
    if "timed out" in low or "timeout" in low:
        return "Bağlantı zaman aşımına uğradı. Tekrar deneyin."
    if "permission denied" in low or "winerror 5" in low:
        return "Seçilen klasöre yazma izni yok. Başka bir klasör seçin."
    if "no such file or directory" in low or "cannot find the path" in low or "winerror 3" in low:
        return "Seçilen indirme klasörü bulunamadı."
    if "network" in low or "connection" in low or "resolve host" in low:
        return "İnternet bağlantısı sorunu tespit edildi."
    return "Bir hata oluştu. Lütfen bağlantıyı kontrol edip tekrar deneyin."


def instagram_friendly_error(exc: Exception) -> str:
    low = str(exc).lower()
    if "profile does not exist" in low or "not found" in low:
        return "Instagram kullanıcısı veya gönderisi bulunamadı."
    if "private profile" in low or "is private" in low:
        return "Bu hesap gizli. Yalnızca profil fotoğrafı kullanılabilir."
    if "login" in low or "401" in low or "403" in low:
        return "Bu içeriğe oturum açmadan erişilemiyor."
    if (
        "429" in low
        or "too many requests" in low
        or "please wait a few minutes" in low
    ):
        return "Instagram geçici olarak çok fazla istek algıladı. Biraz sonra deneyin."
    if "connection" in low or "network" in low or "timeout" in low:
        return "Instagram bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin."
    return "Instagram içeriği alınamadı. Linki veya kullanıcı adını kontrol edin."


def instagram_post_media(post):
    """Return original media URLs represented by an Instaloader Post."""
    media = []
    if post.typename == "GraphSidecar":
        for index, node in enumerate(post.get_sidecar_nodes(), start=1):
            media.append({
                "index": index,
                "is_video": bool(node.is_video),
                "url": node.video_url if node.is_video else node.display_url,
                "thumbnail_url": node.display_url,
            })
    else:
        media.append({
            "index": 1,
            "is_video": bool(post.is_video),
            "url": post.video_url if post.is_video else post.url,
            "thumbnail_url": post.url,
        })
    return media


def safe_filename_part(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:100] or "instagram"


class ThemedDropdown(ctk.CTkFrame):
    """A CTkOptionMenu look-alike whose popup is fully custom-drawn.

    CTkOptionMenu's own dropdown list is a native OS menu (tkinter.Menu) on
    Windows - it always renders with square corners and native menu chrome,
    no matter what colors are passed to it, so it looks visually disconnected
    from a fully custom-themed app. This draws the popup as a plain CTkFrame
    of CTkButtons instead, matching the rest of the UI exactly.
    """

    def __init__(self, master, values, variable, command=None,
                 height=40, corner_radius=10, font=None, state="normal", **kwargs):
        super().__init__(master, fg_color=SURFACE, corner_radius=corner_radius,
                          height=height, **kwargs)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self._values = list(values)
        self._variable = variable
        self._command = command
        self._font = font or (FONT_FAMILY, 13)
        self._state = state
        self._popup = None
        self._popup_opened_at = 0.0
        self._hovering = False

        self.grid_rowconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            self, text=self._variable.get(), text_color=TEXT,
            font=self._font, anchor="w",
        )
        self._label.grid(row=0, column=0, sticky="ew", padx=(14, 2))

        self._arrow = ctk.CTkLabel(
            self, text="▾", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 17, "bold"),
        )
        self._arrow.grid(row=0, column=1, padx=(0, 14))

        for widget in (self, self._label, self._arrow):
            widget.bind("<Button-1>", self._toggle)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        self._variable.trace_add("write", self._sync_label)
        self._apply_state_visual()

    def _sync_label(self, *_args):
        self._label.configure(text=self._variable.get())

    def _apply_state_visual(self):
        if self._state == "disabled":
            self._label.configure(text_color=TEXT_FAINT)
            self._arrow.configure(text_color=TEXT_FAINT)
            super().configure(fg_color=SURFACE)
        else:
            self._label.configure(text_color=TEXT)
            self._arrow.configure(text_color=TEXT_MUTED)

    def _on_enter(self, _event=None):
        if self._state == "disabled":
            return
        self._hovering = True
        super().configure(fg_color=SURFACE_2)

    def _on_leave(self, _event=None):
        self._hovering = False
        if self._popup is None:
            super().configure(fg_color=SURFACE)

    def _toggle(self, _event=None):
        if self._state == "disabled":
            return
        if self._popup is not None:
            self._close_popup(force=True)
        else:
            self._open_popup()

    def _open_popup(self):
        if not self._values:
            return
        super().configure(fg_color=SURFACE_2)

        popup = tkinter.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        _set_noactivate(popup)
        try:
            popup.attributes("-topmost", True)
            popup.attributes("-alpha", 0.0)
        except Exception:
            pass

        panel = ctk.CTkFrame(
            popup, fg_color=SURFACE_2, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        panel.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(panel, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        current = self._variable.get()
        for value in self._values:
            is_current = value == current
            row = ctk.CTkButton(
                inner, text=value, anchor="w", height=34,
                corner_radius=6,
                fg_color=(ACCENT if is_current else "transparent"),
                hover_color=(ACCENT_HOVER if is_current else SURFACE_3),
                text_color=TEXT, font=self._font,
                command=lambda v=value: self._select(v),
            )
            row.pack(fill="x", pady=(0, 4))

        popup.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        w = self.winfo_width()
        h = popup.winfo_reqheight()

        screen_h = self.winfo_screenheight()
        if y + h > screen_h - 8:
            y = self.winfo_rooty() - h - 4

        popup.geometry(f"{w}x{h}+{x}+{y}")
        try:
            popup.attributes("-alpha", 1.0)
        except Exception:
            pass

        # No focus_force()/keyboard binding here on purpose: the popup is
        # WS_EX_NOACTIVATE (see _set_noactivate), so it can never receive
        # keyboard focus - closing is handled entirely by
        # _route_global_click below, which needs no focus at all.

        self._popup = popup
        self._popup_opened_at = time.monotonic()
        self._ensure_global_click_watch()

    def _ensure_global_click_watch(self):
        # The popup closes based on routing every in-app click through here,
        # not on OS focus events (FocusOut proved unreliable - it can fire
        # immediately in some environments, closing the popup before a user
        # could ever click an option).
        root = self.winfo_toplevel()
        if getattr(root, "_dropdown_click_watch_installed", False):
            return
        root.bind_all("<Button-1>", self._route_global_click, add="+")
        root._dropdown_click_watch_installed = True

    def _route_global_click(self, event):
        if self._popup is None:
            return
        clicked = event.widget
        if clicked in (self, self._label, self._arrow):
            return  # the trigger's own binding handles this click
        try:
            top = clicked.winfo_toplevel()
        except Exception:
            top = None
        if top is self._popup:
            return  # click landed on an option row; its own command handles it
        self._close_popup()

    def _select(self, value):
        self._variable.set(value)
        self._close_popup(force=True)
        if self._command is not None:
            self._command(value)

    def _close_popup(self, force=False):
        if self._popup is None:
            return
        # Guard against any spurious/ambient close trigger landing in the
        # first instant after opening (some environments fire odd focus/click
        # events right at window-creation time). A deliberate user action
        # (picking an option, clicking the trigger again) always bypasses
        # this via force=True; only the passive global-click watcher waits.
        if not force and (time.monotonic() - self._popup_opened_at) < 0.25:
            return
        popup = self._popup
        self._popup = None
        try:
            popup.destroy()
        except Exception:
            pass
        if not self._hovering:
            super().configure(fg_color=SURFACE)

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._values = list(kwargs.pop("values"))
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            if self._state == "disabled":
                self._close_popup(force=True)
            self._apply_state_visual()
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            super().configure(**kwargs)

    def cget(self, attribute_name):
        if attribute_name == "values":
            return list(self._values)
        if attribute_name == "state":
            return self._state
        return super().cget(attribute_name)


class ArnoldDW(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.ui_queue = queue.Queue()
        self.current_info = None
        self.current_url = None
        self.request_id = 0
        self.debounce_job = None
        self.thumb_ctk_image = None
        self._thumb_pil_image = None

        self._preview_spin_job = None
        self._preview_spin_angle = 0

        self._processing_active = False
        self._processing_job = None
        self._processing_angle = 0
        self._processing_tick_count = 0
        self._processing_dots = 0
        self._processing_base_img = None

        self._is_downloading = False
        self.cancel_event = None

        self.download_dir = load_download_dir()
        self.current_screen = "home"
        self.instagram_profile_cache = {}

        self._configure_window()
        self._build_ui()
        self._apply_dark_titlebar()

        self.after(60, self._poll_queue)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _configure_window(self):
        self.title("Arnold DW")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        try:
            self.iconbitmap(ICON_PATH)
        except Exception:
            pass

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ArnoldDW.YoutubeDownloader.1"
            )
        except Exception:
            pass

    def _apply_dark_titlebar(self):
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._show_home()

    def _clear_screen(self):
        for child in self.winfo_children():
            child.destroy()

    def _show_home(self):
        self._clear_screen()
        self.current_screen = "home"
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")

        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=28, pady=(30, 14))

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack()
        app_logo = Image.open(APP_LOGO_PATH).convert("RGBA")
        self.home_app_logo = ctk.CTkImage(
            light_image=app_logo,
            dark_image=app_logo,
            size=(86, 86),
        )
        ctk.CTkLabel(header, text="", image=self.home_app_logo).pack()

        ctk.CTkLabel(
            header,
            text="Arnold DW",
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 27, "bold"),
        ).pack(pady=(6, 0))

        self.home_platform_images = {}
        cards = ctk.CTkFrame(root, fg_color="transparent")
        cards.place(relx=0.5, rely=0.5, anchor="center", relwidth=1)

        platforms = (
            ("YouTube", YOUTUBE_LOGO_PATH, self._show_youtube),
            ("Instagram", INSTAGRAM_LOGO_PATH, self._show_instagram),
            ("TikTok", TIKTOK_LOGO_PATH, None),
        )

        for index, (name, logo_path, command) in enumerate(platforms):
            logo = Image.open(logo_path).convert("RGBA")
            platform_image = ctk.CTkImage(
                light_image=logo,
                dark_image=logo,
                size=(40, 40),
            )
            self.home_platform_images[name] = platform_image

            card = ctk.CTkButton(
                cards,
                text=name,
                image=platform_image,
                compound="left",
                anchor="w",
                command=command,
                height=64,
                corner_radius=10,
                border_width=1,
                border_color=BORDER,
                border_spacing=18,
                fg_color=HOME_CARD,
                hover_color=SURFACE,
                text_color=TEXT,
                font=(FONT_FAMILY, 17, "bold"),
            )
            card.pack(fill="x", pady=(0, 22 if index < 2 else 0))

        self.update_idletasks()
        header_bottom = header.winfo_y() + header.winfo_height()
        available_bottom = root.winfo_height()
        lower_area_center = (header_bottom + available_bottom) / 2
        cards.place_configure(
            rely=lower_area_center / available_bottom,
            y=0,
        )

    def _show_youtube(self):
        self._clear_screen()
        self.current_screen = "youtube"
        self._build_youtube_ui()

    def _back_to_home(self):
        if self._is_downloading or self._processing_active:
            return
        if self.debounce_job is not None:
            self.after_cancel(self.debounce_job)
            self.debounce_job = None
        self.request_id += 1
        self._stop_preview_spinner()
        self._show_home()

    # ------------------------------------------------------------------
    # Instagram
    # ------------------------------------------------------------------

    def _show_instagram(self):
        self._clear_screen()
        self.current_screen = "instagram"
        self.current_info = None
        self.current_url = None
        self.instagram_mode = None
        self.instagram_loader = None
        self.instagram_post = None
        self.instagram_profile = None
        self.instagram_media = []
        self.instagram_media_vars = []
        self.instagram_category_vars = {}
        self.instagram_preview_images = []

        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=28, pady=(30, 14))

        self._build_instagram_input(root)

        self.instagram_preview_card = ctk.CTkFrame(
            root,
            fg_color=SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            height=350,
        )
        self.instagram_preview_card.pack(fill="x", pady=(0, 14))
        self.instagram_preview_card.pack_propagate(False)

        self.instagram_preview_content = ctk.CTkFrame(
            self.instagram_preview_card,
            fg_color="transparent",
        )
        self.instagram_preview_content.pack(fill="both", expand=True, padx=14, pady=14)
        self._show_instagram_empty()

        self._build_save_location(root)

        self.instagram_download_btn = ctk.CTkButton(
            root,
            text="İndir",
            command=self._on_instagram_download,
            height=50,
            corner_radius=12,
            state="disabled",
            fg_color=SURFACE_3,
            hover_color=ACCENT_HOVER,
            text_color=TEXT,
            text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.instagram_download_btn.pack(fill="x")

    def _build_instagram_input(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=46)
        row.pack(fill="x", pady=(0, 4))
        row.pack_propagate(False)

        back_icon = Image.open(BACK_ICON_PATH).convert("RGBA")
        self.instagram_back_icon_image = ctk.CTkImage(
            light_image=back_icon,
            dark_image=back_icon,
            size=(22, 22),
        )
        self.back_btn = ctk.CTkButton(
            row,
            text="",
            image=self.instagram_back_icon_image,
            command=self._back_to_home,
            width=46,
            height=46,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color_disabled=TEXT_FAINT,
        )
        self.back_btn.pack(side="left", padx=(0, 8))

        self.instagram_entry = ctk.CTkEntry(
            row,
            placeholder_text="Instagram linki veya kullanıcı adı...",
            height=46,
            corner_radius=10,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
        )
        self.instagram_entry.pack(side="left", fill="both", expand=True)
        self.instagram_entry.bind("<KeyRelease>", self._on_instagram_input_changed)
        self.instagram_entry.bind(
            "<<Paste>>",
            lambda e: self.after(10, self._on_instagram_input_changed),
        )
        self.instagram_entry.bind(
            "<FocusIn>",
            lambda e: self.instagram_entry.configure(border_color=ACCENT),
        )
        self.instagram_entry.bind(
            "<FocusOut>",
            lambda e: self.instagram_entry.configure(border_color=BORDER),
        )

        self.instagram_clear_btn = ctk.CTkButton(
            row,
            text="✕",
            width=34,
            height=34,
            corner_radius=8,
            fg_color=SURFACE_2,
            hover_color=SURFACE_3,
            border_width=0,
            text_color=TEXT_MUTED,
            text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
            command=self._clear_instagram_input,
        )

        self.instagram_status_label = ctk.CTkLabel(
            parent,
            text="",
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12),
            anchor="w",
            justify="left",
        )
        self.instagram_status_label.pack(fill="x", pady=(0, 4))

    def _replace_instagram_preview(self):
        for child in self.instagram_preview_content.winfo_children():
            child.destroy()
        self.instagram_preview_images = []

    def _show_instagram_empty(self):
        self._replace_instagram_preview()
        empty = ctk.CTkFrame(self.instagram_preview_content, fg_color="transparent")
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

    def _show_instagram_loading(self):
        self._replace_instagram_preview()
        loading = ctk.CTkFrame(self.instagram_preview_content, fg_color="transparent")
        loading.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(
            loading,
            text="Yükleniyor...",
            text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack()

    def _set_instagram_status(self, text, color=TEXT_MUTED):
        self.instagram_status_label.configure(text=text, text_color=color)

    def _update_instagram_clear_button(self):
        has_content = bool(self.instagram_entry.get().strip())
        if has_content and not self.instagram_clear_btn.winfo_ismapped():
            self.instagram_clear_btn.place(
                in_=self.instagram_entry,
                relx=1.0,
                rely=0.5,
                anchor="e",
                x=-6,
            )
        elif not has_content and self.instagram_clear_btn.winfo_ismapped():
            self.instagram_clear_btn.place_forget()

    def _clear_instagram_input(self):
        if self.debounce_job is not None:
            self.after_cancel(self.debounce_job)
            self.debounce_job = None
        self.request_id += 1
        self.instagram_entry.delete(0, "end")
        self.instagram_entry.focus_set()
        self.instagram_mode = None
        self.instagram_media = []
        self.instagram_category_vars = {}
        self._set_instagram_status("")
        self.instagram_download_btn.configure(
            state="disabled",
            fg_color=SURFACE_3,
            text="İndir",
        )
        self._show_instagram_empty()
        self._update_instagram_clear_button()

    def _on_instagram_input_changed(self, event=None):
        self._update_instagram_clear_button()
        if self.debounce_job is not None:
            self.after_cancel(self.debounce_job)
            self.debounce_job = None

        value = self.instagram_entry.get().strip()
        if not value:
            self._clear_instagram_input()
            return

        self.request_id += 1
        rid = self.request_id
        self._set_instagram_status("")
        self.instagram_download_btn.configure(state="disabled", fg_color=SURFACE_3)
        self._show_instagram_loading()
        self.debounce_job = self.after(
            1200,
            lambda: self._start_instagram_resolve(value, rid),
        )

    def _start_instagram_resolve(self, value, rid):
        self.debounce_job = None
        threading.Thread(
            target=self._instagram_resolve_worker,
            args=(value, rid),
            daemon=True,
        ).start()

    def _new_instagram_loader(self):
        return instaloader.Instaloader(
            sleep=False,
            max_connection_attempts=1,
            request_timeout=15,
            user_agent=INSTAGRAM_CRAWLER_USER_AGENT,
            iphone_support=False,
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

    def _instagram_public_profile(self, loader, username):
        profile_url = f"https://www.instagram.com/{username}/"
        response = requests.get(
            profile_url,
            headers={"User-Agent": INSTAGRAM_CRAWLER_USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        page = response.text

        def meta_content(property_name):
            match = re.search(
                rf'<meta[^>]+property=["\']{re.escape(property_name)}["\']'
                rf'[^>]+content=["\']([^"\']+)',
                page,
                re.IGNORECASE,
            )
            if match is None:
                match = re.search(
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+'
                    rf'property=["\']{re.escape(property_name)}["\']',
                    page,
                    re.IGNORECASE,
                )
            return html.unescape(match.group(1)) if match else ""

        user_id_match = re.search(r"profilePage_([0-9]+)", page)
        if user_id_match is None:
            user_id_match = re.search(r'"user_id":"?([0-9]+)', page)
        if user_id_match is None:
            raise instaloader.ProfileNotExistsException(
                f"Profile does not exist: {username}"
            )

        title = meta_content("og:title")
        full_name = title.split("(@", 1)[0].strip() if "(@" in title else username
        profile_pic_url = meta_content("og:image")
        user_id = user_id_match.group(1)

        variables = {
            "data": {
                "count": 12,
                "include_relationship_info": True,
                "latest_besties_reel_media": True,
                "latest_reel_media": True,
            },
            "id": int(user_id),
            "after": None,
            "first": 12,
        }
        result = loader.context.doc_id_graphql_query(
            "7950326061742207",
            variables,
            referer=profile_url,
        )
        user_data = (result.get("data") or {}).get("user") or {}
        timeline = user_data.get("edge_owner_to_timeline_media")
        is_private = timeline is None
        if timeline is None:
            timeline = {
                "count": 0,
                "page_info": {"has_next_page": False, "end_cursor": None},
                "edges": [],
            }

        node = {
            "id": user_id,
            "username": username,
            "full_name": full_name,
            "is_private": is_private,
            "profile_pic_url": profile_pic_url,
            "profile_pic_url_hd": profile_pic_url,
            "edge_owner_to_timeline_media": timeline,
            "edge_followed_by": {"count": 0},
            "edge_follow": {"count": 0},
        }
        profile = instaloader.Profile(loader.context, node)
        profile._has_full_metadata = True
        return profile

    def _instagram_resolve_worker(self, value, rid):
        try:
            loader = self._new_instagram_loader()
            post_match = INSTAGRAM_POST_RE.search(value)
            if post_match:
                post = instaloader.Post.from_shortcode(loader.context, post_match.group(1))
                media = instagram_post_media(post)
                thumbnails = []
                for item in media:
                    image = None
                    try:
                        response = requests.get(item["thumbnail_url"], timeout=15)
                        response.raise_for_status()
                        image = Image.open(io.BytesIO(response.content)).convert("RGB")
                    except Exception:
                        pass
                    thumbnails.append(image)
                self.ui_queue.put((
                    "instagram_post_ok",
                    rid,
                    loader,
                    post,
                    media,
                    thumbnails,
                ))
                return

            profile_match = INSTAGRAM_PROFILE_RE.search(value)
            username = profile_match.group(1) if profile_match else value
            username = username.strip().lstrip("@").strip("/")
            if not re.fullmatch(r"[A-Za-z0-9._]+", username):
                raise ValueError("Invalid Instagram username")

            cached = self.instagram_profile_cache.get(username.lower())
            if cached is not None:
                cached_loader, cached_profile, cached_avatar = cached
                self.ui_queue.put((
                    "instagram_profile_ok",
                    rid,
                    cached_loader,
                    cached_profile,
                    cached_avatar,
                ))
                return

            profile = self._instagram_public_profile(loader, username)
            avatar = None
            try:
                response = requests.get(str(profile.profile_pic_url), timeout=15)
                response.raise_for_status()
                avatar = Image.open(io.BytesIO(response.content)).convert("RGB")
            except Exception:
                pass
            self.instagram_profile_cache[username.lower()] = (loader, profile, avatar)
            self.ui_queue.put(("instagram_profile_ok", rid, loader, profile, avatar))
        except Exception as exc:
            self.ui_queue.put(("instagram_err", rid, instagram_friendly_error(exc)))

    def _apply_instagram_post(self, loader, post, media, thumbnails):
        self.instagram_mode = "post"
        self.instagram_loader = loader
        self.instagram_post = post
        self.instagram_profile = None
        self.instagram_media = media
        self.instagram_media_vars = []
        self._replace_instagram_preview()

        media_type = "Carousel" if len(media) > 1 else ("Video" if media[0]["is_video"] else "Fotoğraf")
        ctk.CTkLabel(
            self.instagram_preview_content,
            text=f"@{post.owner_username}  •  {media_type}",
            text_color=TEXT,
            font=(FONT_FAMILY, 14, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        if len(media) == 1:
            image = thumbnails[0]
            if image is not None:
                preview = make_rounded(image, (300, 230), radius=10)
                preview_image = ctk.CTkImage(preview, size=(300, 230))
                self.instagram_preview_images.append(preview_image)
                ctk.CTkLabel(
                    self.instagram_preview_content,
                    text="",
                    image=preview_image,
                ).pack()
            else:
                ctk.CTkLabel(
                    self.instagram_preview_content,
                    text="Önizleme yüklenemedi",
                    text_color=TEXT_FAINT,
                    font=(FONT_FAMILY, 13),
                ).pack(expand=True)
            self.instagram_media_vars = [ctk.BooleanVar(value=True)]
        else:
            toolbar = ctk.CTkFrame(self.instagram_preview_content, fg_color="transparent")
            toolbar.pack(fill="x", pady=(0, 8))
            self.instagram_select_all_var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                toolbar,
                text=f"Tümünü seç ({len(media)})",
                variable=self.instagram_select_all_var,
                command=self._toggle_all_instagram_media,
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
                self.instagram_preview_content,
                orientation="horizontal",
                fg_color="transparent",
                height=225,
            )
            strip.pack(fill="both", expand=True)

            for index, (item, image) in enumerate(zip(media, thumbnails), start=1):
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
                    thumb = make_rounded(image, (104, 120), radius=8)
                    thumb_image = ctk.CTkImage(thumb, size=(104, 120))
                    self.instagram_preview_images.append(thumb_image)
                    ctk.CTkLabel(tile, text="", image=thumb_image).pack(pady=(8, 4))
                else:
                    ctk.CTkLabel(
                        tile,
                        text="Önizleme yok",
                        text_color=TEXT_FAINT,
                        font=(FONT_FAMILY, 11),
                        width=104,
                        height=120,
                    ).pack(pady=(8, 4))

                var = ctk.BooleanVar(value=True)
                self.instagram_media_vars.append(var)
                ctk.CTkCheckBox(
                    tile,
                    text=f"{index}. {'Video' if item['is_video'] else 'Fotoğraf'}",
                    variable=var,
                    command=self._update_instagram_download_state,
                    checkbox_width=18,
                    checkbox_height=18,
                    corner_radius=5,
                    fg_color=ACCENT,
                    hover_color=ACCENT_HOVER,
                    border_color=BORDER,
                    text_color=TEXT_MUTED,
                    font=(FONT_FAMILY, 11),
                ).pack(padx=8, pady=(2, 8))

        self._set_instagram_status("")
        self._update_instagram_download_state()

    def _toggle_all_instagram_media(self):
        selected = bool(self.instagram_select_all_var.get())
        for var in self.instagram_media_vars:
            var.set(selected)
        self._update_instagram_download_state()

    def _apply_instagram_profile(self, loader, profile, avatar):
        self.instagram_mode = "profile"
        self.instagram_loader = loader
        self.instagram_profile = profile
        self.instagram_post = None
        self.instagram_media = []
        self._replace_instagram_preview()

        header = ctk.CTkFrame(self.instagram_preview_content, fg_color="transparent")
        header.pack(fill="x", pady=(2, 16))
        if avatar is not None:
            rounded = make_rounded(avatar, (72, 72), radius=36)
            avatar_image = ctk.CTkImage(rounded, size=(72, 72))
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
            self.instagram_preview_content,
            text="İNDİRİLEBİLİR KATEGORİLER",
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        categories = (
            ("posts", "Gönderiler / Fotoğraflar"),
            ("reels", "Reels / Videolar"),
            ("profile_pic", "Profil Fotoğrafı"),
        )
        self.instagram_category_vars = {}
        for key, label in categories:
            var = ctk.BooleanVar(value=False)
            self.instagram_category_vars[key] = var
            state = "disabled" if profile.is_private and key != "profile_pic" else "normal"
            checkbox = ctk.CTkCheckBox(
                self.instagram_preview_content,
                text=label,
                variable=var,
                command=self._update_instagram_download_state,
                state=state,
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
            )
            checkbox.pack(fill="x", pady=(0, 6))

        if profile.is_private:
            self._set_instagram_status(
                "Gizli hesaplarda yalnızca profil fotoğrafı indirilebilir.",
                TEXT_MUTED,
            )
        else:
            self._set_instagram_status("")
        self._update_instagram_download_state()

    def _update_instagram_download_state(self):
        enabled = False
        if self.instagram_mode == "post":
            enabled = any(var.get() for var in self.instagram_media_vars)
        elif self.instagram_mode == "profile":
            enabled = any(var.get() for var in self.instagram_category_vars.values())

        self.instagram_download_btn.configure(
            state="normal" if enabled else "disabled",
            fg_color=ACCENT if enabled else SURFACE_3,
        )

    def _on_instagram_download(self):
        if self._is_downloading:
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.instagram_download_btn.configure(
                state="disabled",
                fg_color=SURFACE_3,
                text="İptal ediliyor...",
            )
            return

        if self.instagram_mode == "post":
            selected_media = [
                item
                for item, var in zip(self.instagram_media, self.instagram_media_vars)
                if var.get()
            ]
            if not selected_media:
                return
            payload = ("post", selected_media)
        elif self.instagram_mode == "profile":
            categories = [
                key for key, var in self.instagram_category_vars.items() if var.get()
            ]
            if not categories:
                return
            payload = ("profile", categories)
        else:
            return

        self._is_downloading = True
        self.cancel_event = threading.Event()
        self.back_btn.configure(state="disabled")
        self.instagram_entry.configure(state="disabled")
        self.instagram_clear_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.instagram_download_btn.configure(
            state="normal",
            fg_color=SURFACE_2,
            hover_color=SURFACE_3,
            text="İptal Et",
        )
        self._set_instagram_status("İndirme başlatılıyor...", TEXT_MUTED)

        threading.Thread(
            target=self._instagram_download_worker,
            args=(payload, self.download_dir, self.cancel_event),
            daemon=True,
        ).start()

    def _download_instagram_media(self, item, folder, basename, cancel_event):
        if cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        extension = ".mp4" if item["is_video"] else ".jpg"
        path = os.path.join(folder, f"{safe_filename_part(basename)}{extension}")
        if os.path.exists(path):
            return False

        response = requests.get(item["url"], stream=True, timeout=30)
        response.raise_for_status()
        with open(path, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if cancel_event.is_set():
                    output.close()
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    raise yt_dlp.utils.DownloadCancelled()
                if chunk:
                    output.write(chunk)
        return True

    def _download_instagram_post_items(
        self,
        post,
        folder,
        cancel_event,
        seen_shortcodes,
    ):
        if post.shortcode in seen_shortcodes:
            return 0
        seen_shortcodes.add(post.shortcode)
        count = 0
        for item in instagram_post_media(post):
            if not item["url"]:
                continue
            basename = (
                f"instagram_{post.owner_username}_"
                f"{post.shortcode}_{item['index']:02d}"
            )
            if self._download_instagram_media(
                item,
                folder,
                basename,
                cancel_event,
            ):
                count += 1
        return count

    def _instagram_download_worker(self, payload, download_dir, cancel_event):
        try:
            root = download_dir
            os.makedirs(root, exist_ok=True)
            downloaded = 0

            if payload[0] == "post":
                post = self.instagram_post
                folder = root
                for position, item in enumerate(payload[1], start=1):
                    self.ui_queue.put((
                        "instagram_progress",
                        f"{position}/{len(payload[1])} indiriliyor...",
                    ))
                    basename = (
                        f"instagram_{post.owner_username}_"
                        f"{post.shortcode}_{item['index']:02d}"
                    )
                    if self._download_instagram_media(
                        item,
                        folder,
                        basename,
                        cancel_event,
                    ):
                        downloaded += 1
            else:
                profile = self.instagram_profile
                categories = payload[1]
                profile_root = root
                seen_shortcodes = set()

                if "profile_pic" in categories:
                    self.ui_queue.put(("instagram_progress", "Profil fotoğrafı indiriliyor..."))
                    profile_item = {
                        "is_video": False,
                        "url": str(profile.profile_pic_url),
                    }
                    folder = profile_root
                    if self._download_instagram_media(
                        profile_item,
                        folder,
                        f"instagram_{profile.username}_profil",
                        cancel_event,
                    ):
                        downloaded += 1

                if "posts" in categories:
                    folder = profile_root
                    for index, post in enumerate(profile.get_posts(), start=1):
                        if cancel_event.is_set():
                            raise yt_dlp.utils.DownloadCancelled()
                        if post.is_video and post.typename != "GraphSidecar":
                            continue
                        self.ui_queue.put((
                            "instagram_progress",
                            f"Gönderi {index} indiriliyor...",
                        ))
                        downloaded += self._download_instagram_post_items(
                            post,
                            folder,
                            cancel_event,
                            seen_shortcodes,
                        )

                if "reels" in categories:
                    folder = profile_root
                    video_index = 0
                    for post in profile.get_posts():
                        if cancel_event.is_set():
                            raise yt_dlp.utils.DownloadCancelled()
                        if not post.is_video:
                            continue
                        video_index += 1
                        self.ui_queue.put((
                            "instagram_progress",
                            f"Reels/video {video_index} indiriliyor...",
                        ))
                        downloaded += self._download_instagram_post_items(
                            post,
                            folder,
                            cancel_event,
                            seen_shortcodes,
                        )

            self.ui_queue.put(("instagram_done", downloaded))
        except yt_dlp.utils.DownloadCancelled:
            self.ui_queue.put(("instagram_cancelled",))
        except Exception as exc:
            self.ui_queue.put(("instagram_download_err", instagram_friendly_error(exc)))

    def _restore_instagram_inputs(self):
        self._is_downloading = False
        self.cancel_event = None
        self.back_btn.configure(state="normal")
        self.instagram_entry.configure(state="normal")
        self.instagram_clear_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.instagram_download_btn.configure(text="İndir")
        self.instagram_download_btn.configure(hover_color=ACCENT_HOVER)
        self._update_instagram_download_state()

    def _finish_instagram_download_ui(self):
        if self.current_screen != "instagram":
            return
        self._restore_instagram_inputs()
        self._clear_instagram_input()

    def _build_youtube_ui(self):
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        root = ctk.CTkFrame(self, fg_color=BG)
        root.pack(fill="both", expand=True, padx=28, pady=(30, 14))

        self._build_url_section(root)
        self._build_preview(root)
        self._build_options(root)
        self._build_save_location(root)
        self._build_download_button(root)
        self._build_progress(root)

        self._prepare_progress_layout()

    def _prepare_progress_layout(self):
        # Measure the progress widgets once without changing the fixed 1:1.5
        # application window, then hide them until a download starts.
        self.progress_frame.pack(fill="x", pady=(0, 6))
        self._show_progress_info_row()
        self.update_idletasks()
        self.progress_info_row.pack_forget()
        self.progress_frame.pack_forget()

    def _build_url_section(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=46)
        row.pack(fill="x", pady=(0, 4))
        row.pack_propagate(False)

        back_icon = Image.open(BACK_ICON_PATH).convert("RGBA")
        self.back_icon_image = ctk.CTkImage(
            light_image=back_icon,
            dark_image=back_icon,
            size=(22, 22),
        )
        self.back_btn = ctk.CTkButton(
            row,
            text="",
            image=self.back_icon_image,
            command=self._back_to_home,
            width=46,
            height=46,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color_disabled=TEXT_FAINT,
        )
        self.back_btn.pack(side="left", padx=(0, 8))

        self.url_entry = ctk.CTkEntry(
            row,
            placeholder_text="YouTube video bağlantısını yapıştırın...",
            height=46, corner_radius=10,
            fg_color=SURFACE, border_width=1, border_color=BORDER,
            text_color=TEXT, placeholder_text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
        )
        self.url_entry.pack(side="left", fill="both", expand=True)
        self.url_entry.bind("<KeyRelease>", self._on_url_changed)
        self.url_entry.bind("<<Paste>>", lambda e: self.after(10, self._on_url_changed))
        self.url_entry.bind(
            "<FocusIn>",
            lambda e: self.url_entry.configure(border_color=ACCENT),
        )
        self.url_entry.bind(
            "<FocusOut>",
            lambda e: self.url_entry.configure(border_color=BORDER),
        )

        # Clear ("vazgeç") button - floats over the entry's own right edge
        # instead of taking its own column, so the entry spans the full row
        # width and its right edge lines up with the preview card below it.
        self.clear_btn = ctk.CTkButton(
            row, text="✕", width=34, height=34, corner_radius=8,
            fg_color=SURFACE_2, hover_color=SURFACE_3, border_width=0,
            text_color=TEXT_MUTED, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13), command=self._on_clear_clicked,
        )

        self.status_label = ctk.CTkLabel(
            parent, text="", text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 12), anchor="w", justify="left",
        )
        self.status_label.pack(fill="x", pady=(0, 4))

    def _build_preview(self, parent):
        self.preview_card = ctk.CTkFrame(
            parent, fg_color=SURFACE, corner_radius=10,
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

    def _build_options(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
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

        self.format_var = ctk.StringVar(value="MP4")
        self.format_seg = ctk.CTkSegmentedButton(
            fmt_col, values=["MP4", "MP3"], variable=self.format_var,
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
            qual_col, values=QUALITY_OPTIONS, variable=self.quality_var,
            height=40, corner_radius=10, font=(FONT_FAMILY, 13, "bold"), state="disabled",
        )
        self.quality_menu.pack(fill="x")

    def _build_save_location(self, parent):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(
            col, text="KAYIT KONUMU", text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=(8, 0), pady=(0, 6))

        row = ctk.CTkFrame(col, fg_color="transparent")
        row.pack(fill="x")

        self.path_entry = ctk.CTkEntry(
            row, height=40, corner_radius=10,
            fg_color=SURFACE, border_color=BORDER, border_width=1,
            text_color=TEXT, font=(FONT_FAMILY, 12), state="readonly",
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._set_path_entry_text(self.download_dir)

        self.browse_btn = ctk.CTkButton(
            row, text="Gözat", width=88, height=40, corner_radius=10,
            fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
            text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13, "bold"), command=self._choose_download_dir,
        )
        self.browse_btn.pack(side="left")

    def _build_download_button(self, parent):
        self.download_btn = ctk.CTkButton(
            parent, text="İndir", command=self._on_download_btn_clicked,
            height=50, corner_radius=12, state="disabled",
            fg_color=SURFACE_3, hover_color=ACCENT_HOVER,
            text_color=TEXT, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.download_btn.pack(fill="x", pady=(0, 14))

    def _build_progress(self, parent):
        self.progress_frame = ctk.CTkFrame(parent, fg_color="transparent")

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
        mapped = bool(self.clear_btn.winfo_ismapped())
        if has_content and not mapped:
            self.clear_btn.place(in_=self.url_entry, relx=1.0, rely=0.5, anchor="e", x=-6)
        elif not has_content and mapped:
            self.clear_btn.place_forget()

    # ------------------------------------------------------------------
    # Download location
    # ------------------------------------------------------------------

    def _set_path_entry_text(self, path):
        self.path_entry.configure(state="normal")
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.path_entry.configure(state="readonly")

    def _choose_download_dir(self):
        chosen = filedialog.askdirectory(
            parent=self,
            initialdir=self.download_dir if os.path.isdir(self.download_dir) else os.path.expanduser("~"),
            mustexist=True,
            title="İndirme klasörünü seçin",
        )
        if chosen:
            self.download_dir = os.path.normpath(chosen)
            self._set_path_entry_text(self.download_dir)
            save_download_dir(self.download_dir)

    # ------------------------------------------------------------------
    # Clear / cancel button
    # ------------------------------------------------------------------

    def _on_clear_clicked(self):
        if self.debounce_job is not None:
            self.after_cancel(self.debounce_job)
            self.debounce_job = None
        self.request_id += 1  # invalidate any in-flight fetch
        self._reset_preview(clear_url=True)

    # ------------------------------------------------------------------
    # URL change / preview fetching
    # ------------------------------------------------------------------

    def _on_url_changed(self, event=None):
        if self.debounce_job is not None:
            self.after_cancel(self.debounce_job)
            self.debounce_job = None

        url = self.url_entry.get().strip()

        if self.current_info is not None:
            self._reset_preview(clear_url=False)

        # Any earlier warning (e.g. "invalid link") is stale the moment the
        # text changes - clear it immediately instead of leaving it stuck
        # until a fresh fetch happens to overwrite it.
        self._set_status("")
        self._update_clear_btn_visibility()

        if not url:
            return

        self.debounce_job = self.after(550, self._try_fetch_preview)

    def _try_fetch_preview(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        if not YOUTUBE_RE.match(url):
            self._set_status("Geçerli bir YouTube bağlantısı girin", ERROR)
            return

        self.request_id += 1
        rid = self.request_id
        self._start_preview_spinner()
        threading.Thread(target=self._fetch_preview_worker, args=(url, rid), daemon=True).start()

    def _fetch_preview_worker(self, url, rid):
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "socket_timeout": 15,
                "retries": 2,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            thumb_img = None
            thumb_url = info.get("thumbnail")
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=12)
                    resp.raise_for_status()
                    thumb_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                except Exception:
                    thumb_img = None

            self.ui_queue.put(("preview_ok", rid, url, info, thumb_img))
        except Exception as exc:
            self.ui_queue.put(("preview_err", rid, friendly_error(exc)))

    def _apply_preview(self, url, info, thumb_img):
        self.current_info = info
        self.current_url = url

        title = info.get("title") or "Bilinmeyen başlık"
        uploader = info.get("uploader") or info.get("channel") or ""
        duration = fmt_duration(info.get("duration"))

        meta_parts = [p for p in (uploader, duration) if p]
        meta_text = "  •  ".join(meta_parts)

        self.title_label.configure(text=title)
        self.meta_label.configure(text=meta_text)

        if thumb_img is not None:
            rounded = make_rounded(thumb_img, (PREVIEW_W, PREVIEW_H), radius=32)
            self._thumb_pil_image = rounded
            self.thumb_ctk_image = ctk.CTkImage(rounded, size=(PREVIEW_W, PREVIEW_H))
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

        if self.format_var.get() == "MP4":
            max_h = _max_available_height(info)
            self.quality_menu.configure(values=_available_quality_options(max_h))
            self.quality_var.set(self._pick_default_quality(max_h))

    def _pick_default_quality(self, max_height):
        target = min(1080, max_height) if max_height else 1080
        for label in QUALITY_OPTIONS:
            if QUALITY_HEIGHTS[label] <= target:
                return label
        return QUALITY_OPTIONS[-1]

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
            self.focus_set()
        self._set_status("")
        self._update_clear_btn_visibility()

    # ------------------------------------------------------------------
    # Preview-loading spinner
    # ------------------------------------------------------------------

    def _start_preview_spinner(self):
        self._preview_spin_angle = 0
        self._show_loading_preview()
        self._tick_preview_spinner()

    def _tick_preview_spinner(self):
        sprite = _spinner_sprite(self._preview_spin_angle)
        self._preview_spinner_img = ctk.CTkImage(sprite, size=sprite.size)
        self.loading_icon_label.configure(image=self._preview_spinner_img, text="")
        self._preview_spin_angle = (self._preview_spin_angle + 18) % 360
        self._preview_spin_job = self.after(70, self._tick_preview_spinner)

    def _stop_preview_spinner(self):
        if self._preview_spin_job is not None:
            self.after_cancel(self._preview_spin_job)
            self._preview_spin_job = None

    # ------------------------------------------------------------------
    # Format change
    # ------------------------------------------------------------------

    def _on_format_changed(self, value):
        if value == "MP3":
            self.quality_title.configure(text="SES KALİTESİ")
            self.quality_menu.configure(values=AUDIO_OPTIONS)
            self.quality_var.set(AUDIO_OPTIONS[1])
        else:
            self.quality_title.configure(text="VİDEO KALİTESİ")
            max_h = _max_available_height(self.current_info) if self.current_info else 0
            self.quality_menu.configure(values=_available_quality_options(max_h))
            self.quality_var.set(self._pick_default_quality(max_h))

    # ------------------------------------------------------------------
    # Processing (post-download) animation
    # ------------------------------------------------------------------

    def _start_processing_animation(self):
        self._processing_active = True
        self._processing_angle = 0
        self._processing_tick_count = 0
        self._processing_dots = 0
        self._processing_base_img = (
            _dim_image(self._thumb_pil_image) if self._thumb_pil_image is not None else None
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
            frame = _compose_spinner_frame(self._processing_base_img, self._processing_angle)
            self._processing_spin_img = ctk.CTkImage(frame, size=(PREVIEW_W, PREVIEW_H))
            self.thumb_label.configure(image=self._processing_spin_img)
            self._processing_angle = (self._processing_angle + 18) % 360

        self._processing_job = self.after(70, self._tick_processing)

    def _stop_processing_animation(self):
        self._processing_active = False
        if self._processing_job is not None:
            self.after_cancel(self._processing_job)
            self._processing_job = None
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self._processing_base_img = None
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
        self.back_btn.configure(state="disabled")

        self.download_btn.configure(
            state="normal", fg_color=SURFACE_2, hover_color=SURFACE_3, text="İptal Et",
        )
        self.url_entry.configure(state="disabled")
        self._set_format_seg_enabled(False)
        self.quality_menu.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")

        self.progress_bar.set(0)
        self.progress_frame.pack(fill="x", pady=(0, 6))
        self._show_progress_message("İndirme başlatılıyor...")

        url = self.current_url
        fmt = self.format_var.get()
        quality = self.quality_var.get()
        download_dir = self.download_dir
        cancel_event = self.cancel_event

        threading.Thread(
            target=self._download_worker,
            args=(url, fmt, quality, download_dir, cancel_event),
            daemon=True,
        ).start()

    def _cancel_download(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.download_btn.configure(state="disabled", fg_color=SURFACE_3, text="İptal ediliyor...")

    def _download_worker(self, url, fmt, quality, download_dir, cancel_event):
        try:
            os.makedirs(download_dir, exist_ok=True)
            outtmpl = os.path.join(download_dir, "%(title).150B [%(id)s].%(ext)s")

            def hook(d):
                if cancel_event.is_set():
                    raise yt_dlp.utils.DownloadCancelled("Kullanıcı tarafından iptal edildi")
                status = d.get("status")
                if status == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    frac = (downloaded / total) if total else 0
                    self.ui_queue.put((
                        "progress", frac,
                        fmt_speed(d.get("speed")),
                        d.get("eta"),
                    ))
                elif status == "finished":
                    self.ui_queue.put(("processing",))

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "noprogress": True,
                "windowsfilenames": True,
                "outtmpl": outtmpl,
                "ffmpeg_location": FFMPEG_PATH,
                "progress_hooks": [hook],
            }

            if fmt == "MP3":
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": AUDIO_BITRATE.get(quality, "192"),
                }]
            else:
                height = QUALITY_HEIGHTS.get(quality, 1080)
                # Prefer m4a/AAC audio explicitly: YouTube's plain "bestaudio"
                # is usually Opus, which many common Windows video players
                # can't decode when it's boxed in an MP4 container, so the
                # merged file plays back with no sound. AAC-in-MP4 is
                # universally supported, so ask for that first and only fall
                # back to whatever audio is available if no m4a track exists.
                ydl_opts["format"] = (
                    f"bestvideo[height<={height}]+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={height}]+bestaudio"
                    f"/best[height<={height}]"
                )
                ydl_opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            self.ui_queue.put(("done",))
        except yt_dlp.utils.DownloadCancelled:
            self.ui_queue.put(("cancelled",))
        except Exception as exc:
            traceback.print_exc()
            self.ui_queue.put(("download_err", friendly_error(exc)))

    # ------------------------------------------------------------------
    # Queue polling / message handling
    # ------------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(60, self._poll_queue)

    def _handle_message(self, msg):
        kind = msg[0]

        if kind == "preview_ok":
            _, rid, url, info, thumb_img = msg
            if rid == self.request_id:
                self._apply_preview(url, info, thumb_img)

        elif kind == "preview_err":
            _, rid, err = msg
            if rid == self.request_id:
                self._show_empty_preview()
                self._set_status(err, ERROR)
                self._update_clear_btn_visibility()

        elif kind == "instagram_post_ok":
            _, rid, loader, post, media, thumbnails = msg
            if rid == self.request_id and self.current_screen == "instagram":
                self._apply_instagram_post(loader, post, media, thumbnails)

        elif kind == "instagram_profile_ok":
            _, rid, loader, profile, avatar = msg
            if rid == self.request_id and self.current_screen == "instagram":
                self._apply_instagram_profile(loader, profile, avatar)

        elif kind == "instagram_err":
            _, rid, err = msg
            if rid == self.request_id and self.current_screen == "instagram":
                self.instagram_mode = None
                self._show_instagram_empty()
                self._set_instagram_status(err, ERROR)
                self.instagram_download_btn.configure(
                    state="disabled",
                    fg_color=SURFACE_3,
                )

        elif kind == "instagram_progress":
            _, text = msg
            if self.current_screen == "instagram":
                self._set_instagram_status(text, TEXT_MUTED)

        elif kind == "instagram_done":
            _, _downloaded = msg
            if self.current_screen == "instagram":
                self._is_downloading = False
                self.cancel_event = None
                self._set_instagram_status("")
                self.instagram_download_btn.configure(
                    state="disabled",
                    text="Tamamlandı",
                    fg_color=SUCCESS,
                )
                self.after(1800, self._finish_instagram_download_ui)

        elif kind == "instagram_cancelled":
            if self.current_screen == "instagram":
                self._set_instagram_status("İndirme iptal edildi", TEXT_MUTED)
                self._restore_instagram_inputs()

        elif kind == "instagram_download_err":
            _, err = msg
            if self.current_screen == "instagram":
                self._set_instagram_status(err, ERROR)
                self._restore_instagram_inputs()

        elif kind == "progress":
            _, frac, speed, eta = msg
            self.progress_bar.set(min(max(frac, 0), 1))
            self._show_progress_info_row()
            self.progress_percent_label.configure(text=f"%{frac * 100:.0f}")
            self.progress_speed_label.configure(text=speed or "")
            self.progress_eta_label.configure(text=f"Kalan: {fmt_eta(eta)}" if eta else "")

        elif kind == "processing":
            self._is_downloading = False
            self.download_btn.configure(state="disabled", fg_color=SURFACE_3, text="İşleniyor...")
            self._show_progress_message("İşleniyor")
            self._start_processing_animation()

        elif kind == "done":
            self._is_downloading = False
            self._stop_processing_animation()
            self.progress_bar.set(1)
            self._show_progress_message("Tamamlandı", SUCCESS)
            self.after(1800, self._finish_download_ui)

        elif kind == "cancelled":
            self._is_downloading = False
            self._stop_processing_animation()
            self.progress_bar.set(0)
            self._show_progress_message("İndirme iptal edildi")
            self._restore_inputs()

        elif kind == "download_err":
            _, err = msg
            self._is_downloading = False
            self._stop_processing_animation()
            self.progress_bar.set(0)
            self._show_progress_message(err, ERROR)
            self._restore_inputs()

    def _finish_download_ui(self):
        self._restore_inputs()
        self.progress_frame.pack_forget()
        self.progress_bar.set(0)
        self.format_var.set("MP4")
        self._on_format_changed("MP4")
        self._reset_preview(clear_url=True)

    def _restore_inputs(self):
        has_preview = self.current_info is not None
        self._is_downloading = False
        self.cancel_event = None
        self._set_cta_enabled(self.download_btn, has_preview, text="İndir")
        self.url_entry.configure(state="normal")
        self._set_format_seg_enabled(has_preview)
        self.quality_menu.configure(state="normal" if has_preview else "disabled")
        self.clear_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        if self.current_screen == "youtube" and self.back_btn.winfo_exists():
            self.back_btn.configure(state="normal")
        self._update_clear_btn_visibility()


def main():
    ctk.set_appearance_mode("dark")
    app = ArnoldDW()
    app.mainloop()


if __name__ == "__main__":
    main()
