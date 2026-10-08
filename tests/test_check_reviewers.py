"""Unit test untuk tools/check_reviewers.py (GitHub API dipalsukan)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tools import check_reviewers as cr
from tools import validate

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "promises"


def review(login: str, state: str) -> dict:
    return {"user": {"login": login}, "state": state}


def promise(reviewers: list[str], *, fictional: bool = False, pid: str = "P-2026-0002") -> dict:
    return {"id": pid, "fictional": fictional, "review": {"reviewers": reviewers}}


# --- approved_logins ----------------------------------------------------------

def test_latest_decisive_review_wins():
    reviews = [review("Ani", "APPROVED"), review("ani", "CHANGES_REQUESTED"), review("budi", "APPROVED")]
    assert cr.approved_logins(reviews) == {"budi"}


def test_comment_does_not_cancel_approval():
    assert cr.approved_logins([review("ani", "APPROVED"), review("ani", "COMMENTED")]) == {"ani"}


def test_dismissed_approval_not_counted():
    assert cr.approved_logins([review("ani", "APPROVED"), review("ani", "DISMISSED")]) == set()


def test_approval_after_changes_requested_counts():
    assert cr.approved_logins([review("ani", "CHANGES_REQUESTED"), review("ani", "APPROVED")]) == {"ani"}


def test_ghost_user_ignored():
    assert cr.approved_logins([{"user": None, "state": "APPROVED"}]) == set()


# --- changed_promise_paths ----------------------------------------------------

def test_changed_paths_only_promise_files_not_removed():
    files = [
        {"filename": "data/promises/P-2026-0002.yaml", "status": "modified"},
        {"filename": "data/promises/P-2026-0003.yaml", "status": "removed"},
        {"filename": "data/drafts/P-2026-0004.yaml", "status": "added"},
        {"filename": "README.md", "status": "modified"},
        {"filename": "data/promises/notes.yaml", "status": "added"},
    ]
    assert cr.changed_promise_paths(files) == ["data/promises/P-2026-0002.yaml"]


# --- check --------------------------------------------------------------------

def test_all_reviewers_approved_is_ok():
    reviews = [review("ani", "APPROVED"), review("budi", "APPROVED")]
    assert cr.check([promise(["ani", "budi"])], "citra", reviews) == []


def test_reviewer_without_approval_flagged():
    errors = cr.check([promise(["ani", "budi"])], "citra", [review("ani", "APPROVED")])
    assert len(errors) == 1 and "budi" in errors[0] and "belum meng-approve" in errors[0]


def test_author_cannot_be_reviewer_even_if_approved():
    errors = cr.check([promise(["Citra", "ani"])], "citra", [review("citra", "APPROVED"), review("ani", "APPROVED")])
    assert len(errors) == 1 and "penulis PR" in errors[0]


def test_case_insensitive_handles():
    assert cr.check([promise(["ANI", "Budi"])], "citra", [review("ani", "APPROVED"), review("BUDI", "APPROVED")]) == []


def test_fictional_data_skipped():
    assert cr.check([promise(["siapa-saja"], fictional=True)], "citra", []) == []


def test_no_reviewers_is_not_this_tools_job():
    # Jumlah minimum reviewer ditegakkan validate.py; di sini tidak ada yang bisa dicocokkan.
    assert cr.check([promise([])], "citra", []) == []


# --- run (API palsu) ----------------------------------------------------------

def _getter(*, author="citra", files=None, reviews=None):
    def get(url: str):
        if url.endswith("/files"):
            return files or []
        if url.endswith("/reviews"):
            return reviews or []
        return {"user": {"login": author}}

    return get


@pytest.fixture
def repo_with_real_promise(tmp_path, monkeypatch):
    data = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    data["fictional"] = False
    data["review"]["reviewers"] = ["ani", "budi"]
    target = tmp_path / "data" / "promises"
    target.mkdir(parents=True)
    (target / "P-2026-0002.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    return tmp_path


FILES = [{"filename": "data/promises/P-2026-0002.yaml", "status": "modified"}]


def test_run_ok(repo_with_real_promise):
    getter = _getter(files=FILES, reviews=[review("ani", "APPROVED"), review("budi", "APPROVED")])
    assert cr.run("o/r", 1, "t", get=getter) == []


def test_run_flags_missing_approval(repo_with_real_promise):
    getter = _getter(files=FILES, reviews=[review("ani", "APPROVED")])
    errors = cr.run("o/r", 1, "t", get=getter)
    assert len(errors) == 1 and "budi" in errors[0]


def test_run_ignores_unchanged_files(repo_with_real_promise):
    assert cr.run("o/r", 1, "t", get=_getter(files=[{"filename": "README.md", "status": "modified"}])) == []


def test_run_skips_file_missing_in_checkout(repo_with_real_promise):
    files = [{"filename": "data/promises/P-2026-0099.yaml", "status": "added"}]
    assert cr.run("o/r", 1, "t", get=_getter(files=files)) == []


@pytest.mark.parametrize("repo", ["bukan-repo", "a/b/c", "o/r; rm -rf", ""])
def test_run_rejects_bad_repo(repo):
    with pytest.raises(ValueError, match="repo"):
        cr.run(repo, 1, "t", get=_getter())


def test_run_requires_pr_author():
    with pytest.raises(ValueError, match="penulis"):
        cr.run("o/r", 1, "t", get=lambda url: {"user": None})


def test_main_requires_token(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cr.main(["--repo", "o/r", "--pr", "1"]) == 1
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_main_reports_violations(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(cr, "run", lambda repo, pr, token: ["P-2026-0002: reviewer 'x' belum meng-approve PR ini"])
    assert cr.main(["--repo", "o/r", "--pr", "1"]) == 1
    assert "GAGAL" in capsys.readouterr().out


# --- paginasi -----------------------------------------------------------------

class _Page:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_github_get_all_follows_pagination(monkeypatch):
    pages = [list(range(100)), [100]]
    requested: list[str] = []

    def fake_urlopen(request, timeout):
        requested.append(request.full_url)
        assert request.get_header("Authorization") == "Bearer tok"
        return _Page(pages[len(requested) - 1])

    monkeypatch.setattr(cr.urllib.request, "urlopen", fake_urlopen)
    result = cr.github_get_all("https://api.github.com/repos/o/r/pulls/1/reviews", "tok")
    assert result == list(range(101))
    assert requested[0].endswith("per_page=100&page=1") and requested[1].endswith("per_page=100&page=2")


def test_github_get_all_returns_dict_directly(monkeypatch):
    monkeypatch.setattr(cr.urllib.request, "urlopen", lambda request, timeout: _Page({"user": {"login": "x"}}))
    assert cr.github_get_all("https://api.github.com/repos/o/r/pulls/1", "tok") == {"user": {"login": "x"}}
