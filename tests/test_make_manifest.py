import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.make_manifest import KEY_ID, load_release_key, make_manifest


def test_make_manifest_includes_signed_installer_size_and_hash(tmp_path):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"fake installer bytes")
    key = Ed25519PrivateKey.generate()
    manifest = make_manifest(setup, "2.1.0", "2026-09-28T00:00:00Z", "Release notes", "https://host/setup.exe", key)

    payload_bytes = base64.b64decode(manifest["payload"], validate=True)
    payload = json.loads(payload_bytes)
    key.public_key().verify(base64.b64decode(manifest["signatures"][0]["sig"]), payload_bytes)
    assert manifest["signatures"][0]["key_id"] == KEY_ID
    assert payload_bytes == json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    asset = payload["assets"]["setup"]
    assert asset["size"] == setup.stat().st_size
    assert asset["sha256"] == hashlib.sha256(setup.read_bytes()).hexdigest()
    assert asset["url"] == "https://host/setup.exe"


def test_release_key_is_read_only_from_environment(monkeypatch):
    monkeypatch.delenv("ARNOLD_DW_RELEASE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        load_release_key()

    generated = Ed25519PrivateKey.generate()
    pem = generated.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("ARNOLD_DW_RELEASE_KEY", pem)
    loaded = load_release_key()
    assert loaded.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ) == generated.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def test_make_manifest_rejects_empty_installer(tmp_path):
    setup = tmp_path / "empty.exe"
    setup.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        make_manifest(setup, "2.1.0", "", "", "https://host/setup.exe", Ed25519PrivateKey.generate())
