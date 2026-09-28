#!/usr/bin/env python3
"""Create a release update manifest for an Inno Setup installer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def make_manifest(
    setup_path: Path,
    version: str,
    published: str,
    notes: str,
    setup_url: str,
) -> dict:
    if not setup_path.is_file():
        raise FileNotFoundError(setup_path)
    digest = hashlib.sha256()
    size = 0
    with setup_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size == 0:
        raise ValueError("Setup installer must not be empty")
    return {
        "version": version,
        "published": published,
        "notes": notes,
        "assets": {"setup": {"url": setup_url, "sha256": digest.hexdigest(), "size": size}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", required=True, type=Path, help="built setup.exe")
    parser.add_argument("--version", required=True)
    parser.add_argument("--published", required=True, help="release publication timestamp")
    parser.add_argument("--notes", default="")
    parser.add_argument("--notes-file", type=Path, help="read release notes from a UTF-8 text file")
    parser.add_argument("--setup-url", required=True, help="public URL where setup.exe will be hosted")
    parser.add_argument("--output", type=Path, default=Path("dist/latest.json"))
    args = parser.parse_args()
    notes = args.notes_file.read_text(encoding="utf-8") if args.notes_file else args.notes
    manifest = make_manifest(args.setup, args.version, args.published, notes, args.setup_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote update manifest for {args.version}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
