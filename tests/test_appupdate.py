import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from arnold_dw.core import appupdate
from arnold_dw.core.appupdate import UpdateCancelled, UpdateValidationError


@pytest.fixture
def http_server():
    class Handler(BaseHTTPRequestHandler):
        payloads = {}

        def do_GET(self):
            response = self.payloads.get(self.path)
            if response is None:
                self.send_error(404)
                return
            content_type, payload = response
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, Handler
    server.shutdown()
    thread.join()
    server.server_close()


def url(server, path):
    return f"http://127.0.0.1:{server.server_port}{path}"


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("2.0.0.dev0", "2.0.0a1", False),
        ("2.0.0", "2.0.0.dev0", True),
        ("2.0.0", "2.0.0rc1", True),
        ("2.0.1", "2.0.0", True),
        ("v2.0.0", "2.0", False),
        ("1!1.0", "999.0", True),
        ("2.0.0.post1", "2.0.0", True),
        ("2.0.0+1", "2.0.0+abc", True),
        ("2.0.0+abc", "2.0.0", True),
    ],
)
def test_pep440_version_order(candidate, current, expected):
    assert appupdate.is_newer(candidate, current) is expected


def test_check_returns_none_for_current_version(http_server):
    server, handler = http_server
    handler.payloads["/latest.json"] = ("application/json", json.dumps({"version": "2.0.0"}).encode())

    assert appupdate.check("2.0.0", url(server, "/latest.json")) is None


def test_check_rejects_malformed_manifest(http_server):
    server, handler = http_server
    handler.payloads["/latest.json"] = ("application/json", b"not json")

    with pytest.raises(UpdateValidationError, match="valid JSON"):
        appupdate.check("1.0", url(server, "/latest.json"))


def test_check_validates_and_returns_update_info(http_server):
    server, handler = http_server
    payload = b"setup bytes"
    handler.payloads["/latest.json"] = (
        "application/json",
        json.dumps(
            {
                "version": "2.1.0",
                "published": "2026-09-28T12:00:00Z",
                "notes": "Bug fixes",
                "assets": {
                    "setup": {
                        "url": url(server, "/setup.exe"),
                        "sha256": hashlib.sha256(payload).hexdigest().upper(),
                        "size": len(payload),
                    }
                },
            }
        ).encode(),
    )

    result = appupdate.check("2.0.0", url(server, "/latest.json"))

    assert result == appupdate.UpdateInfo(
        "2.1.0", "2026-09-28T12:00:00Z", "Bug fixes", url(server, "/setup.exe"), hashlib.sha256(payload).hexdigest(), len(payload)
    )


def test_check_rejects_manifest_missing_setup_asset(http_server):
    server, handler = http_server
    handler.payloads["/latest.json"] = ("application/json", b'{"version":"2.0"}')

    with pytest.raises(UpdateValidationError, match="setup asset"):
        appupdate.check("1.0", url(server, "/latest.json"))


def test_download_verifies_hash_and_reports_progress(http_server, tmp_path):
    server, handler = http_server
    payload = b"verified setup binary"
    handler.payloads["/setup.exe"] = ("application/octet-stream", payload)
    info = appupdate.UpdateInfo("2.0.0", "", "", url(server, "/setup.exe"), hashlib.sha256(payload).hexdigest(), len(payload))
    progress = []

    result = appupdate.download(info, tmp_path, lambda downloaded, size: progress.append((downloaded, size)))

    assert result.read_bytes() == payload
    assert progress[-1] == (len(payload), len(payload))
    assert not result.with_name(result.name + ".part").exists()


def test_download_rejects_hash_mismatch_and_removes_partial_file(http_server, tmp_path):
    server, handler = http_server
    handler.payloads["/setup.exe"] = ("application/octet-stream", b"not the expected setup")
    info = appupdate.UpdateInfo("2.0.0", "", "", url(server, "/setup.exe"), "0" * 64, 100)

    with pytest.raises(UpdateValidationError, match="SHA-256"):
        appupdate.download(info, tmp_path)

    assert not list(tmp_path.iterdir())


def test_download_rejects_size_limit_exceeded(http_server, tmp_path):
    server, handler = http_server
    handler.payloads["/setup.exe"] = ("application/octet-stream", b"x" * 110)
    info = appupdate.UpdateInfo("2.0.0", "", "", url(server, "/setup.exe"), hashlib.sha256(b"x" * 110).hexdigest(), 100)

    with pytest.raises(UpdateValidationError, match="size limit"):
        appupdate.download(info, tmp_path)

    assert not list(tmp_path.iterdir())


def test_download_honors_cancellation(http_server, tmp_path):
    server, handler = http_server
    payload = b"setup"
    handler.payloads["/setup.exe"] = ("application/octet-stream", payload)
    info = appupdate.UpdateInfo("2.0.0", "", "", url(server, "/setup.exe"), hashlib.sha256(payload).hexdigest(), len(payload))
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(UpdateCancelled):
        appupdate.download(info, tmp_path, cancel_event=cancel)

    assert not list(tmp_path.iterdir())
