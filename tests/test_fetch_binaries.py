import hashlib
import shutil
import subprocess
import zipfile
from types import SimpleNamespace

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
            "archive_member": "bin/tool.exe",
            "destination_dir": ".",
            "destination_name": "tool.exe",
            "version_args": ["--version"],
            "version_check": "test-tool 1.0",
        },
    )

    assert fetch_binaries.fetch_tool("test-tool") == binary
    assert "already present" in capsys.readouterr().out


def test_fetch_tool_extracts_ffmpeg_pair_and_shared_libraries(tmp_path, monkeypatch):
    archive_path = tmp_path / "ffmpeg.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("release/bin/ffmpeg.exe", b"ffmpeg")
        archive.writestr("release/bin/ffprobe.exe", b"ffprobe")
        archive.writestr("release/bin/avcodec-9.dll", b"codec")
        archive.writestr("release/bin/ffplay.exe", b"not included")
        archive.writestr("release/doc/readme.txt", b"not included")
    archive_hash = sha256_file(archive_path)
    monkeypatch.setattr(fetch_binaries, "ROOT", tmp_path / "root")
    monkeypatch.setitem(
        fetch_binaries.TOOLS,
        "test-ffmpeg",
        {
            "version": "9.0",
            "url": "https://example.invalid/ffmpeg.zip",
            "archive_sha256": archive_hash,
            "archive_member": "bin/ffmpeg.exe",
            "destination_dir": "bin",
            "destination_name": "ffmpeg.exe",
            "include_bin_files": True,
            "version_args": ["-version"],
            "version_check": "ffmpeg version",
            "configuration_check": "--enable-shared",
            "forbidden_configuration": "--enable-gpl",
            "output_sha256": {
                "ffmpeg.exe": hashlib.sha256(b"ffmpeg").hexdigest(),
                "ffprobe.exe": hashlib.sha256(b"ffprobe").hexdigest(),
                "avcodec-9.dll": hashlib.sha256(b"codec").hexdigest(),
            },
        },
    )

    def fake_download(_url, destination):
        shutil.copyfile(archive_path, destination)

    monkeypatch.setattr(fetch_binaries, "download", fake_download)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="ffmpeg version 9.0 --enable-shared", stderr=""
        ),
    )

    result = fetch_binaries.fetch_tool("test-ffmpeg")
    bin_dir = tmp_path / "root" / "bin"
    assert result == bin_dir / "ffmpeg.exe"
    assert (bin_dir / "ffmpeg.exe").read_bytes() == b"ffmpeg"
    assert (bin_dir / "ffprobe.exe").read_bytes() == b"ffprobe"
    assert (bin_dir / "avcodec-9.dll").read_bytes() == b"codec"
    assert not (bin_dir / "ffplay.exe").exists()
    assert not (bin_dir / "readme.txt").exists()


def test_runtime_archives_are_pinned_to_requested_releases():
    assert fetch_binaries.TOOLS["ffmpeg"]["archive_sha256"] == "8ee8dcffde407fe78381b8d5888a0d19dca5e20fb26cdadba78c1bbc03043e30"
    assert "autobuild-2026-09-27-13-04" in fetch_binaries.TOOLS["ffmpeg"]["url"]
    assert fetch_binaries.TOOLS["deno"]["version"] == "2.9.7"
    assert fetch_binaries.TOOLS["deno"]["archive_sha256"] == "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238"
