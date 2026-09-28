"""Downloads screen: running/queued jobs on top, finished ones (the history) below.

The screen is persistent (built once, hidden instead of destroyed) and is fed
the manager's job events by the window. A progress event only reconfigures the
one affected row; rows are created, moved or dropped only when a job changes
between active and finished, is added or removed. Finished jobs are shown a
page at a time so a 500-entry history stays light.
"""

import logging
import os
from tkinter import messagebox

import customtkinter as ctk

from arnold_dw import APP_NAME
from arnold_dw.ui import shell
from arnold_dw.ui.screens.base import Screen
from arnold_dw.ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    FONT_FAMILY,
    ICON_FONT,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_FAINT,
    TEXT_MUTED,
)
from arnold_dw.ui.widgets.jobviews import ImageCache, JobRow

log = logging.getLogger(__name__)

PAGE_SIZE = 40
BUILD_CHUNK = 6  # rows created per UI turn; the rest follow on the next turns


class DownloadsScreen(Screen):
    name = "downloads"
    tab = "downloads"
    persistent = True

    def __init__(self, app):
        super().__init__(app)
        self.images = ImageCache()
        self._rows = {}          # job id -> JobRow
        self._jobs = {}          # job id -> latest snapshot
        self._layout = None      # (active ids, finished ids) currently packed
        self._limit = PAGE_SIZE
        self._missing = set()    # finished job ids whose file is gone
        self._build_job = None   # pending schedule() that creates the next chunk of rows

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text="İndirmeler", text_color=TEXT, font=(FONT_FAMILY, 22, "bold"),
                     anchor="w", height=30).pack(fill="x")
        self.summary_label = ctk.CTkLabel(titles, text="", text_color=TEXT_FAINT, font=(FONT_FAMILY, 12),
                                          anchor="w", height=18)
        self.summary_label.pack(fill="x")
        self.clear_btn = ctk.CTkButton(
            header, text="Tamamlananları temizle", command=self._clear_finished, height=30, width=10,
            corner_radius=8, fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT_MUTED,
            font=(FONT_FAMILY, 11, "bold"),
        )

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=SURFACE_2,
                                           scrollbar_button_hover_color=SURFACE_3)
        self.body.pack(fill="both", expand=True)
        self._body_shown = True

        self.active_header = self._section_header("DEVAM EDENLER")
        self.active_list = ctk.CTkFrame(self.body, fg_color="transparent")
        self.finished_header = self._section_header("TAMAMLANANLAR")
        self.finished_list = ctk.CTkFrame(self.body, fg_color="transparent")
        self.more_btn = ctk.CTkButton(
            self.body, text="", command=self._show_more, height=34, corner_radius=8,
            fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT_MUTED, font=(FONT_FAMILY, 12, "bold"),
        )

        self.empty_state = self._build_empty_state()
        self._resync()

    def _section_header(self, text):
        return ctk.CTkLabel(self.body, text=text, text_color=TEXT_FAINT, font=(FONT_FAMILY, 11, "bold"),
                            anchor="w", height=20)

    def _build_empty_state(self):
        empty = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(empty, text="", font=(ICON_FONT, 40), text_color=SURFACE_3).pack()
        ctk.CTkLabel(empty, text="Henüz indirme yok", text_color=TEXT, font=(FONT_FAMILY, 16, "bold")).pack(
            pady=(14, 4))
        ctk.CTkLabel(
            empty, text="Bir YouTube veya Instagram bağlantısı yapıştırıp\n\"İndir\"e bastığınızda burada görünür.",
            text_color=TEXT_FAINT, font=(FONT_FAMILY, 12), justify="center",
        ).pack()
        ctk.CTkButton(
            empty, text="Bağlantı yapıştır", command=lambda: self.app.show_screen("home"), height=38,
            width=170, corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack(pady=(18, 0))
        return empty

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self):
        self._check_files()

    # ------------------------------------------------------------------
    # Job events (from the window, on the UI thread)
    # ------------------------------------------------------------------

    def on_job_event(self, kind, payload):
        if kind in ("removed", "loaded"):
            self._resync()
            if kind == "loaded":
                self._check_files()
            return
        job = payload
        previous = self._jobs.get(job.id)
        self._jobs[job.id] = job
        row = self._rows.get(job.id)
        if previous is None or previous.is_active != job.is_active or (row is None and job.is_active):
            if not job.is_active:
                self._missing.discard(job.id)
            self._resync()
        elif row is not None:
            row.update_job(job)
            if kind != "progress":
                self._update_summary()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _resync(self):
        """Bring the rows in line with the manager's job list.

        At most BUILD_CHUNK new rows are created per call; while rows are
        missing, the list shows the built prefix and the next chunk is
        scheduled, so a long history appears at once and fills in without
        freezing the window.
        """
        self._build_job = self.cancel_job(self._build_job)
        ordered = self.app.downloads.jobs()
        self._jobs = {job.id: job for job in ordered}
        active = [job for job in ordered if job.is_active]
        finished = [job for job in ordered if job.is_finished]
        visible = finished[:self._limit]
        wanted = {job.id: job for job in active + visible}

        for job_id, row in list(self._rows.items()):
            job = wanted.get(job_id)
            if job is None or row.active != job.is_active:
                row.destroy()
                del self._rows[job_id]
                if job is None:
                    self.images.forget(job_id)

        budget = BUILD_CHUNK
        shown = []
        for job in active + visible:
            row = self._rows.get(job.id)
            if row is None:
                if budget == 0:
                    break
                budget -= 1
                parent = self.active_list if job.is_active else self.finished_list
                row = self._rows[job.id] = JobRow(parent, job, self.images, self)
                if job.id in self._missing:
                    row.set_file_exists(False)
            else:
                row.update_job(job)
            shown.append(job)
        pending = len(shown) < len(wanted)
        if pending:
            shown_ids = {job.id for job in shown}
            for job_id, row in self._rows.items():
                if job_id not in shown_ids:
                    row.pack_forget()
            self._build_job = self.schedule(1, self._resync)

        shown_active = [job for job in shown if job.is_active]
        shown_visible = [job for job in shown if not job.is_active]
        layout = ([j.id for j in shown_active], [j.id for j in shown_visible],
                  len(finished) > len(visible), pending)
        if layout != self._layout:
            self._layout = layout
            self._pack_sections(shown_active, shown_visible, len(visible) if pending else len(finished))
        self._update_summary()

    def _pack_sections(self, active, visible, finished_total):
        for widget in (self.active_header, self.active_list, self.finished_header, self.finished_list,
                       self.more_btn):
            widget.pack_forget()
        if not active and not finished_total:
            self.body.pack_forget()
            self._body_shown = False
            self.empty_state.place(relx=0.5, rely=0.45, anchor="center")
            return
        self.empty_state.place_forget()
        if not self._body_shown:
            self._body_shown = True
            self.body.pack(fill="both", expand=True)

        if active:
            self.active_header.pack(fill="x", padx=(4, 0), pady=(0, 6))
            self.active_list.pack(fill="x")
            self._pack_rows(active)
        if visible:
            self.finished_header.pack(fill="x", padx=(4, 0), pady=(14 if active else 0, 6))
            self.finished_list.pack(fill="x")
            self._pack_rows(visible)
        hidden = finished_total - len(visible)
        if hidden > 0:
            self.more_btn.configure(text=f"Daha fazla göster ({hidden})")
            self.more_btn.pack(fill="x", pady=(4, 8))

    def _pack_rows(self, jobs_in_order):
        for job in jobs_in_order:
            self._rows[job.id].pack_forget()
        for job in jobs_in_order:
            self._rows[job.id].pack(fill="x", pady=(0, 8), padx=(0, 4))

    def _update_summary(self):
        active = sum(1 for j in self._jobs.values() if j.is_active)
        finished = len(self._jobs) - active
        parts = []
        if active:
            parts.append(f"{active} devam ediyor")
        if finished:
            parts.append(f"{finished} tamamlanan")
        self.summary_label.configure(text="  ·  ".join(parts) or "Liste boş")
        if finished:
            self.clear_btn.pack(side="right", anchor="n", pady=(4, 0))
        else:
            self.clear_btn.pack_forget()

    def _show_more(self):
        self._limit += PAGE_SIZE
        self._resync()
        self._check_files()

    # ------------------------------------------------------------------
    # File checks (worker thread: the folder may be on a slow drive)
    # ------------------------------------------------------------------

    def _check_files(self):
        # Every listed finished job, including rows still waiting to be built.
        listed = [job for job in self._jobs.values() if job.is_finished][:self._limit]
        targets = [(job.id, job.primary_file) for job in listed if job.primary_file]
        if targets:
            self.start_worker(self._check_files_worker, targets)

    def _check_files_worker(self, targets):
        self.post("files_checked", {job_id: os.path.exists(path) for job_id, path in targets})

    def on_files_checked(self, result):
        for job_id, exists in result.items():
            if exists:
                self._missing.discard(job_id)
            else:
                self._missing.add(job_id)
            row = self._rows.get(job_id)
            if row is not None:
                row.set_file_exists(exists)

    # ------------------------------------------------------------------
    # Row actions (JobRow calls these)
    # ------------------------------------------------------------------

    def cancel(self, job_id):
        self.app.downloads.cancel(job_id)

    def retry(self, job_id):
        self._missing.discard(job_id)
        self.app.downloads.retry(job_id)

    def remove(self, job_id):
        self._missing.discard(job_id)
        self.app.downloads.remove(job_id)

    def open(self, job_id):
        job = self._jobs.get(job_id)
        if job is not None and not shell.open_file(job.primary_file):
            self.on_files_checked({job_id: False})

    def reveal(self, job_id):
        job = self._jobs.get(job_id)
        if job is not None:
            shell.show_in_folder(job.primary_file)

    def _clear_finished(self):
        if not messagebox.askyesno(
            APP_NAME, "Tamamlanan indirmeler listeden kaldırılsın mı?\nİndirilen dosyalar silinmez.",
            parent=self.winfo_toplevel(),
        ):
            return
        self._missing.clear()
        self._limit = PAGE_SIZE
        self.app.downloads.clear_finished()
