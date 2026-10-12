# User guide

## Open the app

On the very first launch Arnold DW shows a setup screen that downloads FFmpeg and Deno (about 71 MB, only once). Keep the app open until it shows **Hazır!**; if the download fails, select **Tekrar dene**.

Open Arnold DW from the Start menu or the shortcut created during installation. Choose YouTube or Instagram on the home screen.

## Download a YouTube video

1. Paste a link to an individual YouTube video into the field on the YouTube screen.
2. Wait for the preview to load while the app resolves the link. The preview shows the thumbnail, title, channel, and duration.
3. Choose **MP4** or **MP3**. For MP4, the quality menu is limited to resolutions available from the video. For MP3, choose 320, 192, or 128 kbps.
4. Choose an existing download folder with **Browse**. The default is `Downloads\Arnold DW`. The app remembers your choice the next time it starts; the same folder is used for YouTube and Instagram downloads.
5. Select **Download**. During the download, the app shows progress, speed, and estimated time remaining. Select the same button to cancel.

The file name is based on the video title and ID. MP4 audio and video are combined in an MP4 container. MP3 uses the selected bitrate.

## Change YouTube video and embedding options

Open **Settings** with the gear button (⚙) on the home screen. Under **Download**, choose a video mode:

- **Maximum compatibility (H.264):** Uses H.264 video and AAC audio for broad player and phone compatibility. YouTube offers this mode up to 1080p.
- **Highest quality:** Uses the best source streams, including VP9 or AV1 where available, up to 4K. Some older players may not support these files.

You can also turn embedding of title, artist, and chapter metadata on or off, and choose whether to embed the cover image. These options require ffmpeg; embedding a cover image in MP4 also requires ffprobe. The Settings screen reports when a required tool is unavailable.

## Download Instagram content

1. Enter a post or reel link, or a public profile link or username.
2. When the preview appears, select individual media items in the post. In a carousel, only the checked photos and videos are downloaded. All items are selected by default; use the select-all checkbox to change the selection.
3. For a profile, select any of **Posts / Photos**, **Reels / Videos**, and **Profile Picture**.
4. Select **Download**. The same button cancels the active download.

Instagram profile items are saved to the selected download folder. If a file with the same name already exists, that item is skipped instead of being overwritten. For a private profile, only the profile picture can be selected. Instagram access limits, removed content, or connection errors can prevent a download.

## Change the download folder

The **Save location** field on either the YouTube or Instagram screen shows the current folder. Select **Browse** and choose an existing folder. The selection is used for both services and saved in the app settings.

## Update the download engine

Open **Settings** from the gear button on the home screen. The **Download engine** section shows the installed yt-dlp version and whether it came with the app or was updated. Select **Check for updates** to look for a newer version. If one is available, select **Download and install** to approve and install it, or **Dismiss** to leave the current version in place. You can cancel an installation while it is downloading.

Choose the **Stable** channel for regular releases or **Nightly** for early fixes. Nightly updates may resolve YouTube changes sooner; if a problem occurs, the app can return to the previous engine. The app can check for updates once a day when that option is enabled, but it only installs an update after you approve it. After installation, select **Restart now** to activate the new engine. If downloads are active, the app asks you to confirm restarting because it will cancel them.

The Settings screen also reports whether a JavaScript runtime, ffmpeg, and ffprobe are available. Open the **About** section and select **Open log folder** to view diagnostic logs.

## Language

[Türkçe kullanım kılavuzu](../kullanim.md) · [English user guide](usage.md)
