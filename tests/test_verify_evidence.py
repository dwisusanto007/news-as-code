"""Unit test untuk tools/verify_evidence.py dan tools/archive.py (fetcher palsu, tanpa jaringan)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from tools import archive, validate, verify_evidence
from tools.fetch import FetchError, Response

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "promises"
BODY = b"isi snapshot"
BODY_HASH = verify_evidence.sha256_hex(BODY)


@pytest.fixture
def real_promise() -> dict:
    """Janji non-fiktif dengan hash yang cocok dengan BODY."""
    data = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    data["fictional"] = False
    for e in data["evidence"]:
        e["sha256"] = BODY_HASH
    return data


def _fetcher(body: bytes = BODY, seen: list | None = None):
    def fetch(url: str) -> Response:
        if seen is not None:
            seen.append(url)
        return Response(url, body)

    return fetch


# --- raw_snapshot_url ---------------------------------------------------------

@pytest.mark.parametrize(
    "archive_url, expected",
    [
        (
            "https://web.archive.org/web/20260116000000/https://example.org/a",
            "https://web.archive.org/web/20260116000000id_/https://example.org/a",
        ),
        (
            "https://web.archive.org/web/20260116000000id_/https://example.org/a",
            "https://web.archive.org/web/20260116000000id_/https://example.org/a",
        ),
        (
            "https://web.archive.org/web/20260116000000/https://example.org/a?x=1&y=2",
            "https://web.archive.org/web/20260116000000id_/https://example.org/a?x=1&y=2",
        ),
        ("https://web.archive.org/web/https://example.org/a", None),  # bentuk "terbaru"
        ("https://archive.ph/AbCdE", None),
        ("https://perma.cc/ABCD-1234", None),
    ],
)
def test_raw_snapshot_url(archive_url, expected):
    assert verify_evidence.raw_snapshot_url(archive_url) == expected


# --- verify_promise -----------------------------------------------------------

def test_matching_hash_is_ok(real_promise):
    results = verify_evidence.verify_promise(real_promise, _fetcher())
    assert [r.status for r in results] == ["ok"] * len(real_promise["evidence"])


def test_fetches_raw_id_form(real_promise):
    seen: list[str] = []
    verify_evidence.verify_promise(real_promise, _fetcher(seen=seen))
    assert seen and all("id_/" in u for u in seen)


def test_hash_mismatch_detected(real_promise):
    results = verify_evidence.verify_promise(real_promise, _fetcher(b"isi berbeda"))
    assert {r.status for r in results} == {"mismatch"}


def test_fetch_failure_reported_as_error(real_promise):
    def failing(url):
        raise FetchError("putus")

    results = verify_evidence.verify_promise(real_promise, failing)
    assert {r.status for r in results} == {"error"}


def test_non_wayback_archive_is_manual(real_promise):
    real_promise["evidence"][0]["archive_url"] = "https://archive.ph/AbCdE"
    results = verify_evidence.verify_promise(real_promise, _fetcher())
    assert results[0].status == "manual"
    assert results[1].status == "ok"


def test_fictional_data_skipped(real_promise):
    real_promise["fictional"] = True
    assert verify_evidence.verify_promise(real_promise, _fetcher()) == []


def test_cli_exit_codes(tmp_path, real_promise, capsys):
    (tmp_path / "P-2026-0002.yaml").write_text(yaml.safe_dump(real_promise, allow_unicode=True), encoding="utf-8")
    assert verify_evidence.main(["--data", str(tmp_path)], fetcher=_fetcher()) == 0
    assert "0 bermasalah" in capsys.readouterr().out
    assert verify_evidence.main(["--data", str(tmp_path)], fetcher=_fetcher(b"lain")) == 1
    assert "MISMATCH" in capsys.readouterr().out


def test_repo_sample_data_is_skipped_entirely():
    # Semua data di repo saat ini fiktif: tidak ada yang diunduh.
    assert verify_evidence.verify_directory(DATA_DIR, _fetcher()) == []


# --- archive helper -----------------------------------------------------------

SOURCE = "https://contoh.go.id/siaran-pers"
SNAPSHOT = f"https://web.archive.org/web/20260116093015/{SOURCE}"


def _archive_fetcher(*, available: bool = True, saved_url: str = SNAPSHOT, seen: list | None = None):
    def fetch(url: str) -> Response:
        if seen is not None:
            seen.append(url)
        if url.startswith("https://archive.org/wayback/available"):
            payload = {"archived_snapshots": {"closest": {"available": available, "timestamp": "20260116093015", "url": "http://x"}}}
            if not available:
                payload = {"archived_snapshots": {}}
            return Response(url, json.dumps(payload).encode())
        if url.startswith("https://web.archive.org/save/"):
            return Response(saved_url, b"")
        if "id_/" in url:
            return Response(url, BODY)
        raise AssertionError(f"URL tak terduga: {url}")

    return fetch


def test_find_snapshot_returns_canonical_https_url():
    assert archive.find_snapshot(SOURCE, _archive_fetcher()) == SNAPSHOT


def test_find_snapshot_without_snapshot_suggests_save():
    with pytest.raises(FetchError, match="--save"):
        archive.find_snapshot(SOURCE, _archive_fetcher(available=False))


def test_find_snapshot_rejects_non_json():
    with pytest.raises(FetchError, match="JSON"):
        archive.find_snapshot(SOURCE, lambda url: Response(url, b"<html>"))


def test_save_snapshot_parses_redirect():
    assert archive.save_snapshot(SOURCE, _archive_fetcher()) == SNAPSHOT


def test_save_snapshot_rejects_unexpected_redirect():
    with pytest.raises(FetchError, match="snapshot"):
        archive.save_snapshot(SOURCE, _archive_fetcher(saved_url="https://web.archive.org/web/https://x.test/"))


def test_make_evidence_fields_end_to_end():
    fields = archive.make_evidence_fields(SOURCE, save=False, fetcher=_archive_fetcher())
    assert fields == {"archive_url": SNAPSHOT, "archived_at": "2026-01-16", "sha256": BODY_HASH}


def test_output_passes_validator_archive_rules():
    fields = archive.make_evidence_fields(SOURCE, save=True, fetcher=_archive_fetcher())
    match = validate.WAYBACK_PATH.match(urlparse(fields["archive_url"]).path)
    assert match and match.group(1)[:8] == fields["archived_at"].replace("-", "")


def test_hashes_raw_snapshot_bytes():
    seen: list[str] = []
    archive.make_evidence_fields(SOURCE, save=False, fetcher=_archive_fetcher(seen=seen))
    assert seen[-1] == f"https://web.archive.org/web/20260116093015id_/{SOURCE}"


@pytest.mark.parametrize("bad", ["ftp://x.test/a", "bukan url", "https://", "https://x.test/a b"])
def test_invalid_source_url_rejected(bad):
    with pytest.raises(ValueError):
        archive.make_evidence_fields(bad, save=False, fetcher=_archive_fetcher())


def test_archive_cli(capsys):
    assert archive.main([SOURCE], fetcher=_archive_fetcher()) == 0
    out = capsys.readouterr().out
    assert f"archive_url: {SNAPSHOT}" in out
    assert 'archived_at: "2026-01-16"' in out
    assert f'sha256: "{BODY_HASH}"' in out


def test_archive_cli_failure_exit_code(capsys):
    assert archive.main([SOURCE], fetcher=_archive_fetcher(available=False)) == 1
    assert "Gagal" in capsys.readouterr().err
