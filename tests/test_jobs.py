"""DownloadManager state machine: concurrency limit, cancel, retry, failure, events, history."""

import threading
import time

import pytest

from arnold_dw.core import jobs
from arnold_dw.core.errors import DownloadCancelled
from arnold_dw.core.history import History
from arnold_dw.core.jobs import DownloadJob, DownloadManager, Runner, RunResult

TIMEOUT = 5


class Controlled:
    """A runner whose jobs block until the test releases (or fails) them."""

    def __init__(self):
        self.started = []
        self.gates = {}
        self.lock = threading.Lock()

    def gate(self, job_id):
        with self.lock:
            return self.gates.setdefault(job_id, {"go": threading.Event(), "error": None, "result": None})

    def run(self, job, ctx):
        gate = self.gate(job.id)
        with self.lock:
            self.started.append(job.id)
        ctx.progress(downloaded=1, fraction=0.1, stage="İndiriliyor")
        while not gate["go"].wait(0.01):
            if ctx.cancel_event.is_set():
                raise DownloadCancelled()
        if gate["error"] is not None:
            raise gate["error"]
        return gate["result"] or RunResult(files=[])

    def release(self, job_id, error=None, result=None):
        gate = self.gate(job_id)
        gate["error"], gate["result"] = error, result
        gate["go"].set()


