import pytest

from arnold_dw.core.runtime.versioning import (
    is_newer,
    meets_minimum,
    parse_version,
    pinned_requirement,
    python_satisfies,
    same_version,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026.08.19", (2026, 8, 19)),
        ("2026.8.19", (2026, 8, 19)),
        ("2026.9.16.232951.dev0", (2026, 9, 16, 232951)),
        ("v24.19.0", (24, 19)),
        ("2.9.7", (2, 9, 7)),
        ("1.2.11-canary", (1, 2, 11)),
        ("7", (7,)),
        ("0", (0,)),
        ("", None),
        (None, None),
        ("unknown", None),
        ("N-12345-gabc", None),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_is_newer_handles_yt_dlp_spellings():
    assert not is_newer("2026.8.19", "2026.08.19")
    assert is_newer("2026.9.1", "2026.08.19")
    assert is_newer("2026.10.1", "2026.9.30")
    assert not is_newer("2026.7.4", "2026.08.19")


def test_is_newer_nightly_after_same_day_stable():
    assert is_newer("2026.8.19.232711.dev0", "2026.8.19")
    assert not is_newer("2026.8.18.232711.dev0", "2026.8.19")


def test_is_newer_with_unknown_values():
    assert is_newer("2026.1.1", None)
    assert is_newer("2026.1.1", "garbage")
    assert not is_newer(None, "2026.1.1")
    assert not is_newer("garbage", None)


def test_same_version():
    assert same_version("2026.08.19", "2026.8.19")
    assert not same_version("2026.8.19", "2026.8.20")
    assert not same_version(None, None)


def test_meets_minimum():
    assert meets_minimum("2.3.0", (2, 3, 0))
    assert meets_minimum("2.9.7", (2, 3, 0))
    assert not meets_minimum("2.2.12", (2, 3, 0))
    assert meets_minimum("22.0.0", (22, 0, 0))
    assert not meets_minimum("20.11.1", (22, 0, 0))
    assert not meets_minimum(None, (1,))


@pytest.mark.parametrize(
    ("spec", "version", "ok"),
    [
        (None, (3, 12, 1), True),
        ("", (3, 12, 1), True),
        (">=3.10", (3, 12, 1), True),
        (">=3.13", (3, 12, 1), False),
        (">=3.9, <4", (3, 12, 1), True),
        (">=3.9,<3.12", (3, 12, 1), False),
        ("!=3.12.*", (3, 12, 1), False),
        ("==3.*", (3, 12, 1), True),
        ("~=3.10", (3, 12, 1), True),
        ("~=3.10", (4, 0, 0), False),
        (">3.12", (3, 12, 1), True),
        (">=3.12.2", (3, 12, 1), False),
        ("weird-spec", (3, 12, 1), True),
    ],
)
def test_python_satisfies(spec, version, ok):
    assert python_satisfies(spec, version) is ok


def test_pinned_requirement():
    requires = [
        'brotli; implementation_name == "cpython" and extra == "default"',
        'yt-dlp-ejs==0.8.0; extra == "default"',
        'yt-dlp-ejs==0.8.0; extra == "pin"',
    ]
    assert pinned_requirement(requires, "yt-dlp-ejs") == "0.8.0"
    assert pinned_requirement(requires, "yt_dlp_ejs") == "0.8.0"
    assert pinned_requirement(requires, "brotli") is None
    assert pinned_requirement(None, "yt-dlp-ejs") is None
    assert pinned_requirement(["yt-dlp-ejs>=0.8"], "yt-dlp-ejs") is None
