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
        "version": "9.0.2-12-gc867e13549 (LGPL shared, autobuild-2026-09-27-13-04)",
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-27-13-04/ffmpeg-n9.0.2-12-gc867e13549-win64-lgpl-shared-9.0.zip",
        "archive_sha256": "8ee8dcffde407fe78381b8d5888a0d19dca5e20fb26cdadba78c1bbc03043e30",
        "archive_member": "bin/ffmpeg.exe",
        "destination_dir": "bin",
        "include_bin_files": True,
        "version_args": ["-version"],
        "version_check": "ffmpeg version",
        "configuration_check": "--enable-shared",
        "forbidden_configuration": "--enable-gpl",
        "output_sha256": {
            "ffmpeg.exe": "2c024f25b3ccfed2b860e45846d0be20298f76133b3476bbcce2d2907fc89cea",
            "ffprobe.exe": "851cf0f640639c0231048cb6ce60e97caf90db5fd6c1f0ed74e69873a6af1559",
            "avcodec-63.dll": "f9520ee939e4eeca8d63bb8d5f8518233a0d855199048c2b0909586d88c6fb1a",
            "avdevice-63.dll": "d7dbc4f2c9cca0b411368abcaef5cf0fc4769612ab52220defa870a74629af1e",
            "avfilter-12.dll": "088cb395e95b9f6463e44e071f35a5ea1de18293d4f3f48d70e26729c95bf162",
            "avformat-63.dll": "216f2b4ef19abd016beaea4a5875508fb3faa4b4bf34d4c03933b17d60ecf54f",
            "avutil-61.dll": "bf37b7814bf0edf663100095d70405a84c041adb1df368cd6bd63af4c62c4a2e",
            "swresample-7.dll": "febf67935243d03e9f073a411da519d6072d9a6d5e7da242f71fe3c26a7384be",
            "swscale-10.dll": "1a398639c5a36cd078beb0087a1c341e5d2656073267455440eca93d21534dec",
        },
    },
    "deno": {
        "version": "2.9.7",
        "url": "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip",
        "archive_sha256": "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238",
        "archive_member": "deno.exe",
        "destination_dir": "bin",
        "destination_name": "deno.exe",
        "version_args": ["--version"],
        "version_check": "deno 2.9.7",
        "output_sha256": {
            "deno.exe": "e020f3e232bd16e33768dee528e5983349c962952051ced0a5d58ad42f5d9b33",
        },
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
    destination_dir = ROOT / tool["destination_dir"]
    destination = destination_dir / tool.get("destination_name", name + ".exe")
    expected_outputs = tool.get("output_sha256")
    if destination.is_file() and not force:
        if expected_outputs:
            valid_outputs = all(
                (destination_dir / filename).is_file()
                and sha256_file(destination_dir / filename) == expected_hash
                for filename, expected_hash in expected_outputs.items()
            )
            if valid_outputs:
                print(f"{name} {tool['version']} is already present and verified: {destination}")
                return destination
        else:
            print(f"{name} {tool['version']} is already present: {destination}")
            return destination

    destination_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"arnold-dw-{name}-") as temporary_dir:
        temporary = Path(temporary_dir)
        archive_path = temporary / "download.zip"
        print(f"Downloading {name} {tool['version']} from {tool['url']}")
        download(tool["url"], archive_path)
        archive_hash = sha256_file(archive_path)
        if archive_hash != tool["archive_sha256"]:
            raise ValueError(f"{name} archive SHA-256 mismatch: {archive_hash}")

        with zipfile.ZipFile(archive_path) as archive:
            if tool.get("include_bin_files"):
                members = []
                for info in archive.infolist():
                    member_path = PurePosixPath(info.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"Unsafe path in binary archive: {info.filename}")
                    if (not info.is_dir() and len(member_path.parts) >= 2
                            and member_path.parts[-2].lower() == "bin"
                            and (member_path.suffix.lower() == ".dll" or member_path.name.lower() in {"ffmpeg.exe", "ffprobe.exe"})):
                        members.append(info)
                names = {PurePosixPath(info.filename).name.lower() for info in members}
                if not {"ffmpeg.exe", "ffprobe.exe"}.issubset(names):
                    raise ValueError("FFmpeg archive must contain both ffmpeg.exe and ffprobe.exe")
            else:
                members = [safe_member(archive, tool["archive_member"])]

            staged = temporary / "staged"
            staged.mkdir()
            for member in members:
                member_name = PurePosixPath(member.filename).name
                if name == "deno":
                    member_name = destination.name
                with archive.open(member) as source, (staged / member_name).open("wb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)

        extracted_path = staged / destination.name
        if not extracted_path.is_file():
            raise ValueError(f"{name} archive did not contain {destination.name}")
        if expected_outputs:
            staged_names = {path.name for path in staged.iterdir()}
            if staged_names != set(expected_outputs):
                raise ValueError(f"{name} archive contents do not match its pinned output manifest")
            for filename, expected_hash in expected_outputs.items():
                if sha256_file(staged / filename) != expected_hash:
                    raise ValueError(f"{name} binary SHA-256 mismatch: {filename}")
        result = subprocess.run(
            [str(extracted_path), *tool["version_args"]],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or tool["version_check"] not in result.stdout.lower():
            raise ValueError(f"Downloaded {name} failed its version check: {result.stderr.strip()}")
        if "configuration_check" in tool:
            configuration = result.stdout.lower()
            if tool["configuration_check"] not in configuration or tool["forbidden_configuration"] in configuration:
                raise ValueError(f"Downloaded {name} does not match the pinned LGPL shared build configuration")
        if tool.get("include_bin_files"):
            expected_names = set(expected_outputs or ())
            for existing in destination_dir.iterdir():
                if (existing.is_file() and existing.suffix.lower() == ".dll"
                        and existing.name not in expected_names):
                    existing.unlink()
        for staged_file in staged.iterdir():
            os.replace(staged_file, destination_dir / staged_file.name)

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
