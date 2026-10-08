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


# =============================================================================
# Skema v2: commitment, program, metrik, hak jawab, koreksi, arsip, relasi, draf
# =============================================================================

PROGRAMS_DIR = Path(__file__).resolve().parent.parent / "data" / "programs"
DRAFTS_DIR = Path(__file__).resolve().parent.parent / "data" / "drafts"


def draft_errors(data: dict) -> list[str]:
    return validate.validate_data(data, TODAY, draft=True)


# --- commitment ---------------------------------------------------------------

@pytest.mark.parametrize("commitment", ["aspiration", "projection"])
def test_broken_not_allowed_for_soft_commitments(valid, commitment):
    valid["commitment"] = commitment
    assert has(errors_for(valid), f"commitment '{commitment}'")
    assert has(draft_errors(valid), f"commitment '{commitment}'")  # juga berlaku di draf


@pytest.mark.parametrize("commitment", ["firm_promise", "target"])
def test_broken_allowed_for_firm_commitments(valid, commitment):
    valid["commitment"] = commitment
    assert not has(errors_for(valid), "commitment")


def test_soft_commitment_can_stay_in_progress(valid):
    valid["commitment"] = "aspiration"
    valid["status"] = "in_progress"
    assert errors_for(valid) == []


def test_commitment_and_program_required(valid):
    del valid["commitment"]
    del valid["program"]
    errs = errors_for(valid)
    assert has(errs, "'commitment' is a required property") and has(errs, "'program' is a required property")


def test_invalid_commitment_value_rejected(valid):
    valid["commitment"] = "janji-manis"
    assert has(errors_for(valid), "commitment")


# --- program ------------------------------------------------------------------

def test_unknown_program_rejected(valid):
    assert has(validate.validate_data(valid, TODAY, programs={}), "tidak ada di data/programs")


def test_known_program_accepted(valid):
    programs = {"puskesmas-24-jam": {"fictional": True}}
    assert validate.validate_data(valid, TODAY, programs=programs) == []


def test_real_promise_cannot_use_fictional_program(valid):
    valid["fictional"] = False
    programs = {"puskesmas-24-jam": {"fictional": True}}
    assert has(validate.validate_data(valid, TODAY, programs=programs), "program fiktif")


def test_load_programs_from_repo():
    programs, problems = validate.load_programs(PROGRAMS_DIR)
    assert problems == {}
    assert {"mbg", "jalan-kabupaten", "puskesmas-24-jam"} <= set(programs)


def test_load_programs_missing_dir_skips_check(tmp_path):
    assert validate.load_programs(tmp_path / "tidak-ada") == (None, {})
    assert validate.load_programs(None) == (None, {})


def test_program_filename_must_match_slug(tmp_path):
    (tmp_path / "salah.yaml").write_text(
        yaml.safe_dump({"slug": "benar", "name": "Nama Program", "description": "Deskripsi program contoh.", "institution": "Instansi"}),
        encoding="utf-8",
    )
    _, problems = validate.load_programs(tmp_path)
    assert has(problems["programs/salah.yaml"], "harus sama dengan slug")


def test_program_schema_violation_reported(tmp_path):
    (tmp_path / "x.yaml").write_text(yaml.safe_dump({"slug": "x", "name": "Nama"}), encoding="utf-8")
    _, problems = validate.load_programs(tmp_path)
    assert has(problems["programs/x.yaml"], "required property")


def test_program_problem_surfaces_in_directory_validation(tmp_path, valid):
    programs_dir = tmp_path / "programs"
    programs_dir.mkdir()
    (programs_dir / "rusak.yaml").write_text("slug: [", encoding="utf-8")
    data_dir = tmp_path / "promises"
    data_dir.mkdir()
    _write(data_dir, "P-2026-0002.yaml", valid)
    problems = validate.validate_directory(data_dir, TODAY, programs_dir=programs_dir)
    assert "programs/rusak.yaml" in problems


# --- metrik -------------------------------------------------------------------

