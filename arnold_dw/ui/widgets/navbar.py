"""Bottom navigation bar. One `Tab` entry per section; adding a tab is one line in TABS."""

from dataclasses import dataclass

import customtkinter as ctk

from arnold_dw.ui.theme import ACCENT, BG, BORDER, FONT_FAMILY, ICON_FONT, TEXT, TEXT_FAINT, TEXT_MUTED

NAVBAR_HEIGHT = 58


@dataclass(frozen=True)
class Tab:
    screen: str        # screen opened by the tab; screens name their tab via Screen.tab
    label: str
    glyph: str         # Segoe MDL2 Assets code point
    badge: str = ""    # name of an app method returning the count to show (0 hides it)


TABS = (
    Tab("home", "Ana Sayfa", ""),
    Tab("downloads", "İndirmeler", "", badge="active_download_count"),
)


class NavBar(ctk.CTkFrame):
    def __init__(self, app, tabs=TABS):
        super().__init__(app, fg_color=BG, corner_radius=0, height=NAVBAR_HEIGHT)
        self.pack_propagate(False)
        self.app = app
        self.tabs = tuple(tab for tab in tabs if app.has_screen(tab.screen))
        self._active = None
        self._items = {}

        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x", side="top")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True)
        for column, tab in enumerate(self.tabs):
            row.grid_columnconfigure(column, weight=1, uniform="tabs")
            self._items[tab.screen] = self._build_tab(row, column, tab)
        row.grid_rowconfigure(0, weight=1)

    def _build_tab(self, parent, column, tab):
        cell = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, cursor="hand2")
        cell.grid(row=0, column=column, sticky="nsew")
        indicator = ctk.CTkFrame(cell, fg_color="transparent", height=2, width=36, corner_radius=1)
        indicator.place(relx=0.5, y=0, anchor="n")
        inner = ctk.CTkFrame(cell, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        icon = ctk.CTkLabel(inner, text=tab.glyph, font=(ICON_FONT, 17), text_color=TEXT_FAINT, height=20)
        icon.pack()
        label = ctk.CTkLabel(inner, text=tab.label, font=(FONT_FAMILY, 11, "bold"),
                             text_color=TEXT_FAINT, height=16)
        label.pack()
        badge = ctk.CTkLabel(cell, text="", font=(FONT_FAMILY, 10, "bold"), text_color=TEXT,
                             fg_color=ACCENT, corner_radius=8, width=18, height=16)
        item = {"cell": cell, "icon": icon, "label": label, "badge": badge, "indicator": indicator,
                "inner": inner, "hover": False}

        def enter(_event):
            item["hover"] = True
            self._paint(tab.screen)

        def leave(_event):
            item["hover"] = False
            self._paint(tab.screen)

        for widget in (cell, inner, icon, label, badge):
            widget.bind("<Button-1>", lambda _e, name=tab.screen: self._open(name))
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
        return item

    def _open(self, screen):
        self.app.show_screen(screen)

    def set_active(self, tab_screen):
        self._active = tab_screen
        for name in self._items:
            self._paint(name)

    def _paint(self, name):
        item = self._items[name]
        active = name == self._active
        color = TEXT if active else (TEXT_MUTED if item["hover"] else TEXT_FAINT)
        item["icon"].configure(text_color=ACCENT if active else color)
        item["label"].configure(text_color=color)
        item["indicator"].configure(fg_color=ACCENT if active else "transparent")

    def refresh_badges(self):
        for tab in self.tabs:
            if not tab.badge:
                continue
            item = self._items[tab.screen]
            count = getattr(self.app, tab.badge)()
            badge = item["badge"]
            if count:
                badge.configure(text=str(count) if count < 100 else "99+")
                # Pinned to the icon's top-right corner.
                badge.place(in_=item["icon"], relx=1.0, x=-4, y=-6, anchor="nw")
                badge.lift()
            else:
                badge.place_forget()
