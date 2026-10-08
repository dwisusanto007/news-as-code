"""Unit test untuk tools/build.py."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from tools import build, validate

TODAY = date(2026, 10, 8)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "promises"


@pytest.fixture
def promise() -> dict:
    return validate.load_yaml(DATA_DIR / "P-2026-0001.yaml")


def test_build_writes_expected_files(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "promises" / "P-2026-0001.html").exists()
    assert (tmp_path / "promises" / "P-2026-0002.html").exists()
    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["promises"]] == ["P-2026-0001", "P-2026-0002"]


def test_fictional_banner_shown(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "DATA CONTOH (FIKTIF)" in html


def test_invalid_data_aborts_build(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    bad = validate.load_yaml(DATA_DIR / "P-2026-0001.yaml")
    bad["status"] = "maybe"
    (src / "P-2026-0001.yaml").write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="build dibatalkan"):
        build.build(src, out, TODAY)
    assert not out.exists()  # tidak ada output parsial dari data tidak valid


def test_html_is_escaped(promise):
    promise["title"] = "<script>alert(1)</script> judul"
    html = build.render_promise(promise, TODAY)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_unsafe_url_not_rendered_as_href():
    assert build.safe_url("javascript:alert(1)") == "#"
    assert build.safe_url("data:text/html,x") == "#"
    assert build.safe_url("https://example.org/a") == "https://example.org/a"


def test_external_links_have_rel(promise):
    html = build.render_promise(promise, TODAY)
    assert 'rel="noopener noreferrer nofollow"' in html


def test_overdue_open_promise_flagged(promise):
    # P-0001 berstatus in_progress dengan deadline 2026-12-31.
    assert build.overdue_days(promise, date(2026, 12, 30)) is None
    assert build.overdue_days(promise, date(2027, 1, 10)) == 10


def test_overdue_ignores_final_status(promise):
    promise["status"] = "fulfilled"
    assert build.overdue_days(promise, date(2027, 6, 1)) is None


def test_overdue_without_deadline(promise):
    promise["promise"]["deadline"] = None
    assert build.overdue_days(promise, date(2030, 1, 1)) is None


def test_all_statuses_have_labels():
    schema = validate.load_schema()
    statuses = set(schema["properties"]["status"]["enum"])
    assert statuses == set(build.STATUS_LABELS)


def test_cli_returns_1_on_invalid(tmp_path, capsys):
    src = tmp_path / "empty"
    src.mkdir()
    code = build.main(["--data", str(src), "--out", str(tmp_path / "o"), "--today", "2026-10-08"])
    assert code == 1
    assert "build dibatalkan" in capsys.readouterr().err