def test_metric_unknown_evidence(valid):
    valid["metrics"][0]["observations"][0]["evidence_id"] = "E99"
    assert has(errors_for(valid), "evidence 'E99'")


def test_metric_target_unknown_evidence(valid):
    valid["metrics"][0]["target"]["evidence_id"] = "E99"
    assert has(errors_for(valid), "evidence 'E99'")


def test_metric_duplicate_ids(valid):
    valid["metrics"].append(copy.deepcopy(valid["metrics"][0]))
    assert has(errors_for(valid), "id metrik 'M1' duplikat")


def test_metric_future_observation(valid):
    valid["metrics"][0]["observations"][0]["date"] = "2026-12-01"
    assert has(errors_for(valid), "observations[0].date ada di masa depan")


def test_metric_observations_must_be_chronological(valid):
    obs = valid["metrics"][0]["observations"]
    obs.append({"date": "2026-06-01", "value": 2, "evidence_id": "E2", "quality": "reported"})
    assert has(errors_for(valid), "observations[1] tidak urut kronologis")


def test_metric_same_date_conflict_requires_disputed(valid):
    obs = valid["metrics"][0]["observations"]
    obs.append({"date": obs[0]["date"], "value": 4, "evidence_id": "E3", "quality": "reported"})
    assert has(errors_for(valid), "harus quality 'disputed'")


def test_metric_same_date_conflict_ok_when_all_disputed(valid):
    obs = valid["metrics"][0]["observations"]
    obs[0]["quality"] = "disputed"
    obs.append({"date": obs[0]["date"], "value": 4, "evidence_id": "E3", "quality": "disputed"})
    assert not has(errors_for(valid), "disputed")


def test_metric_same_date_same_value_is_not_conflict(valid):
    obs = valid["metrics"][0]["observations"]
    obs.append({"date": obs[0]["date"], "value": obs[0]["value"], "evidence_id": "E3", "quality": "reported"})
    assert errors_for(valid) == []


def test_metric_target_revision_before_target_date(valid):
    valid["metrics"][0]["target_revisions"] = [{"date": "2026-01-01", "value": 10, "evidence_id": "E1"}]
    assert has(errors_for(valid), "target_revisions[0] tidak urut kronologis")


def test_metric_target_must_be_positive(valid):
    valid["metrics"][0]["target"]["value"] = 0
    assert has(errors_for(valid), "metrics.0.target.value")


def test_metric_negative_observation_rejected(valid):
    valid["metrics"][0]["observations"][0]["value"] = -1
    assert has(errors_for(valid), "observations.0.value")


def test_metric_invalid_quality_rejected(valid):
    valid["metrics"][0]["observations"][0]["quality"] = "mungkin"
    assert has(errors_for(valid), "quality")


# --- hak jawab ----------------------------------------------------------------

def test_final_status_requires_right_of_reply(valid):
    del valid["response"]
    assert has(errors_for(valid), "hak jawab sudah diupayakan")


@pytest.mark.parametrize("status", ["not_yet_sought"])
def test_final_status_rejects_unsought_response(valid, status):
    valid["response"] = {"status": status}
    assert has(errors_for(valid), "hak jawab sudah diupayakan")


def test_final_status_rejects_pending_response(valid):
    valid["response"] = {"status": "requested", "requested_at": "2026-07-05"}
    assert has(errors_for(valid), "hak jawab sudah diupayakan")


def test_no_reply_needs_waiting_period(valid):
    valid["response"] = {"status": "no_reply", "requested_at": "2026-07-12"}  # reviewed_at 2026-07-15
    assert has(errors_for(valid), "jeda minimal 7 hari")


def test_no_reply_with_enough_waiting_is_ok(valid):
    valid["response"] = {"status": "no_reply", "requested_at": "2026-07-08"}  # tepat 7 hari
    assert not has(errors_for(valid), "jeda minimal")


def test_received_response_needs_details(valid):
    valid["response"] = {"status": "received"}
    errs = errors_for(valid)
    assert has(errs, "response") and has(errs, "received_at")


