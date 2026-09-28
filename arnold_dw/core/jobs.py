"""Download jobs and the manager that queues and runs them (UI-independent, no tkinter).

A platform plugs in by registering a `Runner` under its name: `run(job, ctx)`
does the blocking download in a worker thread, reports progress through the
`JobContext`, honours `ctx.cancel_event` by raising DownloadCancelled, and
returns a `RunResult`. Everything else - the queue, the concurrency limit,
cancel/retry, persistence to the history and the event stream - lives here.

The manager reports every change through one callback, `on_event(kind,
payload)`, called from whichever thread made the change (the UI forwards it to
its own queue). Payloads are snapshots (copies) of jobs, never the live objects:

    "added"    snapshot        a new job was queued
    "updated"  snapshot        status / result changed
    "progress" snapshot        progress changed (throttled per job)
    "removed"  [job ids]       jobs left the list (remove / clear_finished)
    "loaded"   [snapshots]     finished jobs restored from the history
"""

import copy
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from arnold_dw.core import errors
from arnold_dw.core.errors import DownloadCancelled

log = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

ACTIVE_STATES = frozenset({QUEUED, RUNNING, PROCESSING})
FINISHED_STATES = frozenset({DONE, FAILED, CANCELLED})
# Only these reach the history; a cancelled job is a non-event once the app closes.
RECORDED_STATES = frozenset({DONE, FAILED})

DEFAULT_MAX_CONCURRENT = 2
MAX_CONCURRENT_LIMIT = 5
CANCELLING = "İptal ediliyor..."  # progress.stage of a running job asked to stop
PROGRESS_INTERVAL = 0.1  # seconds: at most ~10 progress events per job per second
THUMB_SIZE = (128, 72)   # stored cover size (shown at half size, crisp on HiDPI)


