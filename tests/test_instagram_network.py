"""Real-network checks against Instagram (see hq/reports/CX-3-T08.md for the measurement this
follows). Skipped unless --network. Instagram rate-limits per URL/endpoint rather than with one
shared cooldown, so a 429 mid-run is skipped with an explicit message instead of xfail - a fixed
"expected failure" would hide a real regression the next time this happens to pass.
"""

import pytest

from arnold_dw.core import instagram
from arnold_dw.core.errors import InstagramRateLimited

pytestmark = pytest.mark.network

REEL_URL = "https://www.instagram.com/reel/DJf0_RmSd-T/"    # CX-3-T08: resolves anonymously via yt-dlp
PHOTO_URL = "https://www.instagram.com/p/BO-zn3kDJcp/"      # CX-3-T08: single photo, yt-dlp says "no video"
CAROUSEL_URL = "https://www.instagram.com/p/CEY-sSQng08/"   # CX-3-T08: verified mixed carousel (3 items)


def _resolve_or_skip(url):
    try:
        return instagram.resolve(url)
    except InstagramRateLimited as exc:
        pytest.skip(f"Instagram rate limited this run, not a code failure: {exc}")


def test_reel_resolves_through_ytdlp():
    preview = _resolve_or_skip(REEL_URL)
    assert isinstance(preview, instagram.PostPreview)
    assert len(preview.media) == 1
    assert preview.media[0]["engine"] == "ytdlp"
    assert preview.media[0]["is_video"] is True
    assert preview.media[0]["url"]


def test_photo_resolves_through_instaloader():
    preview = _resolve_or_skip(PHOTO_URL)
    assert isinstance(preview, instagram.PostPreview)
    assert len(preview.media) == 1
    assert preview.media[0]["engine"] == "instaloader"
    assert preview.media[0]["is_video"] is False


def test_mixed_carousel_resolves_through_instaloader():
    preview = _resolve_or_skip(CAROUSEL_URL)
    assert isinstance(preview, instagram.PostPreview)
    assert len(preview.media) >= 2
    assert all(item["engine"] == "instaloader" for item in preview.media)


def test_profile_metadata_is_anonymous_and_not_googlebot():
    preview = _resolve_or_skip("https://www.instagram.com/natgeo/")
    assert isinstance(preview, instagram.ProfilePreview)
    assert preview.profile.username == "natgeo"
    assert "googlebot" not in instagram.new_loader().context.user_agent.lower()
