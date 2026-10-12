# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import re
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from arnold_dw import __version__  # noqa: E402


version_match = re.match(r"^(\d+)\.(\d+)\.(\d+)", __version__)
if not version_match:
    raise ValueError(f"Unsupported application version: {__version__}")
version_parts = tuple(int(part) for part in version_match.groups()) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=version_parts,
        prodvers=version_parts,
        mask=0x3F,
        flags=0,
        OS=0x40004,
        fileType=0x1,
        subtype=0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "ArnoldGods"),
                        StringStruct("FileDescription", "Arnold DW media downloader"),
                        StringStruct("FileVersion", __version__),
                        StringStruct("InternalName", "Arnold DW"),
                        StringStruct("OriginalFilename", "Arnold DW.exe"),
                        StringStruct("ProductName", "Arnold DW"),
                        StringStruct("ProductVersion", __version__),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

datas = [(str(ROOT / "logo"), "logo")]
# ffmpeg and Deno are not bundled: the app downloads them on first launch
# (arnold_dw.core.runtime.components), which keeps the installer small.
datas += [(str(ROOT / "THIRD_PARTY_NOTICES.md"), "."), (str(ROOT / "licenses"), "licenses")]
binaries = []
hiddenimports = collect_submodules("yt_dlp")
customtkinter_data, customtkinter_binaries, customtkinter_imports = collect_all("customtkinter")
datas += customtkinter_data
binaries += customtkinter_binaries
hiddenimports += customtkinter_imports

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Build/test tooling and heavy optional packages yt-dlp can import but the app never uses.
    excludes=[
        "tkinter.test", "mutagen", "pytest", "_pytest", "pip", "setuptools", "pkg_resources",
        "PyInstaller", "ruff", "IPython", "numpy", "matplotlib", "pandas", "lib2to3", "pydoc_data",
        # Optional yt-dlp extras the app does not use (browser impersonation, Linux keyring).
        "curl_cffi", "secretstorage", "jeepney", "websockets",
        # Pillow's AVIF codec (7.5 MB); thumbnails are JPEG/PNG/WebP. The plugin degrades
        # gracefully when the module is missing.
        "PIL._avif",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Arnold DW",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "logo" / "icon.ico")],
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Arnold DW",
)
