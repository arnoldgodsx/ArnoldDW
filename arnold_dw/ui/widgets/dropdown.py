"""ThemedDropdown: a CTkOptionMenu look-alike with a custom-drawn popup."""

import time
import tkinter

import customtkinter as ctk

from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    FONT_FAMILY,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)


def set_noactivate(win):
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


def _route_global_click(root, event):
    dropdown = getattr(root, "_open_dropdown", None)
    if dropdown is not None:
        dropdown._on_global_click(event)


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

        self._trace_id = self._variable.trace_add("write", self._sync_label)
        self._apply_state_visual()

    def destroy(self):
        # The variable usually outlives this widget (it belongs to the screen).
        try:
            self._variable.trace_remove("write", self._trace_id)
        except Exception:
            pass
        self._close_popup(force=True)
        super().destroy()

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
        set_noactivate(popup)
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
        # WS_EX_NOACTIVATE (see set_noactivate), so it can never receive
        # keyboard focus - closing is handled entirely by the global click
        # router below, which needs no focus at all.

        self._popup = popup
        self._popup_opened_at = time.monotonic()
        self._watch_global_clicks()

    def _watch_global_clicks(self):
        # The popup closes based on routing every in-app click through here,
        # not on OS focus events (FocusOut proved unreliable - it can fire
        # immediately in some environments, closing the popup before a user
        # could ever click an option). The root-level binding is installed
        # once and forwards to whichever dropdown is open right now, so
        # dropdowns created later (e.g. after a screen change) still work.
        root = self.winfo_toplevel()
        if not getattr(root, "_dropdown_click_watch_installed", False):
            root.bind_all("<Button-1>", lambda e: _route_global_click(root, e), add="+")
            root._dropdown_click_watch_installed = True
        root._open_dropdown = self

    def _on_global_click(self, event):
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
            root = self.winfo_toplevel()
            if getattr(root, "_open_dropdown", None) is self:
                root._open_dropdown = None
        except Exception:
            pass
        try:
            popup.destroy()
        except Exception:
            pass
        if not self._hovering:
            try:
                super().configure(fg_color=SURFACE)
            except Exception:
                pass  # widget is being destroyed

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
