"""Single instance guard: a second acquire fails until the first lock is released."""

import sys
import uuid

import pytest

from arnold_dw import single_instance


def random_key():
    return (uuid.uuid4().int & 0x7FFFFFFF) or 1


def test_instance_key_is_case_insensitive_and_nonzero():
    a = single_instance.instance_key("C:\\Users\\X\\AppData\\Roaming\\Arnold DW")
    b = single_instance.instance_key("c:\\users\\x\\appdata\\roaming\\arnold dw\\")
    assert a == b and a > 0
    assert single_instance.instance_key("D:\\other") != a
    assert single_instance.mutex_name(0x1F).endswith("ArnoldDW-0000001f")


@pytest.mark.skipif(sys.platform != "win32", reason="named mutexes are Windows only")
def test_second_acquire_fails_until_the_first_is_released():
    key = random_key()
    first = single_instance.acquire(key)
    assert first is not None and first.handle
    try:
        assert single_instance.acquire(key) is None
    finally:
        first.release()
    again = single_instance.acquire(key)
    assert again is not None
    again.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_find_window_without_a_tagged_window_returns_none():
    assert single_instance.find_window(random_key()) is None
