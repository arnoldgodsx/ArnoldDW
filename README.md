<div align="center">

<img src="site/assets/arnold-dw-logo.png" alt="Arnold DW logo" width="96" height="96">

# Arnold DW

**A clean, fast desktop downloader for YouTube and Instagram on Windows.**

Paste a link, check the preview, pick a format, and keep working while it downloads.

[![Latest release](https://img.shields.io/github/v/release/arnoldgodsx/ArnoldDW?label=release&color=e5484d)](https://github.com/arnoldgodsx/ArnoldDW/releases/latest)
[![CI](https://github.com/arnoldgodsx/ArnoldDW/actions/workflows/ci.yml/badge.svg)](https://github.com/arnoldgodsx/ArnoldDW/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011%20(x64)-0078d4)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)

[**Download for Windows**](https://github.com/arnoldgodsx/ArnoldDW/releases/latest) ·
[User guide](docs/en/usage.md) ·
[FAQ](docs/en/faq.md) ·
[Changelog](CHANGELOG.md) ·
[Türkçe](README.tr.md)

![Arnold DW home screen](docs/images/baseline-home.png)

</div>

---

## Table of contents

- [Features](#features)
- [System requirements](#system-requirements)
- [Installation](#installation)
- [Updating](#updating)
- [Uninstalling](#uninstalling)
- [Where Arnold DW keeps its files](#where-arnold-dw-keeps-its-files)
- [Using Arnold DW](#using-arnold-dw)
- [Building from source](#building-from-source)
- [Project layout](#project-layout)
- [Releasing a new version](#releasing-a-new-version)
- [Security](#security)
- [Third-party software and licenses](#third-party-software-and-licenses)
- [Legal notice](#legal-notice)

## Features

| | |
| --- | --- |
| 🎬 **YouTube video** | Single videos as **MP4** up to the best resolution the source offers (4K included). The default *Maximum compatibility* mode produces H.264 + AAC files that play everywhere; *Highest quality* keeps VP9/AV1 streams. |
| 🎵 **YouTube audio** | **MP3** at 320, 192 or 128 kbps, with optional title/artist/chapter metadata and cover art embedded. |
| 📸 **Instagram** | Posts, reels and carousels with per-item selection. Bulk download from public profiles (posts, reels, profile picture), with an optional, explicitly confirmed *use my browser session* mode. |
| 📥 **Download queue** | Press **Download** and paste the next link right away. Up to two downloads run at once; progress shows in the bottom strip and the **Downloads** tab. |
| 🕘 **History** | Cancel active downloads; open, show in folder or retry finished ones. History survives restarts. |
| 👀 **Preview** | Thumbnail, title, channel and duration before you download. Already-downloaded files are detected. |
| ⚙️ **Settings** | Download folder, video mode, metadata/cover embedding, download-engine (yt-dlp) updates with Stable/Nightly channels and optional daily check, helper tool status. |
| 🔄 **Self-updating engine** | The yt-dlp engine updates in place from PyPI over HTTPS with SHA-256 verification, staged install and automatic rollback, so YouTube changes are fixed without reinstalling the app. |
| 🚀 **Small download, guided first launch** | The installer is tiny. On first launch a setup screen downloads ffmpeg/ffprobe (LGPL build) and the Deno JavaScript runtime once (~71 MB, every file SHA-256 verified). Nothing else to install. |
| 🌍 **Bilingual setup** | The installer and uninstaller speak English and Turkish. |

> Arnold DW focuses on YouTube and Instagram. Other sites are not offered in the app.

## System requirements

- Windows 10 or Windows 11, 64-bit (x64)
- About 320 MB of free disk space (app + ffmpeg + Deno), plus space for your downloads
- An internet connection (also used once on first launch to download ffmpeg and Deno, ~71 MB)

No Python, ffmpeg or other tools need to be installed separately.

## Installation

### Setup wizard (recommended)

1. Go to the [latest release](https://github.com/arnoldgodsx/ArnoldDW/releases/latest) and download **`ArnoldDW-<version>-setup.exe`** — a single file of about 22 MB.
2. Run it. The installer is not code-signed yet, so Windows SmartScreen may show *"Windows protected your PC"*. After making sure you downloaded the file from the official release page, choose **More info → Run anyway**.
3. Walk through the wizard:

   | Step | What you choose |
   | --- | --- |
   | Language | English or Turkish (used for the wizard and the uninstaller) |
   | Install mode | **Install for all users** (needs administrator rights, installs to `C:\Program Files\Arnold DW`) or **Install for me only** (no admin needed, installs to `%LOCALAPPDATA%\Programs\Arnold DW`) |
   | Terms of use | Read and accept the usage disclaimer |
   | Destination | Keep the default folder or pick another one |
   | Shortcuts | A Start menu folder is always created; a desktop shortcut is optional |
   | Finish | Optionally launch Arnold DW right away |

4. **First launch.** Arnold DW opens a setup screen that downloads the two helper tools it needs — FFmpeg (merging video and audio, MP3 conversion) and Deno (unlocks every YouTube quality) — with live progress and speed. This happens only once; if the connection drops, press **Tekrar dene** (Retry). The tools are stored in `%LOCALAPPDATA%\Arnold DW\runtime`.

### Silent / unattended install

The setup supports the standard [Inno Setup command-line switches](https://jrsoftware.org/ishelp/index.php?topic=setupcmdline), which is handy for scripting or deployment tools:

```powershell
# Per-user, no prompts, with a desktop shortcut
.\ArnoldDW-1.1.0-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /TASKS=desktopicon

# All users, custom folder, with a log file
.\ArnoldDW-1.1.0-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS /DIR="D:\Apps\Arnold DW" /LOG="$env:TEMP\arnolddw-setup.log"

# Optional: download ffmpeg + Deno for the current user now instead of on first launch
& "$env:LOCALAPPDATA\Programs\Arnold DW\Arnold DW.exe" --install-components
```

## Updating

Download the newer setup from the [releases page](https://github.com/arnoldgodsx/ArnoldDW/releases) and run it. The wizard recognises the existing installation, closes Arnold DW if it is running, removes the old runtime files and installs the new version into the same folder. Your language, folder and shortcut choices, settings and download history are kept, and FFmpeg/Deno are only downloaded again when a new version pins different ones.

The **download engine** (yt-dlp) updates separately from inside the app: **Settings → Download engine → Check for updates**.

## Uninstalling

Use any of these:

- **Settings → Apps → Installed apps → Arnold DW → Uninstall**
- **Control Panel → Programs and Features → Arnold DW**
- **Start menu → Arnold DW → Uninstall Arnold DW**

The uninstaller:

1. Offers to close Arnold DW if it is still running (any active downloads stop).
2. Removes the program files, the downloaded FFmpeg/Deno (`%LOCALAPPDATA%\Arnold DW\runtime`), shortcuts and the *Installed apps* entry.
3. Asks whether to also delete your settings, download history, logs and engine updates in `%APPDATA%\Arnold DW`. Answer **No** to keep them for a later reinstall.

**Your downloaded files are never deleted.**

For unattended removal run `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES` from the install folder; in that mode user data is kept.

## Where Arnold DW keeps its files

| What | Location |
| --- | --- |
| Program files | `C:\Program Files\Arnold DW` (all users) or `%LOCALAPPDATA%\Programs\Arnold DW` (current user) |
| Settings | `%APPDATA%\Arnold DW\config.json` |
| Download history and thumbnails | `%APPDATA%\Arnold DW\history.db`, `%APPDATA%\Arnold DW\thumbs\` |
| Logs | `%APPDATA%\Arnold DW\logs\` (also reachable from **Settings → About → Open log folder**) |
| FFmpeg and Deno (downloaded on first launch) | `%LOCALAPPDATA%\Arnold DW\runtime\` |
| Updated download engines | `%APPDATA%\Arnold DW\engine\` |
| Downloads (default) | `%USERPROFILE%\Downloads\Arnold DW` (change it in Settings) |

## Using Arnold DW

1. Open Arnold DW and choose **YouTube** or **Instagram** on the home screen.
2. Paste a link. A preview with the thumbnail and details appears.
3. Choose the format (MP4/MP3), quality or the items to download.
4. Press **Download**. The job moves to the queue, and the screen is ready for the next link.
5. Follow progress in the bottom strip or the **Downloads** tab, then open the file or its folder from there.

Step-by-step instructions are in the [user guide](docs/en/usage.md); common problems (antivirus warnings, Instagram rate limits, failing YouTube links, uninstalling) are covered in the [FAQ](docs/en/faq.md).

## Building from source

### Prerequisites

- Windows 10/11 x64
- [Python 3.12](https://www.python.org/downloads/) (3.11+ works)
- [Inno Setup 6.3+](https://jrsoftware.org/isinfo.php) — only needed to build the setup wizard (`choco install innosetup`)

### Run from source

```powershell
git clone https://github.com/arnoldgodsx/ArnoldDW.git
cd ArnoldDW
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python tools/fetch_binaries.py   # optional: pinned ffmpeg/ffprobe + Deno into bin/ (skips the first-launch screen)
python app.py
```

### Lint and test

```powershell
python -m ruff check .
python -m pytest                  # unit tests; network tests are skipped
python -m pytest --network        # also run the live network tests
```

### Build the app and the setup wizard

```powershell
.\tools\build.ps1                       # uses .venv\Scripts\python.exe by default
.\tools\build.ps1 -RequireInstaller     # fail if Inno Setup is missing
.\tools\build.ps1 -Portable             # also produce a portable ZIP
```

The build prints a size report of the largest files so packaging regressions are easy to spot.

Output in `dist\`:

| File | Description |
| --- | --- |
| `dist\Arnold DW\` | The PyInstaller one-folder app |
| `ArnoldDW-<version>-win64.zip` | Portable package (only with `-Portable`) |
| `ArnoldDW-<version>-setup.exe` | Setup wizard with uninstaller |

To verify an installer end to end (silent install → shortcuts and *Installed apps* entry → first-launch component download → launch → uninstall while running → everything removed):

```powershell
.\tools\installer_smoke.ps1 -Setup dist\ArnoldDW-1.1.0-setup.exe
```

CI runs this same check on every push.

## Project layout

```text
ArnoldDW/
├── app.py                    # Launcher / PyInstaller entry point (`--version` for smoke tests)
├── arnold_dw/
│   ├── main.py               # Startup: single instance, logging, engine activation, UI
│   ├── config.py, paths.py   # Settings and file locations
│   ├── core/                 # UI-independent logic: downloads, queue, history, formats, errors
│   │   ├── platforms/        # Per-site download engines and URL router
│   │   └── runtime/          # yt-dlp engine updater, bundled binary discovery
│   ├── ui/                   # CustomTkinter window, theme, widgets and screens
│   └── i18n/                 # English/Turkish text catalogs
├── packaging/
│   ├── ArnoldDW.spec         # PyInstaller build definition
│   └── installer.iss         # Inno Setup wizard + uninstaller
├── tools/                    # build.ps1, installer_smoke.ps1, build_runtime_packs.py, fetch_binaries.py, make_manifest.py
├── tests/                    # pytest suite
├── docs/                     # User guides (English and Turkish), developer and release docs
└── site/                     # Static promotional website
```

The architecture, contribution recipes and update/threat model are described in the [developer guide](docs/gelistirici.md) (Turkish).

## Releasing a new version

1. Set `__version__` in `arnold_dw/__init__.py` (for example `1.0.1`).
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under a new `## [1.0.1] - YYYY-MM-DD` heading.
3. Either push a matching tag (`git tag v1.0.1 && git push origin v1.0.1`) or open **Actions → Release → Run workflow** on `main`, which creates the tag for you.

The [release workflow](.github/workflows/release.yml) lints, tests, builds the app and the setup wizard, runs the installer smoke test, and publishes a GitHub Release whose only download is `ArnoldDW-<version>-setup.exe`, with the changelog section as release notes. When the `ARNOLD_DW_RELEASE_KEY` secret is configured it also publishes a signed `latest.json` update manifest. The full checklist is in [docs/yayin.md](docs/yayin.md).

## Security

- Engine updates are downloaded only over HTTPS from PyPI, verified by size and SHA-256, installed into a staging folder and rolled back automatically if they fail to load.
- Bundled ffmpeg and Deno binaries are pinned and verified by SHA-256 at build time.
- The application update manifest is Ed25519-signed; unsigned or tampered manifests are rejected.
- Diagnostic bundles mask cookies, tokens and account names.

Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Third-party software and licenses

Arnold DW is built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Instaloader](https://github.com/instaloader/instaloader), [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [Pillow](https://python-pillow.org/), [Requests](https://requests.readthedocs.io/), [FFmpeg](https://ffmpeg.org/) (LGPL build), [Deno](https://deno.com/) and is packaged with [PyInstaller](https://pyinstaller.org/) and [Inno Setup](https://jrsoftware.org/isinfo.php). Licenses and attributions for everything that ships in the package are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), with full texts in [`licenses/`](licenses/).

## Legal notice

Arnold DW is a technical download utility. Use it only for content you own or are authorized to download and use, and respect copyright, local law and each platform's terms of service. YouTube, Instagram and the other named services are trademarks of their respective owners; Arnold DW is not affiliated with, endorsed by or sponsored by them. See [DISCLAIMER.md](DISCLAIMER.md).
