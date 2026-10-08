"""Validator untuk data janji (promise tracker).

Dua lapis pengecekan:
1. Struktur  -> JSON Schema (schema/promise.schema.json)
2. Editorial -> aturan yang tidak bisa diekspresikan schema (independensi bukti,
   jumlah reviewer, konsistensi tanggal, referensi silang, dll)

Pemakaian:
    python tools/validate.py [--data data/promises] [--today 2026-10-08]

Exit code 0 = semua valid, 1 = ada error (dipakai CI untuk menolak PR).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "promise.schema.json"
DEFAULT_DATA_DIR = ROOT / "data" / "promises"

# Status yang menyatakan hasil akhir; butuh standar bukti lebih tinggi.
FINAL_STATUSES = {"fulfilled", "partially_fulfilled", "broken"}
MIN_REVIEWERS_FINAL = 2
MIN_PUBLISHERS_FINAL = 2

# Hanya layanan arsip publik yang diterima, supaya bukti tetap bisa diperiksa
# saat tautan asli mati.
ARCHIVE_HOSTS = {"web.archive.org", "archive.org", "archive.ph", "archive.today", "perma.cc"}

_PLACEHOLDER_HASH = re.compile(r"^0{50,}")


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader yang TIDAK mengubah 2026-01-15 menjadi objek date.

    Semua tanggal tetap string, sehingga schema berlaku seragam dan kontributor
    tidak kena error aneh kalau lupa memberi tanda kutip.
    """


_StringDateLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path) -> dict:
    """Baca satu file YAML. Melempar ValueError kalau isinya bukan mapping."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_StringDateLoader)  # noqa: S506 (loader aman, turunan SafeLoader)
    if not isinstance(data, dict):
        raise ValueError("isi file harus berupa mapping YAML")
    return data


def load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD; None kalau kosong atau bukan tanggal kalender yang valid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_structure(data: dict, schema: dict | None = None) -> list[str]:
    """Lapis 1: validasi JSON Schema. Mengembalikan daftar pesan error."""
    validator = Draft202012Validator(schema or load_schema())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        location = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"[schema] {location}: {err.message}")
    return errors


def validate_editorial(data: dict, today: date) -> list[str]:
    """Lapis 2: aturan editorial. Mengasumsikan struktur sudah lolos schema."""
    errors: list[str] = []
    evidence = data["evidence"]
    ids = [e["id"] for e in evidence]
    by_id = {e["id"]: e for e in evidence}

    # --- Referensi silang ---------------------------------------------------
    if len(ids) != len(set(ids)):
        errors.append("[editorial] id evidence duplikat")

    source_id = data["promise"]["source_evidence_id"]
    if source_id not in by_id:
        errors.append(f"[editorial] promise.source_evidence_id '{source_id}' tidak ada di evidence")

    for i, event in enumerate(data["timeline"]):
        for ev_id in event["evidence_ids"]:
            if ev_id not in by_id:
                errors.append(f"[editorial] timeline[{i}] merujuk evidence '{ev_id}' yang tidak ada")

    # --- Tanggal ------------------------------------------------------------
    made_at = _parse_date(data["promise"]["made_at"])
    deadline_raw = data["promise"].get("deadline")
    deadline = _parse_date(deadline_raw)

    if made_at is None:
        errors.append(f"[editorial] promise.made_at bukan tanggal valid: {data['promise']['made_at']}")
    elif made_at > today:
        errors.append("[editorial] promise.made_at ada di masa depan")

    if deadline_raw and deadline is None:
        errors.append(f"[editorial] promise.deadline bukan tanggal valid: {deadline_raw}")
    if made_at and deadline and deadline < made_at:
        errors.append("[editorial] promise.deadline lebih awal dari made_at")

    for e in evidence:
        pub = _parse_date(e.get("published_at"))
        arc = _parse_date(e["archived_at"])
        if e.get("published_at") and pub is None:
            errors.append(f"[editorial] evidence {e['id']}: published_at bukan tanggal valid")
        if arc is None:
            errors.append(f"[editorial] evidence {e['id']}: archived_at bukan tanggal valid")
            continue
        if arc > today:
            errors.append(f"[editorial] evidence {e['id']}: archived_at ada di masa depan")
        if pub and pub > today:
            errors.append(f"[editorial] evidence {e['id']}: published_at ada di masa depan")
        if pub and arc < pub:
            errors.append(f"[editorial] evidence {e['id']}: archived_at lebih awal dari published_at")

    previous: date | None = None
    for i, event in enumerate(data["timeline"]):
        d = _parse_date(event["date"])
        if d is None:
            errors.append(f"[editorial] timeline[{i}].date bukan tanggal valid: {event['date']}")
            continue
        if d > today:
            errors.append(f"[editorial] timeline[{i}].date ada di masa depan")
        if made_at and d < made_at:
            errors.append(f"[editorial] timeline[{i}].date lebih awal dari tanggal janji")
        if previous and d < previous:
            errors.append(f"[editorial] timeline[{i}] tidak urut kronologis")
        previous = d

    reviewed_at = data["review"].get("reviewed_at")
    if reviewed_at:
        r = _parse_date(reviewed_at)
        if r is None:
            errors.append("[editorial] review.reviewed_at bukan tanggal valid")
        elif r > today:
            errors.append("[editorial] review.reviewed_at ada di masa depan")

    # --- Kualitas bukti -----------------------------------------------------
    for e in evidence:
        host = (urlparse(e["archive_url"]).hostname or "").lower()
        if host not in ARCHIVE_HOSTS:
            errors.append(
                f"[editorial] evidence {e['id']}: archive_url harus dari layanan arsip "
                f"({', '.join(sorted(ARCHIVE_HOSTS))}), bukan '{host}'"
            )
        # Hash placeholder hanya boleh di data contoh.
        if not data.get("fictional") and _PLACEHOLDER_HASH.match(e["sha256"]):
            errors.append(f"[editorial] evidence {e['id']}: sha256 tampak seperti placeholder")

    # --- Standar bukti untuk status akhir ----------------------------------
    if data["status"] in FINAL_STATUSES:
        publishers = {e["publisher"].strip().lower() for e in evidence}
        if len(publishers) < MIN_PUBLISHERS_FINAL:
            errors.append(
                f"[editorial] status '{data['status']}' butuh bukti dari minimal "
                f"{MIN_PUBLISHERS_FINAL} penerbit berbeda (ada {len(publishers)})"
            )
        if not any(e["type"] in {"primary_document", "direct_witness"} for e in evidence):
            errors.append(
                f"[editorial] status '{data['status']}' butuh minimal satu bukti "
                "primary_document atau direct_witness"
            )
        if len(data["review"]["reviewers"]) < MIN_REVIEWERS_FINAL:
            errors.append(
                f"[editorial] status '{data['status']}' butuh minimal {MIN_REVIEWERS_FINAL} reviewer"
            )
        if not reviewed_at:
            errors.append(f"[editorial] status '{data['status']}' butuh review.reviewed_at")
        if not data.get("status_note"):
            errors.append(f"[editorial] status '{data['status']}' butuh status_note (alasan penilaian)")
        if not any(ev["kind"] in {"action", "update", "setback"} for ev in data["timeline"]):
            errors.append(
                f"[editorial] status '{data['status']}' butuh minimal satu event "
                "action/update/setback di timeline"
            )

    return errors


def validate_data(data: dict, today: date, schema: dict | None = None) -> list[str]:
    """Validasi lengkap satu janji. Lapis editorial hanya jalan kalau struktur valid."""
    errors = validate_structure(data, schema)
    if errors:
        return errors
    return validate_editorial(data, today)


def validate_directory(data_dir: Path, today: date) -> dict[str, list[str]]:
    """Validasi semua *.yaml di folder. Mengembalikan {nama_file: [error]} (hanya yang bermasalah)."""
    schema = load_schema()
    problems: dict[str, list[str]] = {}
    seen_ids: dict[str, str] = {}

    files = sorted(data_dir.glob("*.yaml"))
    if not files:
        return {str(data_dir): ["tidak ada file *.yaml ditemukan"]}

    for path in files:
        try:
            data = load_yaml(path)
        except (yaml.YAMLError, ValueError, OSError) as exc:
            problems[path.name] = [f"[parse] {exc}"]
            continue

        errors = validate_data(data, today, schema)

        # Aturan antar-file: nama file = id, dan id unik.
        promise_id = data.get("id")
        if isinstance(promise_id, str):
            if path.stem != promise_id:
                errors.append(f"[editorial] nama file '{path.name}' harus sama dengan id '{promise_id}.yaml'")
            if promise_id in seen_ids:
                errors.append(f"[editorial] id '{promise_id}' sudah dipakai di {seen_ids[promise_id]}")
            else:
                seen_ids[promise_id] = path.name

        if errors:
            problems[path.name] = errors
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validasi data promise tracker")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder berisi *.yaml")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="override tanggal hari ini (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    problems = validate_directory(args.data, args.today)
    if not problems:
        count = len(list(args.data.glob("*.yaml")))
        print(f"OK: {count} file valid")
        return 0

    for name, errors in problems.items():
        print(f"\n{name}")
        for msg in errors:
            print(f"  - {msg}")
    print(f"\nGAGAL: {len(problems)} file bermasalah")
    return 1


if __name__ == "__main__":
    sys.exit(main())
