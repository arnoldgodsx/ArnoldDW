"""Widgets shared by the platform screens: link input row and save-location picker."""

import os
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from arnold_dw import paths
from arnold_dw.ui.afterjobs import AfterJobsMixin
from arnold_dw.ui.theme import (
    ACCENT,
    BORDER,
    FONT_FAMILY,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)


class InputRow(AfterJobsMixin, ctk.CTkFrame):
    """Back button + link entry with a floating clear button.

    `on_change()` fires on every key release and after a paste; screens
    decide themselves whether the text actually changed.
    """

    def __init__(self, parent, placeholder, on_back, on_change, on_clear):
        super().__init__(parent, fg_color="transparent", height=46)
        self.pack_propagate(False)

        back_icon = Image.open(paths.BACK_ICON_PATH).convert("RGBA")
        self.back_icon_image = ctk.CTkImage(
            light_image=back_icon,
            dark_image=back_icon,
            size=(22, 22),
        )
        self.back_btn = ctk.CTkButton(
            self,
            text="",
            image=self.back_icon_image,
            command=on_back,
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

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            height=46,
            corner_radius=10,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 13),
        )
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<KeyRelease>", lambda e: on_change())
        self.entry.bind("<<Paste>>", lambda e: self.schedule(10, on_change))
        self.entry.bind("<FocusIn>", lambda e: self.entry.configure(border_color=ACCENT))
        self.entry.bind("<FocusOut>", lambda e: self.entry.configure(border_color=BORDER))

        # Clear ("vazgeç") button - floats over the entry's own right edge
        # instead of taking its own column, so the entry spans the full row
        # width and its right edge lines up with the preview card below it.
        self.clear_btn = ctk.CTkButton(
            self, text="✕", width=34, height=34, corner_radius=8,
            fg_color=SURFACE_2, hover_color=SURFACE_3, border_width=0,
            text_color=TEXT_MUTED, text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13), command=on_clear,
        )

    def get(self):
        return self.entry.get()

    def set_clear_visible(self, visible):
        mapped = bool(self.clear_btn.winfo_ismapped())
        if visible and not mapped:
            self.clear_btn.place(in_=self.entry, relx=1.0, rely=0.5, anchor="e", x=-6)
        elif not visible and mapped:
            self.clear_btn.place_forget()

    def set_locked(self, locked):
        """Disable back/entry/clear while a download runs."""
        state = "disabled" if locked else "normal"
        self.back_btn.configure(state=state)
        self.entry.configure(state=state)
        self.clear_btn.configure(state=state)


class SaveLocation(ctk.CTkFrame):
    """"KAYIT KONUMU" label, read-only path field and a folder picker bound to the app setting."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(
            self, text="KAYIT KONUMU", text_color=TEXT_FAINT,
            font=(FONT_FAMILY, 11, "bold"), anchor="w",
        ).pack(fill="x", padx=(8, 0), pady=(0, 6))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")

        self.path_entry = ctk.CTkEntry(
            row, height=40, corner_radius=10,
            fg_color=SURFACE, border_color=BORDER, border_width=1,
            text_color=TEXT, font=(FONT_FAMILY, 12), state="readonly",
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._set_path_entry_text(app.download_dir)

        self.browse_btn = ctk.CTkButton(
            row, text="Gözat", width=88, height=40, corner_radius=10,
            fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
            text_color_disabled=TEXT_FAINT,
            font=(FONT_FAMILY, 13, "bold"), command=self._choose_download_dir,
        )
        self.browse_btn.pack(side="left")

    def set_enabled(self, enabled):
        self.browse_btn.configure(state="normal" if enabled else "disabled")

    def _set_path_entry_text(self, path):
        self.path_entry.configure(state="normal")
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.path_entry.configure(state="readonly")

    def _choose_download_dir(self):
        current = self.app.download_dir
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            initialdir=current if os.path.isdir(current) else os.path.expanduser("~"),
            mustexist=True,
            title="İndirme klasörünü seçin",
        )
        if chosen and self.winfo_exists():
            self.app.set_download_dir(os.path.normpath(chosen))
            self._set_path_entry_text(self.app.download_dir)
