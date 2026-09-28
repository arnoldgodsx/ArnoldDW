# Arnold DW

![Arnold DW](docs/images/social-preview.png)

Arnold DW is a Windows desktop app for downloading YouTube and Instagram content. Paste a link, review the preview, and choose the download options.

![Arnold DW home screen](docs/images/baseline-home.png)

## Working features

- **YouTube:** Download a single video as MP4 (up to the highest resolution the source offers, including 4K) or MP3 (320/192/128 kbps). MP4 defaults to H.264 + AAC, which plays in every player.
- **Instagram:** Preview and pick items from posts, reels and carousels. Bulk download from public profiles with an optional "use my browser session" setting.
- **Download queue:** Paste a link and press Download; it runs in the background while you paste the next one. Up to 2 downloads at a time, with progress in the bottom strip and the **Downloads** tab.
- **Downloads / history:** Cancel active downloads; open, show in folder or retry finished ones. History survives restarts.
- **Preview:** Thumbnail, title, channel and duration.
- **Settings (⚙):** Download folder, video mode, metadata/cover embedding, yt-dlp engine updates and update channel, helper tool status.

Download engines for TikTok, X, Reddit and other sites are built, but their screens are not yet, so the app does not offer them.

## Installation

Download the Windows installer from [GitHub Releases](https://github.com/arnoldgodsx/ArnoldDW/releases/latest). Run `setup.exe` and follow the installation steps.

## Developer setup

On a Windows environment with Python installed:

```powershell
git clone https://github.com/arnoldgodsx/ArnoldDW.git
cd ArnoldDW
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools/fetch_binaries.py
python app.py
```

`fetch_binaries.py` downloads the binary tools required for building. To package the app, run `tools/build.ps1` in PowerShell.

## Project layout

The app starts at `arnold_dw/main.py`; core logic is in `arnold_dw/core/`, screens are in `arnold_dw/ui/`, tests are in `tests/`, documentation is in `docs/`, and the promotional website is in `site/`. See the [developer guide](docs/gelistirici.md) for architecture, contribution, and release details.

## Third-party licenses

For licenses and attributions for the distributed packages, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the full license texts in `licenses/`.

## User documentation

- [User guide](docs/en/usage.md)
- [FAQ and troubleshooting](docs/en/faq.md)
- [Disclaimer](DISCLAIMER.md)

## Legal notice

See the [disclaimer](DISCLAIMER.md) for the Turkish and English legal notice. Use Arnold DW only for content you own or are authorized to download and use.

## Language

[Türkçe README](README.md) · [English README](README.en.md)
