import io

import pytest
from fakes import FakeResponse
from PIL import Image

from arnold_dw.core import http


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (4, 3), (255, 0, 0, 128)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def serve(monkeypatch):
    def install(response):
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        monkeypatch.setattr(http.requests, "get", fake_get)
        return calls

    return install


def test_get_bytes_streams_with_timeout(serve):
    calls = serve(FakeResponse([b"ab", b"cd"]))
    body, _ = http.get_bytes("https://x/y", timeout=5, limit=10)
    assert body == b"abcd"
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["timeout"] == 5


def test_get_bytes_rejects_large_content_length(serve):
    serve(FakeResponse([b"a"], headers={"Content-Length": "999"}))
    with pytest.raises(http.ResponseTooLarge):
        http.get_bytes("https://x", timeout=5, limit=10)


def test_get_bytes_rejects_oversized_body_without_content_length(serve):
    serve(FakeResponse([b"x" * 6, b"x" * 6]))
    with pytest.raises(http.ResponseTooLarge):
        http.get_bytes("https://x", timeout=5, limit=10)


def test_get_text_decodes(serve):
    serve(FakeResponse(["İstanbul".encode()]))
    assert http.get_text("https://x", timeout=5) == "İstanbul"


def test_fetch_image_decodes_to_rgb(serve):
    serve(FakeResponse([_png_bytes()]))
    img = http.fetch_image("https://x/img.png")
    assert img.mode == "RGB"
    assert img.size == (4, 3)


@pytest.mark.parametrize("response", [
    FakeResponse([b""]),                          # 0-byte thumbnail
    FakeResponse([b"not an image"]),
    FakeResponse([b"x"], status=404),
    FakeResponse([b"x" * 100], headers={"Content-Length": str(10**9)}),
])
def test_fetch_image_failures_return_none(serve, response):
    serve(response)
    assert http.fetch_image("https://x/img") is None


def test_fetch_image_without_url_skips_network(serve):
    calls = serve(FakeResponse([b""]))
    assert http.fetch_image(None) is None
    assert http.fetch_image("") is None
    assert calls == []