def wait_for(predicate, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    raise AssertionError("condition not reached")


@pytest.fixture
def events():
    return []


@pytest.fixture
def runner():
    return Controlled()


@pytest.fixture
def manager(runner, events, tmp_path):
    m = DownloadManager({"fake": Runner(runner.run, lambda exc: f"friendly: {exc}")},
                       on_event=lambda kind, payload: events.append((kind, payload)),
                       max_concurrent=2, progress_interval=0)
    yield m
    m.cancel_all()
    m.wait_idle(TIMEOUT)
    m.close()


def new_job(n=0, **kw):
    return DownloadJob(platform="fake", url=f"https://example.com/{n}", title=f"Job {n}",
                       download_dir="C:\\dl", **kw)


def status(manager, job_id):
    return manager.get(job_id).status


def test_concurrency_limit_queues_the_third_job(manager, runner):
    ids = [manager.enqueue(new_job(i)).id for i in range(3)]
    wait_for(lambda: len(runner.started) == 2)
    time.sleep(0.05)
    assert runner.started == ids[:2]
    assert [status(manager, i) for i in ids] == [jobs.RUNNING, jobs.RUNNING, jobs.QUEUED]
    assert manager.active_count() == 3 and manager.running_count() == 2

    runner.release(ids[0])
    wait_for(lambda: status(manager, ids[2]) == jobs.RUNNING)
    assert status(manager, ids[0]) == jobs.DONE
    assert manager.running_count() == 2


def test_cancel_queued_job_never_starts_it(manager, runner):
    ids = [manager.enqueue(new_job(i)).id for i in range(3)]
    wait_for(lambda: len(runner.started) == 2)
    assert manager.cancel(ids[2]) is True
    assert status(manager, ids[2]) == jobs.CANCELLED
    runner.release(ids[0])
    runner.release(ids[1])
    assert manager.wait_idle(TIMEOUT)
    assert ids[2] not in runner.started


def test_cancel_running_job_stops_it_and_frees_the_slot(manager, runner):
    ids = [manager.enqueue(new_job(i)).id for i in range(3)]
    wait_for(lambda: len(runner.started) == 2)
    assert manager.cancel(ids[0])
    wait_for(lambda: status(manager, ids[0]) == jobs.CANCELLED)
    wait_for(lambda: status(manager, ids[2]) == jobs.RUNNING)


def test_cancel_finished_or_unknown_job_is_a_no_op(manager, runner):
    job_id = manager.enqueue(new_job()).id
    wait_for(lambda: runner.started)
    runner.release(job_id)
    wait_for(lambda: status(manager, job_id) == jobs.DONE)
    assert manager.cancel(job_id) is False
    assert manager.cancel("nope") is False


def test_failure_gets_friendly_error_and_retry_requeues_in_place(manager, runner):
    job_id = manager.enqueue(new_job()).id
    wait_for(lambda: runner.started)
    runner.release(job_id, error=RuntimeError("boom"))
    wait_for(lambda: status(manager, job_id) == jobs.FAILED)
    assert manager.get(job_id).error == "friendly: boom"

    runner.gates.pop(job_id)
    assert manager.retry(job_id) == job_id
    wait_for(lambda: runner.started.count(job_id) == 2)
    job = manager.get(job_id)
    assert job.status == jobs.RUNNING and job.error is None
    runner.release(job_id, result=RunResult(files=["a.mp4"]))
    wait_for(lambda: status(manager, job_id) == jobs.DONE)


def test_retry_of_done_job_creates_a_new_job(manager, runner):
    job_id = manager.enqueue(new_job(options={"format": "MP4"})).id
    wait_for(lambda: runner.started)
    runner.release(job_id)
    wait_for(lambda: status(manager, job_id) == jobs.DONE)
    new_id = manager.retry(job_id)
    assert new_id != job_id
    new = manager.get(new_id)
    assert new.options == {"format": "MP4"} and new.url == manager.get(job_id).url
    assert manager.get(job_id).status == jobs.DONE


def test_retry_of_active_job_is_refused(manager, runner):
    job_id = manager.enqueue(new_job()).id
    assert manager.retry(job_id) is None


def test_exception_after_cancel_counts_as_cancelled(manager, runner):
    job_id = manager.enqueue(new_job()).id
    wait_for(lambda: runner.started)
    manager._cancel[job_id].set()
    runner.release(job_id, error=RuntimeError("socket closed"))
    wait_for(lambda: status(manager, job_id) == jobs.CANCELLED)


def test_success_while_processing_ignores_late_cancel(runner, events):
    gate = threading.Event()

    def run(job, ctx):
        ctx.processing()
        gate.wait(TIMEOUT)
        return RunResult(files=[])

    m = DownloadManager({"fake": Runner(run)}, on_event=lambda *e: events.append(e))
    job_id = m.enqueue(new_job()).id
    wait_for(lambda: m.get(job_id).status == jobs.PROCESSING)
    m.cancel(job_id)
    gate.set()
    wait_for(lambda: m.get(job_id).status == jobs.DONE)
    m.close()


def test_remove_and_clear_finished(manager, runner, events):
    ids = [manager.enqueue(new_job(i)).id for i in range(3)]
    wait_for(lambda: len(runner.started) == 2)
    assert manager.remove(ids[0]) is False  # still running
    runner.release(ids[0])
    runner.release(ids[1])
    # Both were released; wait for both - under load the first may finish after the second.
    wait_for(lambda: status(manager, ids[0]) == jobs.DONE and status(manager, ids[1]) == jobs.DONE)
    assert manager.remove(ids[0]) is True
    assert manager.get(ids[0]) is None
    wait_for(lambda: status(manager, ids[2]) == jobs.RUNNING)
    assert manager.clear_finished() == [ids[1]]
    assert [j.id for j in manager.jobs()] == [ids[2]]
    assert ("removed", [ids[0]]) in events


def test_events_carry_snapshots_not_live_objects(manager, runner, events):
    job = new_job()
    manager.enqueue(job)
    wait_for(lambda: runner.started)
    kinds = [kind for kind, _ in events]
    assert kinds[:2] == ["added", "updated"]
    added = events[0][1]
    assert added is not job and added.status == jobs.QUEUED
    assert any(kind == "progress" and p.progress.fraction == 0.1 for kind, p in events)


def test_progress_events_are_throttled():
    clock = [0.0]
    events = []

    def run(job, ctx):
        for i in range(50):
            ctx.progress(downloaded=i, fraction=i / 100)
        clock[0] += 1.0
        ctx.progress(downloaded=60, fraction=0.6)
        return RunResult(files=[])

    m = DownloadManager({"fake": Runner(run)}, on_event=lambda k, p: events.append(k),
                        progress_interval=0.1, clock=lambda: clock[0])
    m.enqueue(new_job())
    m.wait_idle(TIMEOUT)
    m.close()
    assert events.count("progress") == 2  # first report + the one after the clock moved


def test_latest_and_find_active(manager, runner):
    a = manager.enqueue(new_job(1, options={"q": 1}))
    b = manager.enqueue(new_job(2))
    assert manager.latest().id == b.id
    assert manager.find_active("fake", a.url, {"q": 1}).id == a.id
    assert manager.find_active("fake", a.url, {"q": 2}) is None


def test_unknown_platform_is_rejected(manager):
    with pytest.raises(ValueError):
        manager.enqueue(DownloadJob(platform="nope", url="u", title="t", download_dir="d"))


def test_clamp_concurrency():
    assert jobs.clamp_concurrency(0) == 1
    assert jobs.clamp_concurrency(99) == jobs.MAX_CONCURRENT_LIMIT
    assert jobs.clamp_concurrency("x") == jobs.DEFAULT_MAX_CONCURRENT
    assert jobs.clamp_concurrency(3) == 3


def test_raising_the_limit_starts_queued_jobs(manager, runner):
    ids = [manager.enqueue(new_job(i)).id for i in range(3)]
    wait_for(lambda: len(runner.started) == 2)
    manager.set_max_concurrent(3)
    wait_for(lambda: status(manager, ids[2]) == jobs.RUNNING)


def test_finished_jobs_are_recorded_and_restored(tmp_path, runner):
    history = History(str(tmp_path / "history.db"))
    out = tmp_path / "video.mp4"
    out.write_bytes(b"12345")
    m = DownloadManager({"fake": Runner(runner.run)}, history=history)
    done_id = m.enqueue(new_job(1, options={"format": "MP4"})).id
    failed_id = m.enqueue(new_job(2)).id
    wait_for(lambda: len(runner.started) == 2)
    runner.release(done_id, result=RunResult(files=[str(out)]))
    runner.release(failed_id, error=RuntimeError("x"))
    cancelled_id = m.enqueue(new_job(3)).id
    m.cancel(cancelled_id)
    m.wait_idle(TIMEOUT)
    m.close()

    restored_events = []
    m2 = DownloadManager({"fake": Runner(runner.run)}, history=history,
                         on_event=lambda k, p: restored_events.append((k, p)))
    snaps = m2.load_history()
    by_id = {j.id: j for j in snaps}
    assert set(by_id) == {done_id, failed_id}  # cancelled jobs aren't history
    assert by_id[done_id].status == jobs.DONE and by_id[done_id].files == [str(out)]
    assert by_id[done_id].size == 5 and by_id[done_id].options == {"format": "MP4"}
    assert by_id[failed_id].status == jobs.FAILED and by_id[failed_id].error
    assert restored_events[0][0] == "loaded"
    assert m2.active_count() == 0 and m2.latest() is None

    # Removing drops it from the history too.
    m2.remove(done_id)
    m2.flush()
    assert [j.id for j in history.load()] == [failed_id]
    m2.close()


def test_thumbnail_is_cached_to_disk_and_removed_with_the_job(tmp_path, runner):
    from PIL import Image

    thumbs = tmp_path / "thumbs"
    m = DownloadManager({"fake": Runner(runner.run)}, thumbs_dir=str(thumbs))
    job_id = m.enqueue(new_job(thumbnail_image=Image.new("RGB", (256, 144), "red"))).id
    wait_for(lambda: runner.started)
    runner.release(job_id)
    wait_for(lambda: m.get(job_id).status == jobs.DONE)
    path = m.get(job_id).thumbnail
    assert path and Image.open(path).size == jobs.THUMB_SIZE
    m.remove(job_id)
    m.flush()
    assert not (thumbs / f"{job_id}.png").exists()
    m.close()


def test_close_drops_covers_of_jobs_that_are_not_kept_in_history(tmp_path, runner):
    from PIL import Image

    thumbs = tmp_path / "thumbs"
    m = DownloadManager({"fake": Runner(runner.run)}, history=History(str(tmp_path / "h.db")),
                        thumbs_dir=str(thumbs))
    kept = m.enqueue(new_job(1, thumbnail_image=Image.new("RGB", (8, 8)))).id
    dropped = m.enqueue(new_job(2, thumbnail_image=Image.new("RGB", (8, 8)))).id
    wait_for(lambda: len(runner.started) == 2)
    runner.release(kept)
    m.cancel(dropped)
    m.wait_idle(TIMEOUT)
    m.close()
    assert sorted(p.name for p in thumbs.iterdir()) == [f"{kept}.png"]


def test_snapshot_round_trip_through_record():
    job = new_job(options={"format": "MP3", "quality": "192 kbps"})
    job.status, job.files, job.finished_at = jobs.DONE, ["x.mp3"], 123.0
    back = DownloadJob.from_record(job.to_record())
    assert back.to_record() == job.to_record()
    assert back.progress.fraction == 1.0
