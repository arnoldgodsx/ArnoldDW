# Arnold DW

![Arnold DW](docs/images/social-preview.png)

Arnold DW is a Windows desktop app for downloading YouTube and Instagram content. Paste a link, review the preview, and choose the download options.

![Arnold DW home screen](docs/images/baseline-home.png)

## Working features

- **YouTube:** Download an individual video as MP4, with quality options up to the highest resolution available from the source, or as MP3 at 320, 192, or 128 kbps.
- **Preview:** When you enter a video link, the app shows its thumbnail, title, channel, and duration.
- **Cancel:** You can cancel an active YouTube or Instagram download.
- **Instagram post, reel, or carousel:** Preview downloadable items in a post and choose which ones to download.
- **Public Instagram profile:** Choose posts/photos, reels/videos, and the profile picture categories.
- **Download folder:** Choose a download folder; the app remembers it the next time it starts.
- **Settings:** Choose the YouTube video mode, whether to embed metadata and cover art, and the yt-dlp update channel. Check for and install engine updates, and view the detected helper tools.

TikTok is not currently supported and is not presented as a working feature.

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
