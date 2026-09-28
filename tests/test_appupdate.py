import base64
import hashlib
import json
import threading

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arnold_dw.core import appupdate
from arnold_dw.core.appupdate import UpdateCancelled, UpdateValidationError


class FakeResponse:
    def __init__(self, body, url):
        self.body = body
        self.url = url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount=-1):
        if amount < 0:
            amount = len(self.body) - self.offset
        result = self.body[self.offset:self.offset + amount]
        self.offset += len(result)
        return result


def make_key():
    return Ed25519PrivateKey.generate()


def pubkey(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def envelope(payload, *keys):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {
        "payload": base64.b64encode(canonical).decode(),
        "signatures": [
            {"key_id": key_id, "sig": base64.b64encode(key.sign(canonical)).decode()}
            for key_id, key in keys
        ],
    }


def payload_for(url="https://github.com/release/setup.exe", data=b"setup bytes"):
    return {
        "version": "2.1.0",
        "published": "2026-09-28T12:00:00Z",
        "notes": "Düzeltmeler",
        "assets": {"setup": {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}},
    }


def fake_urlopen(monkeypatch, response):
    monkeypatch.setattr(appupdate.urllib.request, "urlopen", lambda *_args, **_kwargs: response)


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    key = make_key()
    monkeypatch.setattr(appupdate, "TRUSTED_KEYS", {"2026a": pubkey(key)})
    return key


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


def test_verify_manifest_accepts_valid_signature(signing_key):
    payload = payload_for()
    assert appupdate.verify_manifest(envelope(payload, ("2026a", signing_key))) == payload


def test_verify_manifest_rejects_tampered_payload(signing_key):
    wrapper = envelope(payload_for(), ("2026a", signing_key))
    wrapper["payload"] = base64.b64encode(b'{"version":"9.9.9"}').decode()
    with pytest.raises(UpdateValidationError, match="Güncelleme doğrulanamadı"):
        appupdate.verify_manifest(wrapper)


def test_verify_manifest_rejects_wrong_key(signing_key):
    wrong = make_key()
    wrapper = envelope(payload_for(), ("2026a", wrong))
    with pytest.raises(UpdateValidationError, match="signature verification failed"):
        appupdate.verify_manifest(wrapper)


def test_verify_manifest_rejects_unknown_key_id(signing_key):
    wrapper = envelope(payload_for(), ("unknown", signing_key))
    with pytest.raises(UpdateValidationError, match="unknown signing key id"):
        appupdate.verify_manifest(wrapper)


def test_verify_manifest_rejects_old_unsigned_format():
    with pytest.raises(UpdateValidationError, match="signed manifest envelope"):
        appupdate.verify_manifest({"version": "99.0"})


def test_verify_manifest_supports_overlapping_key_rotation(monkeypatch, signing_key):
    next_key = make_key()
    monkeypatch.setitem(appupdate.TRUSTED_KEYS, "2027a", pubkey(next_key))
    wrapper = envelope(payload_for(), ("2026a", signing_key), ("2027a", next_key))
    assert appupdate.verify_manifest(wrapper)["version"] == "2.1.0"


def test_check_returns_none_for_current_version(monkeypatch, signing_key):
    body = json.dumps(envelope({"version": "2.0.0"}, ("2026a", signing_key))).encode()
    fake_urlopen(monkeypatch, FakeResponse(body, "https://updates.test/latest.json"))
    assert appupdate.check("2.0.0", "https://updates.test/latest.json") is None


def test_check_validates_signed_manifest_and_returns_update_info(monkeypatch, signing_key):
    payload = payload_for()
    body = json.dumps(envelope(payload, ("2026a", signing_key))).encode()
    fake_urlopen(monkeypatch, FakeResponse(body, "https://updates.test/latest.json"))
    result = appupdate.check("2.0.0", "https://updates.test/latest.json")
    assert result == appupdate.UpdateInfo(
        "2.1.0", "2026-09-28T12:00:00Z", "Düzeltmeler", payload["assets"]["setup"]["url"],
        hashlib.sha256(b"setup bytes").hexdigest(), len(b"setup bytes"), "updates.test",
    )


def test_check_rejects_insecure_feed_url(monkeypatch):
    with pytest.raises(UpdateValidationError):
        appupdate.check("1.0", "http://updates.test/latest.json")


def test_check_rejects_feed_redirect_to_http_or_untrusted_host(monkeypatch, signing_key):
    body = json.dumps(envelope(payload_for(), ("2026a", signing_key))).encode()
    for final_url in ("http://updates.test/latest.json", "https://evil.test/latest.json"):
        fake_urlopen(monkeypatch, FakeResponse(body, final_url))
        with pytest.raises(UpdateValidationError, match="final feed URL"):
            appupdate.check("1.0", "https://updates.test/latest.json")


def test_check_rejects_asset_with_disallowed_host(monkeypatch, signing_key):
    body = json.dumps(envelope(payload_for("https://evil.test/setup.exe"), ("2026a", signing_key))).encode()
    fake_urlopen(monkeypatch, FakeResponse(body, "https://updates.test/latest.json"))
    with pytest.raises(UpdateValidationError, match="host is not allowed"):
        appupdate.check("1.0", "https://updates.test/latest.json")


def test_download_verifies_hash_size_and_redirect(monkeypatch, tmp_path):
    payload = b"verified setup binary"
    info = appupdate.UpdateInfo(
        "2.0.0", "", "", "https://github.com/release/setup.exe", hashlib.sha256(payload).hexdigest(), len(payload),
    )
    fake_urlopen(monkeypatch, FakeResponse(payload, "https://release-assets.githubusercontent.com/setup.exe"))
    result = appupdate.download(info, tmp_path)
    assert result.read_bytes() == payload


@pytest.mark.parametrize("final_url", ["http://github.com/setup.exe", "https://evil.test/setup.exe"])
def test_download_rejects_unsafe_redirect_and_removes_partial_file(monkeypatch, tmp_path, final_url):
    payload = b"verified setup binary"
    info = appupdate.UpdateInfo("2.0.0", "", "", "https://github.com/setup.exe", hashlib.sha256(payload).hexdigest(), len(payload))
    fake_urlopen(monkeypatch, FakeResponse(payload, final_url))
    with pytest.raises(UpdateValidationError, match="final setup URL"):
        appupdate.download(info, tmp_path)
    assert not list(tmp_path.iterdir())


def test_download_rejects_hash_mismatch(monkeypatch, tmp_path):
    data = b"not expected"
    info = appupdate.UpdateInfo("2.0.0", "", "", "https://github.com/setup.exe", "0" * 64, len(data))
    fake_urlopen(monkeypatch, FakeResponse(data, "https://github.com/setup.exe"))
    with pytest.raises(UpdateValidationError, match="SHA-256"):
        appupdate.download(info, tmp_path)


def test_download_honors_cancellation(monkeypatch, tmp_path):
    cancel = threading.Event()
    cancel.set()
    data = b"setup"
    info = appupdate.UpdateInfo("2.0.0", "", "", "https://github.com/setup.exe", hashlib.sha256(data).hexdigest(), len(data))
    fake_urlopen(monkeypatch, FakeResponse(data, "https://github.com/setup.exe"))
    with pytest.raises(UpdateCancelled):
        appupdate.download(info, tmp_path, cancel_event=cancel)
    assert not list(tmp_path.iterdir())
