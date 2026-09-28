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


class FakeResponse:
    def __init__(self, data, url):
        self.data = data
        self.url = url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.data) - self.offset
        result = self.data[self.offset:self.offset + size]
        self.offset += len(result)
        return result


def test_download_stream_enforces_archive_cap_and_checks_final_url(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fetch_binaries.urllib.request, "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"x" * 5, "https://release-assets.githubusercontent.com/archive.zip"),
    )
    destination = tmp_path / "archive.zip"
    with pytest.raises(ValueError, match="exceeds"):
        fetch_binaries.download("https://github.com/archive.zip", destination, 4)
    assert destination.stat().st_size <= 4


def test_download_rejects_non_https_or_unapproved_source(tmp_path):
    with pytest.raises(ValueError, match="must use HTTPS"):
        fetch_binaries.download("http://github.com/archive.zip", tmp_path / "http.zip", 100)
    with pytest.raises(ValueError, match="allowed host"):
        fetch_binaries.download("https://evil.test/archive.zip", tmp_path / "evil.zip", 100)


@pytest.mark.parametrize("final_url", ["http://github.com/archive.zip", "https://evil.test/archive.zip"])
def test_download_rejects_unsafe_final_url(tmp_path, monkeypatch, final_url):
    monkeypatch.setattr(
        fetch_binaries.urllib.request, "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"archive", final_url),
    )
    with pytest.raises(ValueError, match="redirect"):
        fetch_binaries.download("https://github.com/archive.zip", tmp_path / "archive.zip", 100)


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
            "max_archive_bytes": 100_000,
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

    def fake_download(_url, destination, _max_bytes):
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
