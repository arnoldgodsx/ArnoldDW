import hashlib

from tools.make_manifest import make_manifest


def test_make_manifest_includes_installer_size_and_hash(tmp_path):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"fake installer bytes")

    manifest = make_manifest(setup, "2.1.0", "2026-09-28T00:00:00Z", "Release notes", "https://host/setup.exe")

    asset = manifest["assets"]["setup"]
    assert asset["size"] == setup.stat().st_size
    assert asset["sha256"] == hashlib.sha256(setup.read_bytes()).hexdigest()
    assert asset["url"] == "https://host/setup.exe"


def test_make_manifest_rejects_empty_installer(tmp_path):
    setup = tmp_path / "empty.exe"
    setup.write_bytes(b"")

    try:
        make_manifest(setup, "2.1.0", "", "", "https://host/setup.exe")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty installer should be rejected")
