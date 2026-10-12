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
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS: dict[str, dict[str, Any]] = {
    "ffmpeg": {
        "version": "9.0.2-27-g7e93014c5b (LGPL shared, autobuild-2026-10-12-13-12)",
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-12-13-12/ffmpeg-n9.0.2-27-g7e93014c5b-win64-lgpl-shared-9.0.zip",
        "archive_sha256": "de3f3b16b3dbf2038a56878aa35795f48bd220f01479697e008470773cecba5b",
        "max_archive_bytes": 120_000_000,
        "archive_member": "bin/ffmpeg.exe",
        "destination_dir": "bin",
        "include_bin_files": True,
        "version_args": ["-version"],
        "version_check": "ffmpeg version",
        "configuration_check": "--enable-shared",
        "forbidden_configuration": "--enable-gpl",
        "output_sha256": {
            "ffmpeg.exe": "1f1334bab3fd4c8086b01dd1f618f2a3a453dfa39429b3a65a13b40502a194e3",
            "ffprobe.exe": "19cfb4211cc00c19591058ab06cd171eeec1dadc5296207e6f6d3414232380a5",
            "avcodec-63.dll": "501c1abd17650647ac829f72c5aa24379eb80e47c001163900da64cec36d68c6",
            "avdevice-63.dll": "33cd7781840597b09b68acb2d75491571ce238f4fcb83465942e6989df12374f",
            "avfilter-12.dll": "3541c6d1af33ae7919dfe945ed5e81fffd50741d948e535d9f0013935fc26d75",
            "avformat-63.dll": "4a598e944123550f3b4f09f5635dd6cf7b2c8b083ac21e2192e1a6290077ebef",
            "avutil-61.dll": "bf15dba19fcc23ba4a79faabae11705e8db0e8647a2003d7efdb0075fa9536c2",
            "swresample-7.dll": "6f1033a18a11358d6665bf80d07b57ff63efe8529e5cc8e73d49b07ddfc3fbe7",
            "swscale-10.dll": "fb7562f214f93743962bbb7879577b11bc8b52a589027fd220e14237b7d0c133",
        },
    },
    "deno": {
        "version": "2.9.7",
        "url": "https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-pc-windows-msvc.zip",
        "archive_sha256": "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238",
        "max_archive_bytes": 60_000_000,
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
# Upstream autobuilds (BtbN) are pruned after a few weeks. The release workflow copies
# each verified archive to this release so pinned builds stay reproducible.
MIRROR_BASE_URL = "https://github.com/arnoldgodsx/ArnoldDW/releases/download/runtime-binaries/"
CHUNK_SIZE = 1024 * 1024
ALLOWED_DOWNLOAD_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, max_bytes: int) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or parsed.hostname is None or parsed.hostname.lower() not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError("Binary archive URL must use HTTPS on an allowed host")
    if max_bytes <= 0:
        raise ValueError("Binary archive size limit must be positive")
    request = urllib.request.Request(url, headers={"User-Agent": "ArnoldDW-build/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        final_url = getattr(response, "url", None) or response.geturl()
        final = urllib.parse.urlparse(final_url)
        if final.scheme.lower() != "https" or final.hostname is None or final.hostname.lower() not in ALLOWED_DOWNLOAD_HOSTS:
            raise ValueError("Binary archive redirect must end at HTTPS on an allowed host")
        total = 0
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"Binary archive exceeds the {max_bytes}-byte limit")
            output.write(chunk)


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


def archive_name(tool: dict[str, Any]) -> str:
    return PurePosixPath(urllib.parse.urlparse(tool["url"]).path).name


def candidate_urls(tool: dict[str, Any]) -> list[str]:
    """The pinned upstream URL first, then this project's mirror of the same archive."""
    return [tool["url"], MIRROR_BASE_URL + archive_name(tool)]


def download_verified_archive(name: str, tool: dict[str, Any], archive_path: Path) -> None:
    errors = []
    for url in candidate_urls(tool):
        print(f"Downloading {name} {tool['version']} from {url}")
        try:
            download(url, archive_path, tool["max_archive_bytes"])
            archive_hash = sha256_file(archive_path)
            if archive_hash != tool["archive_sha256"]:
                raise ValueError(f"{name} archive SHA-256 mismatch: {archive_hash}")
            return
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append(f"{url}: {exc}")
            archive_path.unlink(missing_ok=True)
    raise ValueError(f"Could not download a verified {name} archive; " + "; ".join(errors))


def fetch_tool(name: str, force: bool = False, archive_dir: Path | None = None) -> Path:
    tool = TOOLS[name]
    destination_dir = ROOT / tool["destination_dir"]
    destination = destination_dir / tool.get("destination_name", name + ".exe")
    expected_outputs = tool.get("output_sha256")
    if destination.is_file() and not force and archive_dir is None:
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
    # Stage inside the destination directory: os.replace below must stay on one volume
    # (on CI the checkout is on D: while the system temp dir is on C:).
    with tempfile.TemporaryDirectory(prefix=f".fetch-{name}-", dir=destination_dir) as temporary_dir:
        temporary = Path(temporary_dir)
        archive_path = temporary / "download.zip"
        download_verified_archive(name, tool, archive_path)
        if archive_dir is not None:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_path, archive_dir / archive_name(tool))

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
    parser.add_argument("--archive-dir", type=Path,
                        help="also keep each verified archive here (for mirroring); implies a fresh download")
    parser.add_argument("tools", nargs="*", choices=sorted(TOOLS), help="tools to fetch (default: all)")
    args = parser.parse_args()
    selected_tools = args.tools or list(TOOLS)
    try:
        for tool_name in selected_tools:
            fetch_tool(tool_name, force=args.force, archive_dir=args.archive_dir)
    except (OSError, ValueError, zipfile.BadZipFile, urllib.error.URLError, subprocess.TimeoutExpired) as exc:
        print(f"Binary fetch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
