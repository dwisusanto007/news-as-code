"""Cocokkan `review.reviewers` di YAML dengan approval PR yang sebenarnya.

Tanpa ini, daftar reviewer hanyalah teks yang bisa ditulis siapa saja. Aturan:
  - tiap reviewer yang tercantum harus punya review APPROVED terakhir pada PR ini
  - reviewer tidak boleh sama dengan penulis PR
Data fiktif dilewati. Hanya file janji yang berubah di PR yang diperiksa.

Pemakaian (di CI, event pull_request):
    GITHUB_TOKEN=... python -m tools.check_reviewers --repo owner/nama --pr 12
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from tools import validate

ROOT = Path(__file__).resolve().parent.parent
_PROMISE_PATH = re.compile(r"^data/promises/P-[0-9]{4}-[0-9]{4}\.yaml$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# Review yang mengubah status persetujuan. COMMENTED/PENDING tidak membatalkan approval.
_DECISIVE = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}

JsonGetter = Callable[[str], list | dict]


def approved_logins(reviews: list[dict]) -> set[str]:
    """Login (huruf kecil) yang review keputusannya terakhir adalah APPROVED."""
    latest: dict[str, str] = {}
    for review in reviews:  # API mengembalikan urutan kronologis
        login = ((review.get("user") or {}).get("login") or "").lower()
        state = review.get("state")
        if login and state in _DECISIVE:
            latest[login] = state
    return {login for login, state in latest.items() if state == "APPROVED"}


def changed_promise_paths(files: list[dict]) -> list[str]:
    """Path file janji yang ditambah/diubah di PR (bukan yang dihapus)."""
    return [
        f["filename"]
        for f in files
        if f.get("status") != "removed" and _PROMISE_PATH.match(f.get("filename", ""))
    ]


def check(promises: list[dict], pr_author: str, reviews: list[dict]) -> list[str]:
    """Kembalikan daftar pelanggaran. Kosong berarti reviewer sesuai approval PR."""
    approved = approved_logins(reviews)
    author = pr_author.lower()
    errors: list[str] = []
    for data in promises:
        if data.get("fictional"):
            continue
        reviewers = data.get("review", {}).get("reviewers", [])
        for handle in reviewers:
            low = handle.lower()
            if low == author:
                errors.append(f"{data['id']}: reviewer '{handle}' adalah penulis PR; reviewer harus orang lain")
            elif low not in approved:
                errors.append(f"{data['id']}: reviewer '{handle}' belum meng-approve PR ini")
    return errors


def github_get_all(url: str, token: str) -> list | dict:
    """GET ke GitHub API; untuk endpoint list, ikuti paginasi (100 per halaman)."""
    results: list = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        request = urllib.request.Request(
            f"{url}{sep}per_page=100&page={page}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "promise-tracker-check-reviewers",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310 (host tetap api.github.com)
            payload = json.loads(resp.read())
        if isinstance(payload, dict):
            return payload
        results += payload
        if len(payload) < 100:
            return results
        page += 1


def run(repo: str, pr: int, token: str, get: JsonGetter | None = None) -> list[str]:
    """Ambil data PR dari GitHub dan kembalikan daftar pelanggaran."""
    if not _REPO.match(repo):
        raise ValueError(f"format repo tidak valid: {repo!r}")
    getter: JsonGetter = get or (lambda url: github_get_all(url, token))
    base = f"https://api.github.com/repos/{repo}/pulls/{pr}"

    pr_info = getter(base)
    author = (pr_info.get("user") or {}).get("login") if isinstance(pr_info, dict) else None
    if not author:
        raise ValueError("tidak bisa menentukan penulis PR")

    promises = []
    for rel_path in changed_promise_paths(getter(f"{base}/files")):  # type: ignore[arg-type]
        path = ROOT / rel_path
        if path.is_file():
            promises.append(validate.load_yaml(path))
    return check(promises, author, getter(f"{base}/reviews"))  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cocokkan reviewer di YAML dengan approval PR")
    parser.add_argument("--repo", required=True, help="owner/nama")
    parser.add_argument("--pr", required=True, type=int)
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN tidak diatur", file=sys.stderr)
        return 1
    try:
        errors = run(args.repo, args.pr, token)
    except (ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"Gagal memeriksa reviewer: {exc}", file=sys.stderr)
        return 1

    if errors:
        for msg in errors:
            print(f"- {msg}")
        print(f"\nGAGAL: {len(errors)} pelanggaran")
        return 1
    print("OK: reviewer sesuai approval PR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
