# Frequently asked questions and troubleshooting

## My video has no sound

For MP4 downloads, the app prefers an AAC audio stream when available and combines it with the video in an MP4 container. If a suitable audio stream is unavailable, it may use another available stream. Try the file in a different player and start the download again. An audio track is not guaranteed for every source.

## YouTube error — update the engine

Changes on YouTube can affect how the download engine resolves a link. Open **Settings** from the home screen's gear button and select **Check for updates** in the **Download engine** section. If a newer yt-dlp version is available, select **Download and install**, then restart the app when prompted. You can choose the **Nightly** update channel to receive early fixes; if a problem occurs, the app can return to the previous engine. If the error continues, report it on [GitHub Issues](https://github.com/arnoldgodsx/ArnoldDW/issues) with the app version and steps to reproduce. Do not share passwords, cookies, or private links.

## Instagram says there have been too many requests

Instagram may be temporarily limiting requests. Wait before trying again and avoid sending repeated requests for many profiles or posts. If access errors continue, try again later.

## Can I download content from a private account?

No. For a private profile, the app only lets you select the profile picture. Private posts and videos cannot be downloaded.

## My antivirus flags the installer

Apps packaged with PyInstaller may trigger false-positive warnings in some antivirus products. Before deciding how to handle a warning, verify that you downloaded the installer from the official [GitHub Releases](https://github.com/arnoldgodsx/ArnoldDW/releases/latest) page. You can submit the file to your antivirus provider for review.

## How do I change the download folder or file name?

Use **Browse** in the **Save location** field on the YouTube or Instagram screen to choose an existing folder. The app remembers the selection. YouTube file names are based on the video title and ID; Instagram file names include the username, post shortcode, and item order.

## How do I change video quality, cover art, or metadata options?

Open **Settings** using the gear button on the home screen. Under **Download**, choose **Maximum compatibility (H.264)** or **Highest quality**, and toggle metadata and cover image embedding. These options require ffmpeg; cover embedding for MP4 also requires ffprobe. The Settings screen shows when a required tool is missing.

## The engine update did not take effect

After installing an engine update, restart Arnold DW to activate it. If a download is active, the app asks for confirmation before restarting because active downloads will be canceled. To abandon an available update without installing it, select **Dismiss** in Settings.

## Why does TikTok not open?

TikTok downloads are not currently supported by the app.

## Language

[Türkçe sık sorulan sorular](../sss.md) · [English FAQ](faq.md)

## How do I uninstall Arnold DW?

Open **Settings → Apps → Installed apps** (or **Control Panel → Programs and Features**), find **Arnold DW** and select **Uninstall**. You can also use **Uninstall Arnold DW** in the Start menu's Arnold DW folder. If the app is running, the uninstaller offers to close it. It then asks whether to delete your settings, download history, logs and engine updates in `%APPDATA%\Arnold DW`; answer **No** to keep them for a later reinstall. Your downloaded files are never deleted.

For scripted removal, run `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES` from the install folder; user data is kept.
