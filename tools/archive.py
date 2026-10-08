"""Skrip bantu kontributor: arsipkan URL ke Wayback dan hitung sha256 snapshot.

Mencetak tiga baris siap tempel untuk blok `evidence` di YAML:
    archive_url, archived_at, sha256

Alur:
  tanpa --save : cari snapshot terdekat yang sudah ada (availability API)
  dengan --save: minta Wayback membuat snapshot baru (Save Page Now)
Lalu snapshot diambil dalam bentuk mentah (`id_`) dan di-hash.

Butuh jaringan; jalankan di komputer sendiri, bukan di CI.
Catatan: logika diuji dengan fetcher palsu; belum diuji terhadap layanan Wayback sungguhan.

Pemakaian:
    python -m tools.archive https://contoh.go.id/siaran-pers [--save]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from urllib.parse import quote, urlparse

from tools.fetch import FetchError, Fetcher, fetch
from tools.verify_evidence import raw_snapshot_url, sha256_hex

_SNAPSHOT_URL = re.compile(r"^/web/(\d{14})(?:id_|if_|im_|js_|cs_)?/(https?://.+)$")


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or re.search(r"\s", url):
        raise ValueError(f"URL tidak valid: {url!r}")


def _canonical(timestamp: str, original: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original}"


def _parse_snapshot(archive_url: str) -> tuple[str, str] | None:
    """(timestamp, url_asli) dari URL snapshot Wayback bertimestamp, atau None."""
    parsed = urlparse(archive_url)
    if (parsed.hostname or "").lower() != "web.archive.org":
        return None
    match = _SNAPSHOT_URL.match(parsed.path + (f"?{parsed.query}" if parsed.query else ""))
    return (match.group(1), match.group(2)) if match else None


def find_snapshot(url: str, fetcher: Fetcher = fetch) -> str:
    """Cari snapshot Wayback terdekat. Melempar FetchError kalau belum ada."""
    api = f"https://archive.org/wayback/available?url={quote(url, safe='')}"
    try:
        payload = json.loads(fetcher(api).body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(f"respons availability API bukan JSON: {exc}") from exc
    closest = (payload.get("archived_snapshots") or {}).get("closest") or {}
    timestamp = closest.get("timestamp")
    if not closest.get("available") or not isinstance(timestamp, str) or not re.fullmatch(r"\d{14}", timestamp):
        raise FetchError("belum ada snapshot; jalankan lagi dengan --save")
    return _canonical(timestamp, url)


def save_snapshot(url: str, fetcher: Fetcher = fetch) -> str:
    """Minta Wayback membuat snapshot baru dan kembalikan URL snapshot-nya."""
    final = fetcher(f"https://web.archive.org/save/{url}").url
    parts = _parse_snapshot(final)
    if parts is None:
        raise FetchError(f"Wayback tidak mengembalikan URL snapshot (dapat: {final})")
    return _canonical(*parts)


def make_evidence_fields(url: str, *, save: bool, fetcher: Fetcher = fetch) -> dict[str, str]:
    """Hasilkan archive_url, archived_at, sha256 untuk satu URL sumber."""
    _validate_source_url(url)
    archive_url = save_snapshot(url, fetcher) if save else find_snapshot(url, fetcher)
    parts = _parse_snapshot(archive_url)
    raw = raw_snapshot_url(archive_url)
    if parts is None or raw is None:
        raise FetchError(f"bukan snapshot Wayback bertimestamp: {archive_url}")
    body = fetcher(raw).body
    try:
        archived_at = datetime.strptime(parts[0][:8], "%Y%m%d").date().isoformat()
    except ValueError as exc:
        raise FetchError(f"timestamp snapshot tidak valid: {parts[0]}") from exc
    return {"archive_url": archive_url, "archived_at": archived_at, "sha256": sha256_hex(body)}


def main(argv: list[str] | None = None, fetcher: Fetcher = fetch) -> int:
    parser = argparse.ArgumentParser(description="Arsipkan URL dan hitung sha256 untuk blok evidence")
    parser.add_argument("url")
    parser.add_argument("--save", action="store_true", help="buat snapshot baru (Save Page Now)")
    args = parser.parse_args(argv)
    try:
        fields = make_evidence_fields(args.url, save=args.save, fetcher=fetcher)
    except (ValueError, FetchError) as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 1
    print(f"    archive_url: {fields['archive_url']}")
    print(f'    archived_at: "{fields["archived_at"]}"')
    print(f'    sha256: "{fields["sha256"]}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
