"""Pengambil HTTP kecil dengan batas ukuran dan retry.

Dipakai verify_evidence.py dan archive.py. Hanya HTTPS. Respons 4xx (kecuali 429)
tidak di-retry; 5xx, 429, dan error jaringan di-retry dengan backoff.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

MAX_BYTES = 25 * 1024 * 1024
USER_AGENT = "promise-tracker/0.1 (+https://github.com/dwisusanto007/news-as-code)"


class FetchError(RuntimeError):
    """Gagal mengambil URL (jaringan, status HTTP, atau melebihi batas ukuran)."""


@dataclass(frozen=True)
class Response:
    url: str  # URL akhir setelah redirect
    body: bytes


Fetcher = Callable[[str], Response]


def fetch(
    url: str,
    *,
    timeout: float = 60,
    retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    opener: Callable | None = None,
) -> Response:
    """Ambil URL dan kembalikan (url akhir, isi). Melempar FetchError kalau gagal."""
    if not url.startswith("https://"):
        raise FetchError(f"hanya https yang diizinkan: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    open_url = opener or urllib.request.urlopen
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            with open_url(request, timeout=timeout) as resp:
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise FetchError(f"respons lebih besar dari {MAX_BYTES} byte: {url}")
                return Response(resp.geturl(), body)
        except FetchError:
            raise
        except urllib.error.HTTPError as exc:  # harus sebelum URLError (subclass)
            last_error = exc
            if exc.code < 500 and exc.code != 429:
                break  # kesalahan permanen, jangan di-retry
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < retries:
            sleep(backoff * attempt)

    raise FetchError(f"gagal mengambil {url}: {last_error}")
