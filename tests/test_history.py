"""History store: versioned schema, entry limit, corrupt file recovery."""

import sqlite3

import pytest

from arnold_dw.core import history as history_mod
from arnold_dw.core import jobs
from arnold_dw.core.history import History
from arnold_dw.core.jobs import DownloadJob


def finished(n, status=jobs.DONE, thumbnail=None):
    job = DownloadJob(platform="youtube", url=f"https://youtu.be/{n}", title=f"Video {n}",
                      download_dir="C:\\dl", options={"format": "MP4", "quality": "720p"},
                      thumbnail=thumbnail)
    job.status = status
    job.files = [f"C:\\dl\\Video {n}.mp4"] if status == jobs.DONE else []
    job.error = "Bağlantı hatası" if status == jobs.FAILED else None
    job.created_at = 1000.0 + n
    job.finished_at = 2000.0 + n
    return job


@pytest.fixture
def store(tmp_path):
    return History(str(tmp_path / "sub" / "history.db"))


def test_new_database_gets_the_current_schema_version(store):
    assert store.count() == 0
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == history_mod.SCHEMA_VERSION
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "downloads" in tables


def test_record_and_load_round_trip_newest_first(store):
    for n in range(3):
        store.record(finished(n))
    store.record(finished(9, status=jobs.FAILED))
    loaded = store.load()
    assert [j.title for j in loaded] == ["Video 9", "Video 2", "Video 1", "Video 0"]
    failed, done = loaded[0], loaded[1]
    assert failed.status == jobs.FAILED and failed.error == "Bağlantı hatası" and failed.files == []
    assert done.status == jobs.DONE and done.files == ["C:\\dl\\Video 2.mp4"]
    assert done.options == {"format": "MP4", "quality": "720p"}
    assert [j.title for j in store.load(limit=2)] == ["Video 9", "Video 2"]


def test_record_again_replaces_the_entry(store):
    job = finished(1)
    store.record(job)
    job.title = "Yeni başlık"
    store.record(job)
    assert store.count() == 1 and store.load()[0].title == "Yeni başlık"


def test_only_the_newest_entries_are_kept_and_pruned_thumbnails_returned(tmp_path):
    store = History(str(tmp_path / "h.db"), max_entries=3)
    pruned = []
    for n in range(5):
        pruned += store.record(finished(n, thumbnail=f"thumb{n}.png"))
    assert store.count() == 3
    assert [j.title for j in store.load()] == ["Video 4", "Video 3", "Video 2"]
    assert sorted(pruned) == ["thumb0.png", "thumb1.png"]


def test_default_limit_is_500(tmp_path):
    store = History(str(tmp_path / "h.db"))
    assert store.max_entries == 500
    for n in range(505):
        store.record(finished(n))
    assert store.count() == 500
    assert store.load()[-1].title == "Video 5"


def test_delete_and_clear(store):
    entries = [finished(n) for n in range(3)]
    for job in entries:
        store.record(job)
    store.delete([entries[0].id, "unknown"])
    assert {j.id for j in store.load()} == {entries[1].id, entries[2].id}
    store.clear()
    assert store.count() == 0


def test_corrupt_file_is_moved_aside_and_recreated(tmp_path):
    path = tmp_path / "history.db"
    path.write_bytes(b"this is not a sqlite database at all" * 100)
    store = History(str(path))
    assert store.load() == []
    store.record(finished(1))
    assert store.count() == 1
    assert (tmp_path / "history.db.corrupt").read_bytes().startswith(b"this is not")


def test_missing_table_with_current_version_is_recreated(tmp_path):
    path = tmp_path / "history.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {history_mod.SCHEMA_VERSION}")
    conn.close()
    store = History(str(path))
    store.record(finished(1))
    assert store.count() == 1


def test_unreadable_rows_are_skipped(store):
    store.record(finished(1))
    store.record(finished(2))
    conn = sqlite3.connect(store.path)
    with conn:
        conn.execute("UPDATE downloads SET options = '{broken' WHERE title = 'Video 1'")
    conn.close()
    assert [j.title for j in store.load()] == ["Video 2"]
