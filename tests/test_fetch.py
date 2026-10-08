"""Unit test untuk tools/fetch.py (tanpa jaringan: opener palsu)."""
from __future__ import annotations

import urllib.error

import pytest

from tools import fetch as fetch_mod
from tools.fetch import FetchError, Response, fetch


class _FakeResp:
    def __init__(self, body: bytes, url: str = "https://x.test/final"):
        self._body, self._url = body, url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._body if n < 0 else self._body[:n]

    def geturl(self) -> str:
        return self._url


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test", code, "err", {}, None)  # type: ignore[arg-type]


def test_rejects_non_https():
    with pytest.raises(FetchError, match="https"):
        fetch("http://x.test/a")


def test_returns_final_url_and_body():
    resp = fetch("https://x.test/a", opener=lambda req, timeout: _FakeResp(b"isi", "https://x.test/redirected"))
    assert resp == Response("https://x.test/redirected", b"isi")


def test_retries_on_5xx_then_succeeds():
    calls, sleeps = [], []

    def opener(req, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(503)
        return _FakeResp(b"ok")

    resp = fetch("https://x.test/a", opener=opener, sleep=sleeps.append, backoff=2.0)
    assert resp.body == b"ok"
    assert len(calls) == 3
    assert sleeps == [2.0, 4.0]  # backoff bertambah per percobaan


def test_retries_on_429():
    calls = []

    def opener(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise _http_error(429)
        return _FakeResp(b"ok")

    assert fetch("https://x.test/a", opener=opener, sleep=lambda s: None).body == b"ok"


def test_does_not_retry_404():
    calls = []

    def opener(req, timeout):
        calls.append(1)
        raise _http_error(404)

    with pytest.raises(FetchError):
        fetch("https://x.test/a", opener=opener, sleep=lambda s: None)
    assert len(calls) == 1


def test_gives_up_after_retries_on_network_error():
    calls = []

    def opener(req, timeout):
        calls.append(1)
        raise urllib.error.URLError("putus")

    with pytest.raises(FetchError, match="putus"):
        fetch("https://x.test/a", opener=opener, sleep=lambda s: None, retries=3)
    assert len(calls) == 3


def test_oversize_response_rejected(monkeypatch):
    monkeypatch.setattr(fetch_mod, "MAX_BYTES", 10)
    with pytest.raises(FetchError, match="lebih besar"):
        fetch("https://x.test/a", opener=lambda req, timeout: _FakeResp(b"x" * 11))
