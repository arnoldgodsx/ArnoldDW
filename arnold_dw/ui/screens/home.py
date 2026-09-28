"""Home screen: app logo + one card per supported platform."""

from dataclasses import dataclass

import customtkinter as ctk
from PIL import Image

from arnold_dw import APP_NAME, paths
from arnold_dw.config import save_settings
from arnold_dw.core.runtime import autocheck
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    BORDER,
    FONT_FAMILY,
    HOME_CARD,
    SURFACE,
    SURFACE_2,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)

NOTICE_POLL_MS = 1000


@dataclass(frozen=True)
class PlatformCard:
    title: str
    logo_path: str
    screen: str  # name of the screen it opens (see ui.window.SCREENS)


# Only cards whose screen is registered in ui.window.SCREENS are shown: a card that
# opens nothing would be a dead control (TikTok's engine exists, its screen doesn't yet).
PLATFORMS = (
    PlatformCard("YouTube", paths.YOUTUBE_LOGO_PATH, "youtube"),
    PlatformCard("Instagram", paths.INSTAGRAM_LOGO_PATH, "instagram"),
    PlatformCard("TikTok", paths.TIKTOK_LOGO_PATH, "tiktok"),
)


class HomeScreen(Screen):
    name = "home"

    def build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack()
        app_logo = Image.open(paths.APP_LOGO_PATH).convert("RGBA")
        self.app_logo_image = ctk.CTkImage(
            light_image=app_logo,
            dark_image=app_logo,
            size=(86, 86),
        )
        ctk.CTkLabel(header, text="", image=self.app_logo_image).pack()

        ctk.CTkLabel(
            header,
            text=APP_NAME,
            text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 27, "bold"),
        ).pack(pady=(6, 0))

        self.platform_images = {}
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.place(relx=0.5, rely=0.5, anchor="center", relwidth=1)

        available = [p for p in PLATFORMS if self.app.has_screen(p.screen)]
        for index, platform in enumerate(available):
            logo = Image.open(platform.logo_path).convert("RGBA")
            platform_image = ctk.CTkImage(
                light_image=logo,
                dark_image=logo,
                size=(40, 40),
            )
            self.platform_images[platform.title] = platform_image

            command = lambda screen=platform.screen: self.app.show_screen(screen)  # noqa: E731

            card = ctk.CTkButton(
                cards,
                text=platform.title,
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
            card.pack(fill="x", pady=(0, 22 if index < len(available) - 1 else 0))

        self._build_settings_entry()

        # Center the cards in the space left below the header.
        self.update_idletasks()
        header_bottom = header.winfo_y() + header.winfo_height()
        available_bottom = self.winfo_height()
        lower_area_center = (header_bottom + available_bottom) / 2
        cards.place_configure(
            rely=lower_area_center / available_bottom,
            y=0,
        )

    # --- settings entry + engine update notice ----------------------------

    def _build_settings_entry(self):
        # Temporary entry point until the bottom navigation bar lands.
        self.settings_btn = ctk.CTkButton(
            self, text="⚙", width=38, height=38, corner_radius=10,
            border_width=1, border_color=BORDER, fg_color=SURFACE, hover_color=SURFACE_2,
            text_color=TEXT_MUTED, font=("Segoe UI Symbol", 17),
            command=self._open_settings,
        )
        self.settings_btn.place(relx=1.0, y=0, anchor="ne")

        self.notice_btn = ctk.CTkButton(
            self, text="", height=28, corner_radius=8, fg_color="transparent",
            hover_color=SURFACE, text_color=ACCENT, font=(FONT_FAMILY, 12, "bold"),
            command=self._open_settings,
        )
        autocheck.notifier.start(self.app.settings, lambda: save_settings(self.app.settings))
        self._refresh_notice()

    def _open_settings(self):
        if self.app.has_screen("settings"):
            self.app.show_screen("settings")

    def _refresh_notice(self):
        text = autocheck.notifier.notice()
        if text:
            self.notice_btn.configure(text=text)
            self.notice_btn.place(relx=0.5, rely=1.0, anchor="s")
        else:
            self.notice_btn.place_forget()
        if autocheck.notifier.pending:
            self.schedule(NOTICE_POLL_MS, self._refresh_notice)
