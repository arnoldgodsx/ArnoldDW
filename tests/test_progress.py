"""CombinedProgress: an MP4's video + audio streams give one monotonic bar."""

import pytest

from arnold_dw.core.progress import CombinedProgress


def test_known_sizes_give_a_byte_based_fraction_across_streams():
    p = CombinedProgress(expected_sizes=[800, 200])
    assert p.update("v", 400, 800).fraction == pytest.approx(0.4)
    assert p.update("v", 800, 800, finished=True).fraction == pytest.approx(0.8)
    # The audio stream starts at 0 % of itself - the job doesn't go back to 0.
    second = p.update("a", 0, 200)
    assert second.fraction == pytest.approx(0.8)
    assert second.total == 1000
    assert p.update("a", 100, 200).fraction == pytest.approx(0.9)
    assert p.update("a", 200, 200, finished=True).fraction == pytest.approx(1.0)


def test_unknown_sizes_split_the_bar_into_equal_shares():
    p = CombinedProgress(stream_count=2)
    assert p.update("v", 50, 100).fraction == pytest.approx(0.25)
    assert p.update("v", 100, 100, finished=True).fraction == pytest.approx(0.5)
    assert p.update("a", 10, 1000).fraction == pytest.approx(0.505)


def test_fraction_never_goes_backwards():
    p = CombinedProgress()
    assert p.update("v", 60, 100).fraction == pytest.approx(0.6)
    # yt-dlp occasionally revises the total estimate upwards.
    assert p.update("v", 61, 200).fraction == pytest.approx(0.6)


def test_unknown_total_has_no_fraction_but_counts_bytes():
    result = CombinedProgress().update("v", 1234)
    assert result.fraction is None and result.downloaded == 1234


def test_eta_is_for_the_whole_job():
    p = CombinedProgress(expected_sizes=[800, 200])
    result = p.update("v", 400, 800, speed=100, eta=4)
    assert result.eta == pytest.approx(6.0)  # 600 bytes left of the job, not 400 of the stream
    assert result.speed == 100


def test_for_info_reads_requested_format_sizes():
    info = {"requested_formats": [{"filesize": 700}, {"filesize_approx": 300}]}
    p = CombinedProgress.for_info(info)
    assert p.update("v", 350, 700).fraction == pytest.approx(0.35)
    assert CombinedProgress.for_info({}).update("x", 1, 2).fraction == pytest.approx(0.5)

