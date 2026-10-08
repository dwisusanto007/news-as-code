"""Unit test untuk tools/validate.py."""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import pytest
import yaml

from tools import validate

TODAY = date(2026, 10, 8)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "promises"


@pytest.fixture
def valid() -> dict:
    """Janji valid dengan status akhir (broken) yang memenuhi semua standar bukti."""
    return validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")


def errors_for(data: dict) -> list[str]:
    return validate.validate_data(data, TODAY)


def has(errors: list[str], fragment: str) -> bool:
    return any(fragment in e for e in errors)


# --- Data contoh -------------------------------------------------------------

def test_example_data_is_valid():
    assert validate.validate_directory(DATA_DIR, TODAY) == {}


# --- Lapis schema ------------------------------------------------------------

def test_missing_required_field(valid):
    del valid["official"]
    assert has(errors_for(valid), "'official' is a required property")


def test_unknown_field_rejected(valid):
    # Mencegah data pribadi/tak terduga menyelinap masuk.
    valid["official"]["home_address"] = "Jl. Rahasia 1"
    assert has(errors_for(valid), "home_address")


def test_non_public_official_rejected(valid):
    valid["official"]["public_official"] = False
    assert errors_for(valid)


def test_javascript_url_rejected(valid):
    valid["evidence"][0]["url"] = "javascript:alert(1)"
    assert has(errors_for(valid), "evidence.0.url")


def test_invalid_status_rejected(valid):
    valid["status"] = "maybe"
    assert has(errors_for(valid), "status")


def test_bad_id_format_rejected(valid):
    valid["id"] = "janji-1"
    assert has(errors_for(valid), "id")


# --- Lapis editorial: referensi & tanggal ------------------------------------

def test_source_evidence_must_exist(valid):
    valid["promise"]["source_evidence_id"] = "E99"
    assert has(errors_for(valid), "source_evidence_id 'E99'")


def test_timeline_unknown_evidence(valid):
    valid["timeline"][0]["evidence_ids"] = ["E99"]
    assert has(errors_for(valid), "evidence 'E99'")


def test_duplicate_evidence_ids(valid):
    valid["evidence"][1]["id"] = "E1"
    assert has(errors_for(valid), "duplikat")


def test_deadline_before_made_at(valid):
    valid["promise"]["deadline"] = "2026-01-01"
    assert has(errors_for(valid), "deadline lebih awal")


def test_future_timeline_date(valid):
    valid["timeline"].append(
        {"date": "2026-12-01", "kind": "update", "summary": "Kejadian di masa depan", "evidence_ids": ["E1"]}
    )
    assert has(errors_for(valid), "masa depan")


def test_timeline_must_be_chronological(valid):
    valid["timeline"].reverse()
    assert has(errors_for(valid), "tidak urut kronologis")


def test_timeline_before_promise_date(valid):
    valid["timeline"][0]["date"] = "2026-01-01"
    assert has(errors_for(valid), "lebih awal dari tanggal janji")


def test_impossible_calendar_date(valid):
    valid["promise"]["made_at"] = "2026-02-30"
    assert has(errors_for(valid), "bukan tanggal valid")


def test_archived_before_published(valid):
    valid["evidence"][0]["archived_at"] = "2026-01-01"
    assert has(errors_for(valid), "archived_at lebih awal")


# --- Lapis editorial: kualitas bukti -----------------------------------------

def test_archive_url_must_be_archive_host(valid):
    valid["evidence"][0]["archive_url"] = "https://example.org/salinan-sendiri"
    assert has(errors_for(valid), "layanan arsip")


def test_placeholder_hash_rejected_for_real_data(valid):
    valid["fictional"] = False
    assert has(errors_for(valid), "placeholder")


def test_placeholder_hash_allowed_for_fictional(valid):
    assert valid["fictional"] is True
    assert not has(errors_for(valid), "placeholder")


# --- Lapis editorial: standar status akhir -----------------------------------

def test_final_status_needs_two_publishers(valid):
    for e in valid["evidence"]:
        e["publisher"] = "Satu Penerbit"
    assert has(errors_for(valid), "penerbit berbeda")


def test_final_status_needs_two_reviewers(valid):
    valid["review"]["reviewers"] = ["hanya-satu"]
    assert has(errors_for(valid), "minimal 2 reviewer")


def test_final_status_needs_reviewed_at(valid):
    valid["review"]["reviewed_at"] = None
    assert has(errors_for(valid), "reviewed_at")


def test_final_status_needs_status_note(valid):
    del valid["status_note"]
    assert has(errors_for(valid), "status_note")


def test_final_status_needs_primary_evidence(valid):
    for e in valid["evidence"]:
        e["type"] = "secondary"
    assert has(errors_for(valid), "primary_document atau direct_witness")


def test_final_status_needs_outcome_event(valid):
    valid["timeline"] = [ev for ev in valid["timeline"] if ev["kind"] == "statement"]
    assert has(errors_for(valid), "action/update/setback")


def test_non_final_status_has_lighter_requirements(valid):
    # in_progress boleh dengan satu reviewer & tanpa status_note.
    valid["status"] = "in_progress"
    valid["review"]["reviewers"] = ["satu"]
    del valid["status_note"]
    assert errors_for(valid) == []


# --- Direktori & parsing -----------------------------------------------------

def _write(tmp_path: Path, name: str, data: dict) -> None:
    (tmp_path / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_filename_must_match_id(tmp_path, valid):
    _write(tmp_path, "salah-nama.yaml", valid)
    problems = validate.validate_directory(tmp_path, TODAY)
    assert has(problems["salah-nama.yaml"], "harus sama dengan id")


def test_duplicate_ids_across_files(tmp_path, valid):
    _write(tmp_path, "P-2026-0002.yaml", valid)
    other = copy.deepcopy(valid)
    _write(tmp_path, "P-2026-0003.yaml", other)  # id di dalam masih 0002
    problems = validate.validate_directory(tmp_path, TODAY)
    assert has(problems["P-2026-0003.yaml"], "sudah dipakai")


def test_empty_directory_is_error(tmp_path):
    problems = validate.validate_directory(tmp_path, TODAY)
    assert has(list(problems.values())[0], "tidak ada file")


def test_malformed_yaml_reported(tmp_path):
    (tmp_path / "P-2026-0009.yaml").write_text("id: [belum ditutup", encoding="utf-8")
    problems = validate.validate_directory(tmp_path, TODAY)
    assert has(problems["P-2026-0009.yaml"], "[parse]")


def test_non_mapping_yaml_reported(tmp_path):
    (tmp_path / "P-2026-0010.yaml").write_text("- a\n- b\n", encoding="utf-8")
    problems = validate.validate_directory(tmp_path, TODAY)
    assert has(problems["P-2026-0010.yaml"], "mapping")


def test_unquoted_dates_stay_strings(tmp_path):
    # Kontributor sering lupa tanda kutip; loader harus tetap menghasilkan string.
    f = tmp_path / "x.yaml"
    f.write_text("made_at: 2026-01-15\n", encoding="utf-8")
    assert validate.load_yaml(f)["made_at"] == "2026-01-15"


def test_cli_exit_codes(tmp_path, valid, capsys):
    assert validate.main(["--data", str(DATA_DIR), "--today", "2026-10-08"]) == 0
    assert "OK" in capsys.readouterr().out

    bad = copy.deepcopy(valid)
    bad["status"] = "maybe"
    _write(tmp_path, "P-2026-0002.yaml", bad)
    assert validate.main(["--data", str(tmp_path), "--today", "2026-10-08"]) == 1
    assert "GAGAL" in capsys.readouterr().out
