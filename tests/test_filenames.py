import os

import pytest

from arnold_dw.core import filenames


@pytest.mark.parametrize("value, expected", [
    ("normal_name", "normal_name"),
    ('a<b>c:d"e/f\\g|h?i*j', "a_b_c_d_e_f_g_h_i_j"),
    ("tab\there\nnewline", "tab_here_newline"),  # control chars go first, as before
    ("ctrl\x01char", "ctrl_char"),
    ("  spaced   out  ", "spaced out"),
    ("trailing dots...", "trailing dots"),
    ("...", "instagram"),
    ("", "instagram"),
    ("çğüşöı İstanbul 🎬", "çğüşöı İstanbul 🎬"),
    (12345, "12345"),
])
def test_safe_filename_part(value, expected):
    assert filenames.safe_filename_part(value) == expected


def test_safe_filename_part_custom_fallback():
    assert filenames.safe_filename_part("", fallback="video") == "video"


def test_safe_filename_part_truncates_to_100_chars_without_trailing_space():
    value = "x" * 99 + " yyyy"
    result = filenames.safe_filename_part(value)
    assert len(result) <= 100
    assert not result.endswith((" ", "."))


@pytest.mark.parametrize("name", ["CON", "con", "NUL", "PRN", "AUX", "COM1", "LPT9", "nul.txt"])
def test_safe_filename_part_escapes_windows_device_names(name):
    result = filenames.safe_filename_part(name)
    assert result.split(".")[0].upper() not in {"CON", "NUL", "PRN", "AUX", "COM1", "LPT9"}
    assert result.startswith("_")


def test_safe_filename_part_leaves_names_merely_containing_device_words():
    assert filenames.safe_filename_part("CONSOLE") == "CONSOLE"
    assert filenames.safe_filename_part("COM10") == "COM10"


def test_youtube_outtmpl():
    path = filenames.youtube_outtmpl(os.path.join("C:\\", "dl"))
    assert path == os.path.join("C:\\", "dl", "%(title).150B [%(id)s].%(ext)s")


def test_instagram_basenames():
    assert filenames.instagram_post_basename("user.name", "AbC_1", 3) == "instagram_user.name_AbC_1_03"
    assert filenames.instagram_profile_pic_basename("user") == "instagram_user_profil"


def test_media_path_picks_extension_and_sanitizes(tmp_path):
    assert filenames.media_path(str(tmp_path), "a/b", True) == os.path.join(str(tmp_path), "a_b.mp4")
    assert filenames.media_path(str(tmp_path), "pic", False) == os.path.join(str(tmp_path), "pic.jpg")
