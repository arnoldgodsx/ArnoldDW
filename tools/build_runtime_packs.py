#!/usr/bin/env python3
"""Build the compact runtime packs the app downloads on first launch.

For each component in ``arnold_dw.core.runtime.components`` this downloads the pinned
upstream archive (or its mirror), keeps only the files the app needs, verifies their
SHA-256 and writes ``arnolddw-<name>-<version>-win64.tar.xz`` (xz -9e). The release
workflow uploads the packs to the ``runtime-binaries`` release. Optionally the verified
upstream archives are kept too (``--archive-dir``) so they can be mirrored.
"""

from __future__ import annotations

import argparse
import io
import lzma
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arnold_dw.core.runtime import components  # noqa: E402

PRESET = 9 | lzma.PRESET_EXTREME


def write_pack(component: components.Component, folder: Path, output: Path) -> None:
    """Deterministic tar.xz (sorted names, zeroed metadata) of the component's files."""
    with tarfile.open(output, "w:xz", preset=PRESET, format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(component.files):
            data = (folder / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))


def build(component: components.Component, out_dir: Path, archive_dir: Path | None) -> Path:
    upstream = [s for s in component.sources if s.kind == "zip"]
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        tmp = Path(tmp)
        errors = []
        for source in upstream:
            archive = tmp / "upstream.zip"
            files = tmp / "files"
            shutil.rmtree(files, ignore_errors=True)
            files.mkdir()
            try:
                print(f"Downloading {component.name} from {source.url}")
                components._download(source, str(archive), None, None, None)
                components._extract(component, source, str(archive), str(files))
            except Exception as exc:  # next source
                errors.append(f"{source.url}: {exc}")
                continue
            if archive_dir is not None:
                archive_dir.mkdir(parents=True, exist_ok=True)
                name = os.path.basename(source.url)
                shutil.copyfile(archive, archive_dir / name)
            pack = out_dir / components.pack_name(component.name, component.version)
            write_pack(component, files, pack)
            # Round-trip: the pack must install exactly like the app will install it.
            check = tmp / "check"
            check.mkdir()
            pack_source = next(s for s in component.sources if s.kind == "tar.xz")
            components._extract(component, pack_source, str(pack), str(check))
            if pack.stat().st_size > pack_source.max_bytes:
                raise SystemExit(f"{pack.name} is larger than the app accepts ({pack_source.max_bytes} bytes)")
            print(f"Wrote {pack} ({pack.stat().st_size / 1_000_000:.1f} MB)")
            return pack
        raise SystemExit(f"Could not fetch {component.name}: " + "; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "runtime-packs")
    parser.add_argument("--archive-dir", type=Path, help="also keep the verified upstream archives here")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for component in components.COMPONENTS:
        build(component, args.out, args.archive_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
