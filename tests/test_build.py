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


# =============================================================================
# Skema v2: metrik, hak jawab, koreksi, relasi, program, ClaimReview
# =============================================================================
import re  # noqa: E402

PROGRAMS_DIR = Path(__file__).resolve().parent.parent / "data" / "programs"
BASE = "https://contoh.github.io/news-as-code"


def _real_site(tmp_path: Path, mutate=None, **build_kwargs) -> Path:
    """Bangun situs dari janji NYATA (non-fiktif) berstatus akhir, dengan program non-fiktif."""
    data = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    data["fictional"] = False
    for e in data["evidence"]:
        e["sha256"] = "a" * 64
    data["official"]["wikidata_id"] = "Q42"
    if mutate:
        mutate(data)
    src = tmp_path / "promises"
    progs = tmp_path / "programs"
    src.mkdir(parents=True)
    progs.mkdir(parents=True)
    (src / "P-2026-0002.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    program = {
        "slug": data["program"], "name": "Program Nyata", "description": "Deskripsi program nyata contoh.",
        "institution": "Instansi",
    }
    (progs / f"{data['program']}.yaml").write_text(yaml.safe_dump(program), encoding="utf-8")
    out = tmp_path / "out"
    build.build(src, out, TODAY, programs_dir=progs, **build_kwargs)
    return out


def _jsonld(html: str) -> dict:
    match = re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', html, re.S)
    assert match, "JSON-LD tidak ditemukan"
    return json.loads(match.group(1))


# --- format angka & progres ---------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [(82.9, "82,9"), (59.86, "59,86"), (50, "50"), (20.5, "20,5"), (0, "0"), (1234567, "1234567"), (76.4512, "76,45")],
)
def test_fmt_number(value, expected):
    assert build.fmt_number(value) == expected


def test_metric_progress_with_revised_target():
    metric = {
        "target": {"value": 80}, "target_revisions": [{"value": 50}],
        "observations": [{"date": "2026-01-01", "value": 20, "quality": "reported"}, {"date": "2026-02-01", "value": 40, "quality": "provisional"}],
    }
    prog = build.metric_progress(metric)
    assert prog["value"] == 40 and prog["pct"] == 50 and prog["revised_target"] == 50 and prog["revised_pct"] == 80
    assert prog["quality"] == "provisional"


def test_metric_progress_without_revision():
    metric = {"target": {"value": 50}, "observations": [{"date": "2026-01-01", "value": 21, "quality": "reported"}]}
    prog = build.metric_progress(metric)
    assert prog["pct"] == 42 and prog["revised_target"] is None and prog["revised_pct"] is None


# --- halaman ------------------------------------------------------------------

