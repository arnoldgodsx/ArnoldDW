import hashlib
import zipfile

import pytest

from tools import fetch_binaries
from tools.fetch_binaries import safe_member, sha256_file


def test_sha256_file_reads_binary_contents(tmp_path):
    path = tmp_path / "binary.exe"
    path.write_bytes(b"verified binary")

    assert sha256_file(path) == hashlib.sha256(b"verified binary").hexdigest()


def test_safe_member_selects_expected_executable(tmp_path):
    path = tmp_path / "runtime.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ffmpeg-release/bin/ffmpeg.exe", b"binary")
        archive.writestr("ffmpeg-release/README.txt", b"readme")

    with zipfile.ZipFile(path) as archive:
        assert safe_member(archive, "bin/ffmpeg.exe").filename == "ffmpeg-release/bin/ffmpeg.exe"


def test_safe_member_rejects_path_traversal(tmp_path):
    path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../../bin/ffmpeg.exe", b"binary")

    with zipfile.ZipFile(path) as archive, pytest.raises(ValueError, match="Unsafe path"):
        safe_member(archive, "bin/ffmpeg.exe")


def test_fetch_tool_skips_binary_with_pinned_hash(tmp_path, monkeypatch, capsys):
    binary = tmp_path / "tool.exe"
    binary.write_bytes(b"already verified")
    monkeypatch.setattr(fetch_binaries, "ROOT", tmp_path)
    monkeypatch.setitem(
        fetch_binaries.TOOLS,
        "test-tool",
        {
            "version": "1.0",
            "url": "https://invalid.example/tool.zip",
            "archive_sha256": "0" * 64,
            "binary_sha256": hashlib.sha256(b"already verified").hexdigest(),
            "archive_member": "bin/tool.exe",
            "destination": "tool.exe",
            "version_args": ["--version"],
            "version_check": "test-tool 1.0",
        },
    )

    assert fetch_binaries.fetch_tool("test-tool") == binary
    assert "already present and verified" in capsys.readouterr().out