def test_received_response_must_cite_evidence(valid):
    valid["response"] = {"status": "received", "received_at": "2026-07-10", "summary": "Tanggapan pihak terkait.", "evidence_id": "E99"}
    assert has(errors_for(valid), "response.evidence_id 'E99'")


def test_received_response_valid(valid):
    valid["response"] = {"status": "received", "received_at": "2026-07-10", "summary": "Tanggapan pihak terkait.", "evidence_id": "E2"}
    assert errors_for(valid) == []


def test_declined_response_needs_request_date(valid):
    valid["response"] = {"status": "declined"}
    assert has(errors_for(valid), "requested_at")


def test_response_reply_before_request_rejected(valid):
    valid["response"] = {
        "status": "received", "requested_at": "2026-07-10", "received_at": "2026-07-05",
        "summary": "Tanggapan pihak terkait.", "evidence_id": "E2",
    }
    assert has(errors_for(valid), "received_at lebih awal dari requested_at")


def test_non_final_status_does_not_require_response(valid):
    valid["status"] = "in_progress"
    del valid["response"]
    assert errors_for(valid) == []


# --- koreksi ------------------------------------------------------------------

def test_correction_in_future_rejected(valid):
    valid["corrections"][0]["date"] = "2026-12-01"
    assert has(errors_for(valid), "corrections[0].date ada di masa depan")


def test_correction_before_promise_rejected(valid):
    valid["corrections"][0]["date"] = "2026-01-01"
    assert has(errors_for(valid), "lebih awal dari tanggal janji")


def test_corrections_must_be_chronological(valid):
    valid["corrections"].append({"date": "2026-07-10", "summary": "Koreksi yang lebih awal."})
    assert has(errors_for(valid), "corrections[1] tidak urut kronologis")


# --- arsip --------------------------------------------------------------------

def test_wayback_latest_form_rejected(valid):
    valid["evidence"][0]["archive_url"] = "https://web.archive.org/web/https://example.org/a"
    assert has(errors_for(valid), "snapshot bertimestamp")


def test_wayback_timestamp_must_match_archived_at(valid):
    valid["evidence"][0]["archived_at"] = "2026-02-12"  # snapshot bertanggal 2026-02-11
    assert has(errors_for(valid), "tidak sama dengan tanggal snapshot")


def test_wayback_raw_form_accepted(valid):
    url = valid["evidence"][0]["archive_url"]
    valid["evidence"][0]["archive_url"] = url.replace("/20260211000000/", "/20260211000000id_/")
    assert errors_for(valid) == []


def test_non_wayback_archive_has_no_timestamp_rule(valid):
    valid["evidence"][0]["archive_url"] = "https://archive.ph/AbCdE"
    assert errors_for(valid) == []


# --- mode draf ----------------------------------------------------------------

def test_draft_mode_relaxes_readiness_requirements(valid):
    valid["fictional"] = False
    valid["review"] = {"reviewers": [], "reviewed_at": None}
    valid["response"] = {"status": "not_yet_sought"}
    valid["evidence"][0]["sha256"] = "0" * 64
    valid["evidence"][0]["archive_url"] = "https://web.archive.org/web/https://example.org/a"
    assert draft_errors(valid) == []
    full = errors_for(valid)
    assert has(full, "placeholder") and has(full, "minimal 2 reviewer") and has(full, "hak jawab")


def test_draft_mode_still_checks_references_and_dates(valid):
    valid["timeline"][0]["evidence_ids"] = ["E99"]
    valid["promise"]["deadline"] = "2026-01-01"
    errs = draft_errors(valid)
    assert has(errs, "evidence 'E99'") and has(errs, "deadline lebih awal")


def test_draft_mode_still_requires_archive_host(valid):
    valid["evidence"][0]["archive_url"] = "https://example.org/salinan"
    assert has(draft_errors(valid), "layanan arsip")


def test_repo_drafts_valid_in_draft_mode():
    problems = validate.validate_directory(DRAFTS_DIR, TODAY, draft=True, extra_dirs=(DATA_DIR,))
    assert problems == {}


