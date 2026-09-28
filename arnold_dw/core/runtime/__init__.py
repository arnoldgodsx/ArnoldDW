"""Engine runtime layer: live yt-dlp updates, external tool discovery, format selectors.

Import-light on purpose: nothing in this package imports ``yt_dlp`` at module level, so
``ytdlp_updater.activate()`` can run before the first ``import yt_dlp`` of the app.

Startup order (Phase 2 integration)::

    from arnold_dw.core.runtime import ytdlp_updater
    ytdlp_updater.activate()          # must run before anything imports yt_dlp
    ...
    from arnold_dw.core.runtime import binaries, selectors
    opts = {**binaries.ytdlp_runtime_options(), **selectors.video_download_options(1080)}
"""