def test_build_writes_program_pages(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    for slug in ("jalan-kabupaten", "puskesmas-24-jam", "mbg"):
        assert (tmp_path / "programs" / f"{slug}.html").exists()
    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert data["schema"] == "v2" and data["last_reviewed_on"] == "2026-08-30"
    assert {p["slug"] for p in data["programs"]} >= {"mbg", "jalan-kabupaten"}


def test_index_separates_review_date_from_build_date(tmp_path):
    build.build(DATA_DIR, tmp_path, date(2026, 10, 8))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "data terakhir direview 2026-08-30" in html
    assert "situs dibangun 2026-10-08" in html
    assert "diperbarui" not in html


def test_index_shows_progress_and_commitment(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "21 / 50 km (42%)" in html  # P-0001
    assert "3 / 12 puskesmas (25%)" in html  # P-0002
    assert "Janji tegas" in html and ">Target<" in html


def test_program_page_lists_its_promises_only(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    html = (tmp_path / "programs" / "jalan-kabupaten.html").read_text(encoding="utf-8")
    assert "P-2026-0001.html" in html and "P-2026-0002.html" not in html


def test_program_without_promises_says_so(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    assert "Belum ada janji untuk program ini" in (tmp_path / "programs" / "mbg.html").read_text(encoding="utf-8")


def test_promise_page_renders_metrics_response_corrections(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    html = (tmp_path / "promises" / "P-2026-0002.html").read_text(encoding="utf-8")
    assert "<h2>Metrik</h2>" in html and "Target awal: <strong>12</strong>" in html
    assert "25%" in html
    assert "Tidak ada tanggapan" in html and "diminta 2026-07-05" in html
    assert "Koreksi contoh" in html


def test_disputed_and_revised_target_are_visible(promise):
    m = promise["metrics"][0]
    m["observations"][0]["quality"] = "disputed"
    m["target_revisions"] = [{"date": "2026-09-01", "value": 40, "evidence_id": "E3", "note": "Target diturunkan."}]
    html = build.render_promise(promise, TODAY)
    assert 'class="disputed"' in html and "Dipersoalkan" in html
    assert "Target direvisi menjadi <strong>40</strong>" in html and "Target diturunkan." in html


@pytest.mark.parametrize(
    "response, expected",
    [
        ({"status": "not_yet_sought"}, "Belum dimintai tanggapan"),
        ({"status": "requested", "requested_at": "2026-07-05"}, "Tanggapan diminta, menunggu"),
        ({"status": "declined", "requested_at": "2026-07-05"}, "Menolak memberi tanggapan"),
        (
            {"status": "received", "received_at": "2026-07-10", "summary": "Kami keberatan dengan penilaian ini.", "evidence_id": "E2"},
            "Kami keberatan dengan penilaian ini.",
        ),
    ],
)
def test_response_states_rendered(promise, response, expected):
    promise["response"] = response
    assert expected in build.render_promise(promise, TODAY)


def test_missing_response_defaults_to_not_sought(promise):
    promise.pop("response", None)
    assert "Belum dimintai tanggapan" in build.render_promise(promise, TODAY)


def test_no_corrections_message(promise):
    promise.pop("corrections", None)
    assert "Belum ada koreksi" in build.render_promise(promise, TODAY)


def test_related_links_only_to_known_ids(promise):
    promise["related"] = [{"id": "P-2026-0002", "relation": "follows"}, {"id": "P-2026-0777", "relation": "part_of"}]
    html = build.render_promise(promise, TODAY, known_ids={"P-2026-0001", "P-2026-0002"})
    assert 'href="P-2026-0002.html"' in html and 'href="P-2026-0777.html"' not in html
    assert "Lanjutan dari" in html and "Bagian dari" in html and "P-2026-0777" in html


def test_new_user_fields_are_escaped(promise):
    evil = "<script>alert(1)</script>"
    promise["metrics"][0]["name"] = evil
    promise["metrics"][0]["observations"][0]["note"] = evil
    promise["response"] = {"status": "received", "received_at": "2026-07-10", "summary": evil, "evidence_id": "E2"}
    promise["corrections"] = [{"date": "2026-07-20", "summary": evil}]
    promise["evidence"][0]["quote"] = evil
    promise["promise"]["on_behalf_of"] = evil
    promise["related"] = [{"id": "P-2026-0002", "relation": "follows"}]
    html = build.render_promise(promise, TODAY)
    assert evil not in html and html.count("&lt;script&gt;") >= 6


def test_noindex_only_for_fictional(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY)
    assert 'name="robots" content="noindex"' in (tmp_path / "promises" / "P-2026-0001.html").read_text(encoding="utf-8")
    out = _real_site(tmp_path / "real")
    assert "noindex" not in (out / "promises" / "P-2026-0002.html").read_text(encoding="utf-8")


# --- ClaimReview JSON-LD ------------------------------------------------------

def test_no_claim_review_without_base_url(tmp_path):
    out = _real_site(tmp_path)
    assert "ld+json" not in (out / "promises" / "P-2026-0002.html").read_text(encoding="utf-8")


def test_no_claim_review_for_fictional_even_with_base_url(tmp_path):
    build.build(DATA_DIR, tmp_path, TODAY, base_url=BASE)
    assert "ld+json" not in (tmp_path / "promises" / "P-2026-0002.html").read_text(encoding="utf-8")


def test_claim_review_emitted_for_real_final_promise(tmp_path):
    out = _real_site(tmp_path, base_url=BASE + "/", site_name="Pelacak Janji")
    ld = _jsonld((out / "promises" / "P-2026-0002.html").read_text(encoding="utf-8"))
    assert ld["@type"] == "ClaimReview"
    assert ld["url"] == f"{BASE}/promises/P-2026-0002.html"  # slash ganda dibuang
    assert ld["datePublished"] == "2026-07-15"
    assert ld["author"] == {"@type": "Organization", "name": "Pelacak Janji", "url": BASE}
    assert ld["claimReviewed"].startswith("Seluruh puskesmas")
    assert ld["itemReviewed"]["datePublished"] == "2026-02-10"
    assert ld["itemReviewed"]["author"]["sameAs"] == "https://www.wikidata.org/wiki/Q42"
    assert ld["itemReviewed"]["appearance"]["url"] == "https://example.org/rekaan/konferensi-pers-kesehatan"
    assert ld["reviewRating"] == {"@type": "Rating", "ratingValue": 1, "bestRating": 5, "worstRating": 1, "alternateName": "Tidak ditepati"}


@pytest.mark.parametrize("status, rating", [("fulfilled", 5), ("partially_fulfilled", 3), ("broken", 1)])
def test_claim_review_rating_mapping(status, rating):
    p = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    p["fictional"] = False
    p["status"] = status
    assert build.claim_review_jsonld(p, BASE, "Situs")["reviewRating"]["ratingValue"] == rating


@pytest.mark.parametrize("status", ["not_started", "in_progress", "unverifiable"])
def test_no_claim_review_for_non_final_status(status):
    p = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    p["fictional"] = False
    p["status"] = status
    assert build.claim_review_jsonld(p, BASE, "Situs") is None


def test_json_ld_cannot_break_out_of_script_tag(tmp_path):
    evil = "</script><img src=x onerror=alert(1)>"

    def mutate(data):
        data["promise"]["statement"] = evil + " janji panjang cukup"

    out = _real_site(tmp_path, mutate=mutate, base_url=BASE)
    html = (out / "promises" / "P-2026-0002.html").read_text(encoding="utf-8")
    head = html.split("</head>")[0]
    assert head.count("</script>") == 1  # hanya penutup milik JSON-LD
    assert "<img src=x" not in head
    assert _jsonld(html)["claimReviewed"].startswith(evil)  # data tetap utuh setelah decode


def test_invalid_base_url_rejected(tmp_path):
    with pytest.raises(ValueError, match="base_url"):
        build.build(DATA_DIR, tmp_path, TODAY, base_url="javascript:alert(1)")


def test_cli_accepts_base_url(tmp_path):
    assert build.main(["--out", str(tmp_path), "--today", "2026-10-08", "--base-url", BASE, "--site-name", "X"]) == 0
