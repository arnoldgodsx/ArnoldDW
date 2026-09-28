import tkinter

import pytest

from arnold_dw.ui.afterjobs import AfterJobsMixin


class JobFrame(AfterJobsMixin, tkinter.Frame):
    pass


@pytest.fixture
def root():
    try:
        tk_root = tkinter.Tk()
    except tkinter.TclError as exc:  # no display
        pytest.skip(f"Tk unavailable: {exc}")
    tk_root.withdraw()
    yield tk_root
    tk_root.destroy()


def _pump(root, ms):
    root.after(ms, root.quit)
    root.mainloop()


def test_scheduled_job_runs_once_and_is_forgotten(root):
    frame = JobFrame(root)
    calls = []
    frame.schedule(1, calls.append, "ran")
    _pump(root, 50)
    assert calls == ["ran"]
    assert frame._after_job_set() == set()


def test_destroy_cancels_pending_jobs(root):
    frame = JobFrame(root)
    calls = []
    frame.schedule(20, calls.append, "should not run")
    frame.schedule(20, calls.append, "nor this")
    frame.destroy()
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(exc)
    _pump(root, 80)
    assert calls == []
    assert errors == []


def test_cancel_job_accepts_none_and_stale_ids(root):
    frame = JobFrame(root)
    assert frame.cancel_job(None) is None
    job = frame.schedule(1, lambda: None)
    _pump(root, 30)
    assert frame.cancel_job(job) is None  # already ran: harmless
