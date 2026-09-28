"""Test doubles shared by the core tests (no network)."""

import requests


class FakeResponse:
    def __init__(self, chunks=(), status=200, headers=None, fail_after=None, encoding="utf-8"):
        self._chunks = list(chunks)
        self.status_code = status
        self.headers = headers or {}
        self._fail_after = fail_after
        self.encoding = encoding
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")

    def iter_content(self, chunk_size=1):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise requests.ConnectionError("Connection broken: IncompleteRead")
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False
