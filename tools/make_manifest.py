#!/usr/bin/env python3
"""Create a release update manifest for an Inno Setup installer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_ID = "2026a"


def make_manifest(
    setup_path: Path,
    version: str,
    published: str,
    notes: str,
    setup_url: str,
    signing_key: Ed25519PrivateKey | None = None,
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
    payload = {
        "version": version,
        "published": published,
        "notes": notes,
        "assets": {"setup": {"url": setup_url, "sha256": digest.hexdigest(), "size": size}},
    }
    return sign_manifest(payload, signing_key or load_release_key())


def load_release_key() -> Ed25519PrivateKey:
    """Load the release-only PEM secret from its environment variable."""
    pem = os.environ.get("ARNOLD_DW_RELEASE_KEY")
    if not pem:
        raise RuntimeError("ARNOLD_DW_RELEASE_KEY is required to sign the update manifest")
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("ARNOLD_DW_RELEASE_KEY must contain an unencrypted PEM private key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("ARNOLD_DW_RELEASE_KEY must be an Ed25519 private key")
    return key


def sign_manifest(payload: dict, signing_key: Ed25519PrivateKey) -> dict:
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise TypeError("signing_key must be an Ed25519 private key")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = signing_key.sign(canonical)
    return {
        "payload": base64.b64encode(canonical).decode("ascii"),
        "signatures": [{"key_id": KEY_ID, "sig": base64.b64encode(signature).decode("ascii")}],
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