def clamp_concurrency(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONCURRENT
    return min(max(value, 1), MAX_CONCURRENT_LIMIT)


@dataclass
class Progress:
    downloaded: int = 0        # bytes so far (all streams of the job)
    total: object = None       # int | None
    fraction: object = None    # float in [0, 1] | None when unknown
    speed: object = None       # bytes/s | None
    eta: object = None         # seconds | None
    stage: str = ""            # short user-facing text ("Hazırlanıyor", "2/5 indiriliyor...")


@dataclass
class RunResult:
    files: list                    # every output file of the job (new or pre-existing)
    already_existed: bool = False  # nothing new was written: the files were already there


@dataclass(frozen=True)
class Runner:
    run: Callable                                   # run(job, ctx) -> RunResult
    friendly_error: Callable = errors.friendly_error  # exception -> Turkish message


@dataclass
class DownloadJob:
    platform: str
    url: str
    title: str
    download_dir: str
    options: dict = field(default_factory=dict)  # platform specific, JSON-serializable
    thumbnail: object = None                     # local cached cover path | None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = QUEUED
    progress: Progress = field(default_factory=Progress)
    files: list = field(default_factory=list)
    already_existed: bool = False
    size: object = None                          # bytes of the output files | None
    error: object = None                         # user-facing message | None
    created_at: float = field(default_factory=time.time)
    started_at: object = None
    finished_at: object = None
    # Runtime only (never persisted): the resolved object a runner can reuse to
    # skip a second lookup, and the cover as a PIL image.
    context: object = field(default=None, repr=False, compare=False)
    thumbnail_image: object = field(default=None, repr=False, compare=False)

    @property
    def is_active(self):
        return self.status in ACTIVE_STATES

    @property
    def is_finished(self):
        return self.status in FINISHED_STATES

    @property
    def primary_file(self):
        return self.files[0] if self.files else None

    def snapshot(self):
        """A copy safe to hand to another thread (shares only the immutable-by-contract image/context)."""
        snap = copy.copy(self)
        snap.progress = copy.copy(self.progress)
        snap.files = list(self.files)
        snap.options = copy.deepcopy(self.options)
        return snap

    def to_record(self):
        return {
            "id": self.id, "platform": self.platform, "url": self.url, "title": self.title,
            "download_dir": self.download_dir, "options": self.options, "thumbnail": self.thumbnail,
            "status": self.status, "files": self.files, "already_existed": self.already_existed,
            "size": self.size, "error": self.error, "created_at": self.created_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_record(cls, record):
        job = cls(
            platform=record["platform"], url=record["url"], title=record.get("title") or "",
            download_dir=record.get("download_dir") or "", options=dict(record.get("options") or {}),
            thumbnail=record.get("thumbnail"), id=record["id"], status=record["status"],
            files=list(record.get("files") or []), already_existed=bool(record.get("already_existed")),
            size=record.get("size"), error=record.get("error"),
            created_at=record.get("created_at") or 0.0, finished_at=record.get("finished_at"),
        )
        if job.status == DONE:
            job.progress.fraction = 1.0
        return job

    def clone_for_rerun(self):
        """A fresh queued job with the same source and options (used for "download again")."""
        return DownloadJob(
            platform=self.platform, url=self.url, title=self.title, download_dir=self.download_dir,
            options=copy.deepcopy(self.options), thumbnail=self.thumbnail,
            context=self.context, thumbnail_image=self.thumbnail_image,
        )


class JobContext:
    """What a runner gets besides the job: the cancel flag and progress reporting."""

    def __init__(self, manager, job, cancel_event):
        self._manager = manager
        self.job = job
        self.cancel_event = cancel_event

    def progress(self, downloaded=0, total=None, fraction=None, speed=None, eta=None, stage=None):
        self._manager._report_progress(self.job, Progress(
            downloaded=downloaded or 0, total=total, fraction=fraction, speed=speed, eta=eta,
            stage=stage if stage is not None else self.job.progress.stage,
        ))

    def processing(self, stage="İşleniyor"):
        """Post-processing started: the job can't be cancelled any more."""
        self._manager._set_processing(self.job, stage)

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise DownloadCancelled()


class DownloadManager:
    def __init__(self, runners, on_event=None, max_concurrent=DEFAULT_MAX_CONCURRENT,
                 history=None, thumbs_dir=None, progress_interval=PROGRESS_INTERVAL,
                 clock=time.monotonic):
        self._runners = dict(runners)
        self._on_event = on_event or (lambda kind, payload: None)
        self._max = clamp_concurrency(max_concurrent)
        self._history = history
        self._thumbs_dir = thumbs_dir
        self._interval = progress_interval
        self._clock = clock
        self._lock = threading.RLock()
        self._jobs = {}           # id -> DownloadJob (the live objects)
        self._seq = {}            # id -> queue position of active jobs
        self._next_seq = 0
        self._cancel = {}         # id -> threading.Event of running jobs
        self._threads = {}        # id -> worker thread
        self._last_emit = {}      # id -> clock() of the last progress event
        self._latest_id = None    # most recently enqueued job of this session
        # One thread does all history/disk bookkeeping, in order, off the UI thread.
        self._io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jobs-io")
        self._closed = False

    # ------------------------------------------------------------------
    # Queries (thread-safe; return snapshots)
    # ------------------------------------------------------------------

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job is not None else None

    def jobs(self):
        """Active jobs in queue order, then finished ones newest first."""
        with self._lock:
            active = sorted((j for j in self._jobs.values() if j.is_active), key=lambda j: self._seq[j.id])
            finished = sorted((j for j in self._jobs.values() if j.is_finished),
                              key=lambda j: j.finished_at or 0, reverse=True)
            return [j.snapshot() for j in active + finished]

    def active_count(self):
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.is_active)

    def running_count(self):
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in (RUNNING, PROCESSING))

    def latest(self):
        """The job enqueued last in this session (history entries don't count)."""
        return self.get(self._latest_id) if self._latest_id else None

    def find_active(self, platform, url, options):
        with self._lock:
            for job in self._jobs.values():
                if job.is_active and job.platform == platform and job.url == url and job.options == options:
                    return job.snapshot()
        return None

    @property
    def max_concurrent(self):
        return self._max

    def set_max_concurrent(self, value):
        with self._lock:
            self._max = clamp_concurrency(value)
        self._pump()

    def has_runner(self, platform):
        return platform in self._runners

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def enqueue(self, job):
        if job.platform not in self._runners:
            raise ValueError(f"No runner registered for platform {job.platform!r}")
        with self._lock:
            job.status = QUEUED
            self._jobs[job.id] = job
            self._seq[job.id] = self._take_seq()
            self._latest_id = job.id
            snap = job.snapshot()
        log.info("Job queued %s: %s %s %s", job.id[:8], job.platform, job.url, job.options)
        self._emit("added", snap)
        self._pump()
        return snap

    def cancel(self, job_id):
        """Cancel a queued job at once, or ask a running one to stop. Returns True if acted on."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.is_active:
                return False
            if job.status == QUEUED:
                self._finish_locked(job, CANCELLED)
                snap = job.snapshot()
            else:
                event = self._cancel.get(job_id)
                if event is not None:
                    event.set()
                job.progress.stage = CANCELLING
                snap = None
        if snap is not None:
            self._emit("updated", snap)
        else:
            self._emit("progress", self.get(job_id))
        return True

    def cancel_all(self):
        with self._lock:
            ids = [j.id for j in self._jobs.values() if j.is_active]
        # Queued ones first, so none of them gets started when a running one stops.
        ids.sort(key=lambda i: self._jobs[i].status != QUEUED)
        for job_id in ids:
            self.cancel(job_id)
        return len(ids)

    def retry(self, job_id):
        """Failed/cancelled -> re-queued in place; done -> a new job with the same options.

        Returns the id of the queued job, or None.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.is_finished:
                return None
            if job.status == DONE:
                new_job = job.clone_for_rerun()
            else:
                job.status = QUEUED
                job.progress = Progress()
                job.files = []
                job.already_existed = False
                job.size = None
                job.error = None
                job.started_at = job.finished_at = None
                self._seq[job.id] = self._take_seq()
                self._latest_id = job.id
                snap = job.snapshot()
                new_job = None
        if new_job is not None:
            return self.enqueue(new_job).id
        self._emit("updated", snap)
        self._pump()
        return job_id

    def remove(self, job_id):
        """Drop a finished job from the list and the history."""
        return bool(self._remove([job_id]))

    def clear_finished(self):
        with self._lock:
            ids = [j.id for j in self._jobs.values() if j.is_finished]
        return self._remove(ids)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def load_history(self, limit=None):
        """Restore finished jobs from the history (blocking disk I/O: call from a worker)."""
        if self._history is None:
            return []
        records = self._history.load(limit)
        restored = []
        with self._lock:
            for record in records:
                if record.id in self._jobs:
                    continue
                self._jobs[record.id] = record
                restored.append(record)
        for job in restored:
            job.thumbnail_image = _load_thumbnail(job.thumbnail)
        self._cleanup_orphan_thumbnails()
        snaps = [j.snapshot() for j in restored]
        self._emit("loaded", snaps)
        return snaps

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def threads(self):
        with self._lock:
            return [t for t in self._threads.values() if t.is_alive()]

    def wait_idle(self, timeout=None):
        """Block until no job is running (tests / shutdown). Returns True if idle."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            threads = self.threads()
            if not threads:
                return True
            for thread in threads:
                remaining = None if deadline is None else max(deadline - time.monotonic(), 0)
                thread.join(remaining)
            if deadline is not None and time.monotonic() >= deadline:
                return not self.threads()

    def flush(self):
        """Wait until pending history writes are on disk."""
        if not self._closed:
            self._io.submit(lambda: None).result()

    def close(self):
        """Finish pending history writes; call once no job runs any more."""
        if not self._closed:
            self._closed = True
            self._io.shutdown(wait=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _take_seq(self):
        self._next_seq += 1
        return self._next_seq

    def _emit(self, kind, payload):
        try:
            self._on_event(kind, payload)
        except Exception:
            log.exception("Job event handler failed for %s", kind)

    def _submit_io(self, fn, *args):
        if self._closed:
            return
        try:
            future = self._io.submit(fn, *args)
        except RuntimeError:  # closed meanwhile (app exit while a worker was finishing)
            return
        future.add_done_callback(
            lambda f: f.exception() and log.error("Job I/O task failed", exc_info=f.exception()))

    def _pump(self):
        """Start queued jobs while there's a free slot."""
        started = []
        with self._lock:
            running = sum(1 for j in self._jobs.values() if j.status in (RUNNING, PROCESSING))
            queued = sorted((j for j in self._jobs.values() if j.status == QUEUED),
                            key=lambda j: self._seq[j.id])
            for job in queued[:max(self._max - running, 0)]:
                job.status = RUNNING
                job.started_at = time.time()
                job.progress = Progress(stage="Hazırlanıyor")
                cancel_event = threading.Event()
                self._cancel[job.id] = cancel_event
                thread = threading.Thread(target=self._run, args=(job, cancel_event), daemon=True,
                                          name=f"job-{job.platform}-{job.id[:8]}")
                self._threads[job.id] = thread
                started.append((thread, job.snapshot()))
        for thread, snap in started:
            self._emit("updated", snap)
            thread.start()

    def _run(self, job, cancel_event):
        runner = self._runners[job.platform]
        ctx = JobContext(self, job, cancel_event)
        try:
            if job.thumbnail is None and job.thumbnail_image is not None:
                job.thumbnail = self._save_thumbnail(job)
            result = runner.run(job, ctx)
        except DownloadCancelled:
            self._finish(job, CANCELLED)
        except Exception as exc:
            if cancel_event.is_set() and job.status != PROCESSING:
                self._finish(job, CANCELLED)
            else:
                log.exception("Job %s (%s %s) failed", job.id[:8], job.platform, job.url)
                self._finish(job, FAILED, error=runner.friendly_error(exc))
        else:
            self._finish(job, DONE, result=result)
        finally:
            with self._lock:
                self._cancel.pop(job.id, None)
                self._threads.pop(job.id, None)
                self._last_emit.pop(job.id, None)
            self._pump()

    def _finish(self, job, status, result=None, error=None):
        with self._lock:
            if job.id not in self._jobs:
                return
            self._finish_locked(job, status, result, error)
            snap = job.snapshot()
        log.info("Job %s %s%s", job.id[:8], status, f": {error}" if error else "")
        self._emit("updated", snap)
        if status in RECORDED_STATES and self._history is not None:
            self._submit_io(self._record, snap)

    def _finish_locked(self, job, status, result=None, error=None):
        job.status = status
        job.finished_at = time.time()
        job.error = error
        if result is not None:
            job.files = list(result.files)
            job.already_existed = bool(result.already_existed)
            job.size = _total_size(job.files)
        if status == DONE:
            job.progress.fraction = 1.0
            job.progress.stage = ""
        self._seq.pop(job.id, None)

    def _record(self, snap):
        pruned = self._history.record(snap)
        for path in pruned:
            _remove_file(path)

    def _remove(self, ids):
        removed, thumbs = [], []
        with self._lock:
            for job_id in ids:
                job = self._jobs.get(job_id)
                if job is None or not job.is_finished:
                    continue
                del self._jobs[job_id]
                removed.append(job_id)
                if job.thumbnail and not self._thumbnail_in_use(job.thumbnail):
                    thumbs.append(job.thumbnail)
            if self._latest_id in removed:
                self._latest_id = None
        if removed:
            self._emit("removed", removed)
            if self._history is not None:
                self._submit_io(self._history.delete, removed)
            for path in thumbs:
                self._submit_io(_remove_file, path)
        return removed

    def _thumbnail_in_use(self, path):
        return any(j.thumbnail == path for j in self._jobs.values())

    def _report_progress(self, job, progress):
        now = self._clock()
        with self._lock:
            if job.status != RUNNING:
                return
            if job.progress.stage == CANCELLING:
                progress.stage = CANCELLING
            job.progress = progress
            last = self._last_emit.get(job.id)
            due = last is None or now - last >= self._interval or progress.fraction == 1.0
            if due:
                self._last_emit[job.id] = now
                snap = job.snapshot()
        if due:
            self._emit("progress", snap)

    def _set_processing(self, job, stage):
        with self._lock:
            if job.status != RUNNING:
                return
            job.status = PROCESSING
            job.progress.stage = stage
            job.progress.speed = job.progress.eta = None
            snap = job.snapshot()
        self._emit("updated", snap)

    def _save_thumbnail(self, job):
        if not self._thumbs_dir:
            return None
        try:
            os.makedirs(self._thumbs_dir, exist_ok=True)
            path = os.path.join(self._thumbs_dir, f"{job.id}.png")
            image = job.thumbnail_image.copy()
            image.thumbnail(THUMB_SIZE)
            image.save(path, "PNG")
            return path
        except Exception:
            log.warning("Could not cache the cover of job %s", job.id[:8], exc_info=True)
            return None

    def _cleanup_orphan_thumbnails(self, min_age=24 * 3600):
        """Delete cached covers no job references any more (older than a day, so never a fresh one)."""
        if not self._thumbs_dir or not os.path.isdir(self._thumbs_dir):
            return
        with self._lock:
            used = {os.path.normcase(os.path.abspath(j.thumbnail)) for j in self._jobs.values() if j.thumbnail}
        cutoff = time.time() - min_age
        for name in os.listdir(self._thumbs_dir):
            path = os.path.join(self._thumbs_dir, name)
            try:
                if os.path.normcase(os.path.abspath(path)) not in used and os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass


def files_exist(job):
    """Does the (primary) output of a finished job still exist on disk?"""
    return bool(job.files) and os.path.exists(job.files[0])


def _total_size(files):
    total = 0
    for path in files:
        try:
            total += os.path.getsize(path)
        except OSError:
            pass
    return total or None


def _load_thumbnail(path):
    if not path:
        return None
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            return image.copy()
    except Exception:
        return None


def _remove_file(path):
    try:
        os.remove(path)
    except OSError:
        pass
