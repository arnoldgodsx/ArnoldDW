import os
import zipfile

from arnold_dw.core import diagnostics


def test_sensitive_values_and_url_queries_are_redacted():
    text = "Cookie: SID=abc; token=xyz https://site.test/watch?v=123&sig=secret"
    scrubbed = diagnostics._mask_text(text, "alice")
    assert "abc" not in scrubbed
    assert "xyz" not in scrubbed
    assert "sig=secret" not in scrubbed
    assert "<redacted>" in scrubbed


def test_cx3_instaloader_sample_and_ytdlp_private_arguments_are_redacted():
    instaloader = (
        r"Instaloader session file: C:\Users\alice\AppData\Local\Instaloader\session-creator_handle"
    )
    yt_dlp = (
        r'yt-dlp --cookies "C:\Users\alice\AppData\Local\browser\cookies.txt" '
        r"--cookies-from-browser chrome:Profile-Private https://example.test/video"
    )
    scrubbed_session = diagnostics._mask_text(instaloader, "alice")
    scrubbed_args = diagnostics._mask_text(yt_dlp, "alice")
    assert r"session-<redacted>" in scrubbed_session
    assert "creator_handle" not in scrubbed_session
    assert "cookies.txt" not in scrubbed_args
    assert "Profile-Private" not in scrubbed_args
    assert scrubbed_args.count("<redacted>") == 2


def test_recent_logs_are_limited_to_five_megabytes(tmp_path):
    older = tmp_path / "older.log"
    newer = tmp_path / "newer.log"
    older.write_bytes(b"x" * (4 * 1024 * 1024))
    newer.write_bytes(b"y" * (4 * 1024 * 1024))

    # Ensure deterministic newest-first ordering.
    os.utime(older, (10, 10))
    os.utime(newer, (20, 20))
    entries = diagnostics._recent_log_bytes([str(older), str(newer)])
    assert sum(map(lambda item: len(item[1]), entries)) <= diagnostics.MAX_LOG_BYTES
    assert entries[0][0] == "newer.log"


def test_build_report_contains_settings_system_and_scrubbed_logs(tmp_path, monkeypatch):
    appdata = tmp_path / "alice" / "Arnold DW"
    log_dir = appdata / "logs"
    log_dir.mkdir(parents=True)
    (appdata / "config.json").write_text(
        '{"download_dir": "C:/Users/alice/Downloads", "token": "secret-value"}',
        encoding="utf-8",
    )
    (log_dir / "app.log").write_text(
        "request https://example.test/?token=secret\nCookie: sessionid=private\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnostics.paths, "log_dir", lambda: str(log_dir))
    monkeypatch.setattr(diagnostics.paths, "config_path", lambda: str(appdata / "config.json"))
    monkeypatch.setattr(diagnostics, "_system_report", lambda username: (b"safe system", str(appdata / "config.json")))
    monkeypatch.setattr(diagnostics.os.path, "expanduser", lambda path: "C:/Users/alice")

    report = diagnostics.build_report(str(tmp_path / "out"))

    assert os.path.basename(report).startswith("ArnoldDW-rapor-")
    with zipfile.ZipFile(report) as archive:
        assert {"system.txt", "settings.json", "logs/app.log"} <= set(archive.namelist())
        settings = archive.read("settings.json").decode()
        logs = archive.read("logs/app.log").decode()
    assert "<user>" in settings
    assert "secret-value" not in settings
    assert "token=secret" not in logs
    assert "private" not in logs
