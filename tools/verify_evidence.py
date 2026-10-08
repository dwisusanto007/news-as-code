"""Verifikasi bukti: ambil ulang snapshot arsip dan cocokkan sha256-nya.

Hanya snapshot Wayback bertimestamp yang bisa diverifikasi otomatis, lewat URL
bentuk mentah `id_` (byte asli tanpa penulisan ulang Wayback). Arsip lain
(archive.ph, perma.cc, ...) dilaporkan sebagai 'manual': reviewer harus
memeriksa sendiri.

Data fiktif dilewati. Exit code 1 kalau ada hash tidak cocok atau gagal ambil.

Pemakaian:
    python -m tools.verify_evidence [--data data/promises]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from tools import validate
from tools.fetch import FetchError, Fetcher, fetch

_WAYBACK = re.compile(r"^/web/(\d{14})(?:id_|if_|im_|js_|cs_)?/(https?://.+)$")


@dataclass(frozen=True)
class Result:
    promise_id: str
    evidence_id: str
    status: str  # ok | mismatch | manual | error
    detail: str = ""


def raw_snapshot_url(archive_url: str) -> str | None:
    """URL snapshot mentah (`id_`) untuk Wayback bertimestamp; None untuk layanan lain."""
    parsed = urlparse(archive_url)
    if (parsed.hostname or "").lower() != "web.archive.org":
        return None
    rest = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    match = _WAYBACK.match(rest)
    if not match:
        return None
    timestamp, original = match.groups()
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def verify_promise(data: dict, fetcher: Fetcher = fetch) -> list[Result]:
    """Periksa semua bukti satu janji. Data fiktif menghasilkan daftar kosong."""
    if data.get("fictional"):
        return []
    results: list[Result] = []
    for evidence in data["evidence"]:
        pid, eid = data["id"], evidence["id"]
        raw_url = raw_snapshot_url(evidence["archive_url"])
        if raw_url is None:
            results.append(Result(pid, eid, "manual", "arsip non-Wayback bertimestamp; periksa manual"))
            continue
        try:
            body = fetcher(raw_url).body
        except FetchError as exc:
            results.append(Result(pid, eid, "error", str(exc)))
            continue
        actual = sha256_hex(body)
        if actual == evidence["sha256"]:
            results.append(Result(pid, eid, "ok"))
        else:
            results.append(Result(pid, eid, "mismatch", f"sha256 di data {evidence['sha256']} != hasil unduhan {actual}"))
    return results


def verify_directory(data_dir: Path, fetcher: Fetcher = fetch) -> list[Result]:
    results: list[Result] = []
    for path in sorted(data_dir.glob("*.yaml")):
        results += verify_promise(validate.load_yaml(path), fetcher)
    return results


def main(argv: list[str] | None = None, fetcher: Fetcher = fetch) -> int:
    parser = argparse.ArgumentParser(description="Verifikasi hash bukti terarsip")
    parser.add_argument("--data", type=Path, default=validate.DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)

    try:
        results = verify_directory(args.data, fetcher)
    except (yaml.YAMLError, ValueError, OSError) as exc:
        print(f"Gagal membaca data: {exc}", file=sys.stderr)
        return 1

    for r in results:
        suffix = f" - {r.detail}" if r.detail else ""
        print(f"[{r.status.upper():8}] {r.promise_id} {r.evidence_id}{suffix}")
    bad = [r for r in results if r.status in {"mismatch", "error"}]
    manual = sum(1 for r in results if r.status == "manual")
    print(f"\n{len(results)} bukti diperiksa: {len(bad)} bermasalah, {manual} perlu cek manual")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
