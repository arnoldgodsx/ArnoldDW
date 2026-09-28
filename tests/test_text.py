import pytest

from arnold_dw.core.text import fmt_bytes, fmt_duration, fmt_eta, fmt_speed


@pytest.mark.parametrize("value, expected", [
    (0, "0:00"),
    (19, "0:19"),
    (59.9, "0:59"),
    (61, "1:01"),
    (3599, "59:59"),
    (3600, "1:00:00"),
    (36061, "10:01:01"),
    ("125", "2:05"),
    (None, ""),
    ("abc", ""),
])
def test_fmt_duration(value, expected):
    assert fmt_duration(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, ""),
    (0, ""),
    (500, "0 KB/s"),
    (1500, "2 KB/s"),
    (999_999, "1000 KB/s"),
    (1_000_000, "1.0 MB/s"),
    (12_345_678, "12.3 MB/s"),
])
def test_fmt_speed(value, expected):
    assert fmt_speed(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, ""),
    ("x", ""),
    (-1, ""),
    (0, "0 sn"),
    (59, "59 sn"),
    (60, "1 dk"),
    (89, "1 dk"),
    (90, "2 dk"),
    (3600, "60 dk"),
    (12.7, "12 sn"),
])
def test_fmt_eta(value, expected):
    assert fmt_eta(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, ""),
    (0, ""),
    (-5, ""),
    (512, "1 KB"),
    (1500, "2 KB"),
    (2_500_000, "2.5 MB"),
    (3_210_000_000, "3.21 GB"),
])
def test_fmt_bytes(value, expected):
    assert fmt_bytes(value) == expected
