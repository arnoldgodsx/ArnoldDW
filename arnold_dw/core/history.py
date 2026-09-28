"""Persistent download history: finished and failed jobs in SQLite (%APPDATA%\\Arnold DW\\history.db).

Every call opens its own short-lived connection, so the store can be used from
any thread. A database that can't be read (corrupt file, not a database) is
moved aside to `history.db.corrupt` and started fresh - losing the history is
better than an app that won't start. Only the newest `max_entries` are kept.
"""

import json
import logging
import os
import sqlite3
from contextlib import closing

from arnold_dw import paths
from arnold_dw.core.jobs import DownloadJob

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MAX_ENTRIES = 500

_COLUMNS = (
    "id", "platform", "url", "title", "download_dir", "options", "thumbnail", "status",
    "files", "already_existed", "size", "error", "created_at", "finished_at",
)
_JSON_COLUMNS = ("options", "files")

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS downloads (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    download_dir TEXT NOT NULL DEFAULT '',
    options TEXT NOT NULL DEFAULT '{}',
    thumbnail TEXT,
    status TEXT NOT NULL,
    files TEXT NOT NULL DEFAULT '[]',
    already_existed INTEGER NOT NULL DEFAULT 0,
    size INTEGER,
    error TEXT,
    created_at REAL NOT NULL DEFAULT 0,
    finished_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS downloads_finished_at ON downloads (finished_at DESC);
"""


class History:
    def __init__(self, path=None, max_entries=MAX_ENTRIES):
        self.path = path or paths.history_path()
        self.max_entries = max_entries

    # --- public API -------------------------------------------------------

    def record(self, job):
        """Insert or update a finished job, then trim to `max_entries`.

        Returns the cover-image paths of the entries trimmed away (the caller
        deletes those files).
        """
        row = _to_row(job)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        sql = f"INSERT OR REPLACE INTO downloads ({', '.join(_COLUMNS)}) VALUES ({placeholders})"

        def op(conn):
            conn.execute(sql, [row[c] for c in _COLUMNS])
            return self._prune(conn)

        return self._run(op, default=[])

    def load(self, limit=None):
        """Newest first, as finished DownloadJob objects."""
        limit = self.max_entries if limit is None else limit

        def op(conn):
            cursor = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM downloads ORDER BY finished_at DESC LIMIT ?", (limit,))
            jobs = []
            for values in cursor.fetchall():
                job = _from_row(dict(zip(_COLUMNS, values, strict=True)))
                if job is not None:
                    jobs.append(job)
            return jobs

        return self._run(op, default=[])

    def delete(self, job_ids):
        ids = list(job_ids)

        def op(conn):
            conn.executemany("DELETE FROM downloads WHERE id = ?", [(i,) for i in ids])

        self._run(op)

    def clear(self):
        self._run(lambda conn: conn.execute("DELETE FROM downloads"))

    def count(self):
        return self._run(lambda conn: conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0], default=0)

    # --- internals --------------------------------------------------------

    def _prune(self, conn):
        stale = conn.execute(
            "SELECT id, thumbnail FROM downloads ORDER BY finished_at DESC LIMIT -1 OFFSET ?",
            (self.max_entries,),
        ).fetchall()
        if not stale:
            return []
        conn.executemany("DELETE FROM downloads WHERE id = ?", [(row[0],) for row in stale])
        return [row[1] for row in stale if row[1]]

    def _run(self, op, default=None):
        for attempt in (1, 2):
            try:
                with closing(self._connect()) as conn:
                    with conn:  # commit / rollback
                        return op(conn)
            except sqlite3.DatabaseError as exc:
                if attempt == 1 and _is_corruption(exc):
                    log.error("History database %s is unreadable (%s); starting a new one", self.path, exc)
                    self._move_aside()
                    continue
                log.exception("History operation failed")
                return default
            except OSError:
                log.exception("History database %s is not accessible", self.path)
                return default
        return default

    def _connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                self._migrate(conn, version)
            elif version > SCHEMA_VERSION:
                log.warning("History schema %s is newer than supported %s; using known columns",
                            version, SCHEMA_VERSION)
        except BaseException:
            conn.close()
            raise
        return conn

    def _migrate(self, conn, version):
        with conn:
            if version < 1:
                conn.executescript(_SCHEMA_V1)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _move_aside(self):
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass
        try:
            os.replace(self.path, self.path + ".corrupt")
        except OSError:
            try:
                os.remove(self.path)
            except OSError:
                log.exception("Could not move the broken history database aside")


def _is_corruption(exc):
    low = str(exc).lower()
    return "not a database" in low or "malformed" in low or "corrupt" in low or "no such table" in low


def _to_row(job):
    record = job.to_record()
    row = {c: record.get(c) for c in _COLUMNS}
    for column in _JSON_COLUMNS:
        row[column] = json.dumps(row[column] or ({} if column == "options" else []), ensure_ascii=False)
    row["already_existed"] = int(bool(row["already_existed"]))
    row["title"] = row["title"] or ""
    row["download_dir"] = row["download_dir"] or ""
    row["created_at"] = row["created_at"] or 0.0
    row["finished_at"] = row["finished_at"] or 0.0
    return row


def _from_row(row):
    try:
        for column in _JSON_COLUMNS:
            row[column] = json.loads(row[column]) if row[column] else None
        return DownloadJob.from_record(row)
    except (ValueError, TypeError, KeyError):
        log.warning("Skipping unreadable history entry %r", row.get("id"))
        return None
