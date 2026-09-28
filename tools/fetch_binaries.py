#!/usr/bin/env python3
"""Download and verify pinned runtime tools used by local and release builds."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS: dict[str, dict[str, Any]] = {
    "ffmpeg": {
        "version": "9.0.2",
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip",
        "archive_sha256": "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
        "binary_sha256": "3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec",
        "archive_member": "bin/ffmpeg.exe",
        "destination": "bin/ffmpeg.exe",
        "version_args": ["-version"],
        "version_check": "ffmpeg version",
    },
}
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ArnoldDW-build/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output, length=CHUNK_SIZE)


def safe_member(archive: zipfile.ZipFile, expected_suffix: str) -> zipfile.ZipInfo:
    matches = []
    for info in archive.infolist():
        member_path = PurePosixPath(info.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"Unsafe path in binary archive: {info.filename}")
        if not info.is_dir() and member_path.as_posix().endswith(expected_suffix):
            matches.append(info)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {expected_suffix} in archive, found {len(matches)}")
    return matches[0]


def fetch_tool(name: str, force: bool = False) -> Path:
    tool = TOOLS[name]
    destination = ROOT / tool["destination"]
    expected_binary_hash = tool["binary_sha256"]
    if len(expected_binary_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_binary_hash):
        raise ValueError(f"{name} has no valid pinned binary SHA-256 in tools/fetch_binaries.py")

    if destination.is_file() and not force and sha256_file(destination) == expected_binary_hash:
        print(f"{name} {tool['version']} is already present and verified: {destination}")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"arnold-dw-{name}-") as temporary_dir:
        temporary = Path(temporary_dir)
        archive_path = temporary / "download.zip"
        extracted_path = temporary / destination.name
        print(f"Downloading {name} {tool['version']} from {tool['url']}")
        download(tool["url"], archive_path)
        archive_hash = sha256_file(archive_path)
        if archive_hash != tool["archive_sha256"]:
            raise ValueError(f"{name} archive SHA-256 mismatch: {archive_hash}")

        with zipfile.ZipFile(archive_path) as archive:
            member = safe_member(archive, tool["archive_member"])
            with archive.open(member) as source, extracted_path.open("wb") as output:
                shutil.copyfileobj(source, output, length=CHUNK_SIZE)

        binary_hash = sha256_file(extracted_path)
        if binary_hash != expected_binary_hash:
            raise ValueError(f"{name} binary SHA-256 mismatch: {binary_hash}")
        result = subprocess.run(
            [str(extracted_path), *tool["version_args"]],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or tool["version_check"] not in result.stdout.lower():
            raise ValueError(f"Downloaded {name} failed its version check: {result.stderr.strip()}")
        os.replace(extracted_path, destination)

    print(f"Installed verified {name} {tool['version']}: {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="download and replace binaries even if valid")
    parser.add_argument("tools", nargs="*", choices=sorted(TOOLS), help="tools to fetch (default: all)")
    args = parser.parse_args()
    selected_tools = args.tools or list(TOOLS)
    try:
        for tool_name in selected_tools:
            fetch_tool(tool_name, force=args.force)
    except (OSError, ValueError, zipfile.BadZipFile, urllib.error.URLError, subprocess.TimeoutExpired) as exc:
        print(f"Binary fetch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
