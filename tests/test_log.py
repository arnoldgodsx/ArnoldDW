import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code, appdata):
    env = dict(os.environ, APPDATA=str(appdata))
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)


def test_setup_logging_writes_rotating_file_in_appdata(tmp_path):
    result = _run("""
        import logging, threading
        from logging.handlers import RotatingFileHandler
        from arnold_dw.log import setup_logging, MAX_BYTES, BACKUP_COUNT
        path = setup_logging()
        assert setup_logging() == path  # idempotent
        handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
        assert len(handlers) == 1
        assert handlers[0].maxBytes == MAX_BYTES == 1_000_000 and handlers[0].backupCount == BACKUP_COUNT == 3
        logging.getLogger("arnold_dw.test").info("merhaba dünya")
        def boom():
            raise RuntimeError("worker exploded")
        t = threading.Thread(target=boom); t.start(); t.join()
        print(path)
    """, tmp_path)
    assert result.returncode == 0, result.stderr
    path = result.stdout.strip()
    assert path == os.path.join(str(tmp_path), "Arnold DW", "logs", "arnold_dw.log")
    content = open(path, encoding="utf-8").read()
    assert "merhaba dünya" in content
    assert "worker exploded" in content and "Traceback" in content


def test_setup_logging_survives_unwritable_log_dir(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not a dir")
    result = _run("""
        from arnold_dw.log import setup_logging
        print(setup_logging())
    """, blocker)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None"