def test_repo_drafts_are_not_publishable_yet():
    # Draf MBG belum punya arsip bertimestamp, hash asli, reviewer, dan hak jawab.
    for path in sorted(DRAFTS_DIR.glob("*.yaml")):
        errs = validate.validate_data(validate.load_yaml(path), TODAY)
        assert errs, f"{path.name} lolos standar penuh padahal belum direview"


def test_empty_drafts_dir_is_ok_in_draft_mode(tmp_path):
    assert validate.validate_directory(tmp_path, TODAY, draft=True) == {}
    assert validate.validate_directory(tmp_path / "tidak-ada", TODAY, draft=True) == {}


def test_cli_drafts_flag(capsys):
    assert validate.main(["--drafts", "--today", "2026-10-08"]) == 0
    assert "(draf)" in capsys.readouterr().out


# --- relasi antar janji -------------------------------------------------------

def _pair(tmp_path, a_related=None, b_related=None):
    a = validate.load_yaml(DATA_DIR / "P-2026-0001.yaml")
    b = validate.load_yaml(DATA_DIR / "P-2026-0002.yaml")
    if a_related is not None:
        a["related"] = a_related
    if b_related is not None:
        b["related"] = b_related
    _write(tmp_path, "P-2026-0001.yaml", a)
    _write(tmp_path, "P-2026-0002.yaml", b)
    return validate.validate_directory(tmp_path, TODAY, programs_dir=PROGRAMS_DIR)


def test_supersedes_pair_is_valid(tmp_path):
    problems = _pair(
        tmp_path,
        [{"id": "P-2026-0002", "relation": "supersedes"}],
        [{"id": "P-2026-0001", "relation": "superseded_by"}],
    )
    assert problems == {}


def test_supersedes_without_inverse_flagged(tmp_path):
    problems = _pair(tmp_path, [{"id": "P-2026-0002", "relation": "supersedes"}])
    assert has(problems["P-2026-0001.yaml"], "butuh pasangan 'superseded_by'")


def test_follows_needs_no_inverse(tmp_path):
    assert _pair(tmp_path, [{"id": "P-2026-0002", "relation": "follows"}]) == {}


def test_related_unknown_id_flagged(tmp_path):
    problems = _pair(tmp_path, [{"id": "P-2026-0099", "relation": "follows"}])
    assert has(problems["P-2026-0001.yaml"], "yang tidak ada")


def test_related_self_reference_flagged(tmp_path):
    problems = _pair(tmp_path, [{"id": "P-2026-0001", "relation": "part_of"}])
    assert has(problems["P-2026-0001.yaml"], "diri sendiri")


def test_draft_can_reference_published_promise(tmp_path):
    draft = validate.load_yaml(DATA_DIR / "P-2026-0001.yaml")
    draft["id"] = "P-2026-0010"
    draft["related"] = [{"id": "P-2026-0002", "relation": "follows"}]
    _write(tmp_path, "P-2026-0010.yaml", draft)
    ok = validate.validate_directory(tmp_path, TODAY, programs_dir=PROGRAMS_DIR, draft=True, extra_dirs=(DATA_DIR,))
    assert ok == {}
    missing = validate.validate_directory(tmp_path, TODAY, programs_dir=PROGRAMS_DIR, draft=True)
    assert has(missing["P-2026-0010.yaml"], "yang tidak ada")


def test_metadata_fields_validated(valid):
    valid["official"]["wikidata_id"] = "Q12345"
    valid["evidence"][0]["language"] = "id"
    valid["evidence"][0]["quote"] = "Kutipan pendek."
    valid["evidence"][0]["locator"] = "halaman 3"
    valid["tags"] = ["kesehatan", "layanan-publik"]
    assert errors_for(valid) == []
    valid["official"]["wikidata_id"] = "12345"
    valid["evidence"][0]["language"] = "indonesia"
    valid["tags"] = ["Kesehatan", "kesehatan"]
    errs = errors_for(valid)
    assert has(errs, "wikidata_id") and has(errs, "language") and has(errs, "tags")
