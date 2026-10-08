"""Validator untuk data janji (promise tracker).

Dua lapis pengecekan:
1. Struktur  -> JSON Schema (schema/promise.schema.json, schema/program.schema.json)
2. Editorial -> aturan yang tidak bisa diekspresikan schema (independensi bukti,
   hak jawab, konsistensi tanggal & metrik, relasi antar janji, dll)

Pemakaian:
    python tools/validate.py                 # data/promises (standar penuh, gerbang CI)
    python tools/validate.py --drafts        # data/drafts (struktur & konsistensi saja)

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
PROGRAM_SCHEMA_PATH = ROOT / "schema" / "program.schema.json"
DEFAULT_DATA_DIR = ROOT / "data" / "promises"
DEFAULT_DRAFTS_DIR = ROOT / "data" / "drafts"
DEFAULT_PROGRAMS_DIR = ROOT / "data" / "programs"

# Status yang menyatakan hasil akhir; butuh standar bukti lebih tinggi.
FINAL_STATUSES = {"fulfilled", "partially_fulfilled", "broken"}
MIN_REVIEWERS_FINAL = 2
MIN_PUBLISHERS_FINAL = 2
# 'broken' hanya adil untuk komitmen yang tegas; harapan/proyeksi tidak bisa "diingkari".
BROKEN_ALLOWED_COMMITMENTS = {"firm_promise", "target"}
# Hak jawab: untuk status akhir, pihak yang dinilai harus sudah dimintai tanggapan.
RESPONSE_OK_FOR_FINAL = {"received", "declined", "no_reply"}
MIN_REPLY_DAYS = 7

# Hanya layanan arsip publik yang diterima, supaya bukti tetap bisa diperiksa
# saat tautan asli mati.
ARCHIVE_HOSTS = {"web.archive.org", "archive.org", "archive.ph", "archive.today", "perma.cc"}
# Wayback: harus snapshot bertimestamp tetap, bukan bentuk "terbaru" (/web/https://...).
WAYBACK_PATH = re.compile(r"^/web/(\d{14})(?:id_|if_|im_|js_|cs_)?/https?://")

_PLACEHOLDER_HASH = re.compile(r"^0{50,}")
_INVERSE_RELATION = {"supersedes": "superseded_by", "superseded_by": "supersedes"}


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


def load_program_schema() -> dict:
    with PROGRAM_SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD; None kalau kosong atau bukan tanggal kalender yang valid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _check_date(errors: list[str], label: str, value: str | None, today: date) -> date | None:
    """Parse tanggal; catat error kalau tidak valid atau ada di masa depan."""
    parsed = _parse_date(value)
    if parsed is None:
        errors.append(f"[editorial] {label} bukan tanggal valid: {value}")
        return None
    if parsed > today:
        errors.append(f"[editorial] {label} ada di masa depan")
    return parsed


def validate_structure(data: dict, schema: dict | None = None) -> list[str]:
    """Lapis 1: validasi JSON Schema. Mengembalikan daftar pesan error."""
    validator = Draft202012Validator(schema or load_schema())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path]):
        location = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"[schema] {location}: {err.message}")
    return errors


def _validate_metrics(data: dict, by_id: dict, today: date) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for mi, metric in enumerate(data.get("metrics", [])):
        label = f"metrics[{mi}]"
        if metric["id"] in seen:
            errors.append(f"[editorial] {label}: id metrik '{metric['id']}' duplikat")
        seen.add(metric["id"])

        target = metric["target"]
        refs = [target["evidence_id"]]
        refs += [r["evidence_id"] for r in metric.get("target_revisions", [])]
        refs += [o["evidence_id"] for o in metric["observations"]]
        for ev_id in sorted(set(refs)):
            if ev_id not in by_id:
                errors.append(f"[editorial] {label} merujuk evidence '{ev_id}' yang tidak ada")

        set_on = _check_date(errors, f"{label}.target.set_on", target["set_on"], today)

        previous = set_on
        for ri, rev in enumerate(metric.get("target_revisions", [])):
            d = _check_date(errors, f"{label}.target_revisions[{ri}].date", rev["date"], today)
            if d and previous and d < previous:
                errors.append(f"[editorial] {label}.target_revisions[{ri}] tidak urut kronologis")
            previous = d or previous

        previous = None
        by_date: dict[date, list[dict]] = {}
        for oi, obs in enumerate(metric["observations"]):
            d = _check_date(errors, f"{label}.observations[{oi}].date", obs["date"], today)
            if d is None:
                continue
            if previous and d < previous:
                errors.append(f"[editorial] {label}.observations[{oi}] tidak urut kronologis")
            previous = d
            by_date.setdefault(d, []).append(obs)

        # Dua angka berbeda untuk tanggal yang sama harus ditandai terbuka sebagai disputed.
        for d, group in by_date.items():
            if len({o["value"] for o in group}) > 1 and any(o["quality"] != "disputed" for o in group):
                errors.append(
                    f"[editorial] {label}: tanggal {d.isoformat()} punya nilai berbeda; "
                    "semua observasi pada tanggal itu harus quality 'disputed'"
                )
    return errors


def _validate_response(data: dict, by_id: dict, today: date, reviewed_at: date | None, draft: bool) -> list[str]:
    errors: list[str] = []
    resp = data.get("response")
    if resp:
        requested = received = None
        if resp.get("requested_at"):
            requested = _check_date(errors, "response.requested_at", resp["requested_at"], today)
        if resp.get("received_at"):
            received = _check_date(errors, "response.received_at", resp["received_at"], today)
        if requested and received and received < requested:
            errors.append("[editorial] response.received_at lebih awal dari requested_at")
        if resp.get("evidence_id") and resp["evidence_id"] not in by_id:
            errors.append(f"[editorial] response.evidence_id '{resp['evidence_id']}' tidak ada di evidence")
        if (
            not draft
            and resp["status"] == "no_reply"
            and requested
            and reviewed_at
            and (reviewed_at - requested).days < MIN_REPLY_DAYS
        ):
            errors.append(
                f"[editorial] response 'no_reply' butuh jeda minimal {MIN_REPLY_DAYS} hari "
                "antara requested_at dan reviewed_at"
            )

    if not draft and data["status"] in FINAL_STATUSES:
        if not resp or resp["status"] not in RESPONSE_OK_FOR_FINAL:
            current = resp["status"] if resp else "(kosong)"
            errors.append(
                f"[editorial] status '{data['status']}' butuh response.status salah satu "
                f"{'/'.join(sorted(RESPONSE_OK_FOR_FINAL))} (hak jawab sudah diupayakan); sekarang {current}"
            )
    return errors


def validate_editorial(
    data: dict,
    today: date,
    *,
    draft: bool = False,
    programs: dict[str, dict] | None = None,
) -> list[str]:
    """Lapis 2: aturan editorial. Mengasumsikan struktur sudah lolos schema.

    draft=True melonggarkan syarat kesiapan terbit (arsip bertimestamp, hash asli,
    reviewer, hak jawab, standar status akhir), tapi tetap memeriksa konsistensi
    referensi dan tanggal.
    """
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

    if programs is not None:
        program = programs.get(data["program"])
        if program is None:
            errors.append(f"[editorial] program '{data['program']}' tidak ada di data/programs/")
        elif program.get("fictional") and not data.get("fictional"):
            errors.append("[editorial] janji nyata tidak boleh memakai program fiktif")

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

    reviewed_at_raw = data["review"].get("reviewed_at")
    reviewed_at = None
    if reviewed_at_raw:
        reviewed_at = _parse_date(reviewed_at_raw)
        if reviewed_at is None:
            errors.append("[editorial] review.reviewed_at bukan tanggal valid")
        elif reviewed_at > today:
            errors.append("[editorial] review.reviewed_at ada di masa depan")

    previous = None
    for i, corr in enumerate(data.get("corrections", [])):
        d = _check_date(errors, f"corrections[{i}].date", corr["date"], today)
        if d and made_at and d < made_at:
            errors.append(f"[editorial] corrections[{i}].date lebih awal dari tanggal janji")
        if d and previous and d < previous:
            errors.append(f"[editorial] corrections[{i}] tidak urut kronologis")
        previous = d or previous

    # --- Metrik & hak jawab -------------------------------------------------
    errors += _validate_metrics(data, by_id, today)
    errors += _validate_response(data, by_id, today, reviewed_at, draft)

    # --- Komitmen -----------------------------------------------------------
    if data["status"] == "broken" and data["commitment"] not in BROKEN_ALLOWED_COMMITMENTS:
        errors.append(
            f"[editorial] status 'broken' tidak boleh untuk commitment '{data['commitment']}' "
            f"(hanya {', '.join(sorted(BROKEN_ALLOWED_COMMITMENTS))}); pakai 'unverifiable' atau status lain"
        )

    # --- Kualitas bukti -----------------------------------------------------
    for e in evidence:
        parsed = urlparse(e["archive_url"])
        host = (parsed.hostname or "").lower()
        if host not in ARCHIVE_HOSTS:
            errors.append(
                f"[editorial] evidence {e['id']}: archive_url harus dari layanan arsip "
                f"({', '.join(sorted(ARCHIVE_HOSTS))}), bukan '{host}'"
            )
            continue
        if draft:
            continue
        # Hash placeholder hanya boleh di data contoh.
        if not data.get("fictional") and _PLACEHOLDER_HASH.match(e["sha256"]):
            errors.append(f"[editorial] evidence {e['id']}: sha256 tampak seperti placeholder")
        if host == "web.archive.org":
            match = WAYBACK_PATH.match(parsed.path)
            arc = _parse_date(e["archived_at"])
            if not match:
                errors.append(
                    f"[editorial] evidence {e['id']}: archive_url Wayback harus snapshot bertimestamp "
                    "14 digit (/web/YYYYMMDDhhmmss/https://...), bukan bentuk 'terbaru'"
                )
            elif arc and match.group(1)[:8] != arc.strftime("%Y%m%d"):
                errors.append(
                    f"[editorial] evidence {e['id']}: archived_at tidak sama dengan tanggal snapshot di archive_url"
                )

    # --- Standar bukti untuk status akhir ----------------------------------
    if not draft and data["status"] in FINAL_STATUSES:
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
        if not reviewed_at_raw:
            errors.append(f"[editorial] status '{data['status']}' butuh review.reviewed_at")
        if not data.get("status_note"):
            errors.append(f"[editorial] status '{data['status']}' butuh status_note (alasan penilaian)")
        if not any(ev["kind"] in {"action", "update", "setback"} for ev in data["timeline"]):
            errors.append(
                f"[editorial] status '{data['status']}' butuh minimal satu event "
                "action/update/setback di timeline"
            )

    return errors


def validate_data(
    data: dict,
    today: date,
    schema: dict | None = None,
    *,
    draft: bool = False,
    programs: dict[str, dict] | None = None,
) -> list[str]:
    """Validasi lengkap satu janji. Lapis editorial hanya jalan kalau struktur valid."""
    errors = validate_structure(data, schema)
    if errors:
        return errors
    return validate_editorial(data, today, draft=draft, programs=programs)


def load_programs(programs_dir: Path | None) -> tuple[dict[str, dict] | None, dict[str, list[str]]]:
    """Muat & validasi data/programs/*.yaml. Mengembalikan ({slug: data}, {file: [error]}).

    Mengembalikan (None, {}) kalau folder tidak ada, sehingga pengecekan program dilewati.
    """
    if programs_dir is None or not programs_dir.is_dir():
        return None, {}
    schema = load_program_schema()
    programs: dict[str, dict] = {}
    problems: dict[str, list[str]] = {}
    for path in sorted(programs_dir.glob("*.yaml")):
        name = f"programs/{path.name}"
        try:
            data = load_yaml(path)
        except (yaml.YAMLError, ValueError, OSError) as exc:
            problems[name] = [f"[parse] {exc}"]
            continue
        errors = validate_structure(data, schema)
        if not errors and path.stem != data["slug"]:
            errors.append(f"[editorial] nama file '{path.name}' harus sama dengan slug '{data['slug']}.yaml'")
        if errors:
            problems[name] = errors
        else:
            programs[data["slug"]] = data
    return programs, problems


def _validate_related(data: dict, docs: dict[str, dict]) -> list[str]:
    """Relasi antar janji: id harus ada, bukan diri sendiri, dan supersedes/superseded_by berpasangan."""
    errors: list[str] = []
    own_id = data["id"]
    for rel in data.get("related", []):
        target_id, relation = rel["id"], rel["relation"]
        if target_id == own_id:
            errors.append("[editorial] related tidak boleh merujuk diri sendiri")
            continue
        target = docs.get(target_id)
        if target is None:
            errors.append(f"[editorial] related merujuk id '{target_id}' yang tidak ada")
            continue
        inverse = _INVERSE_RELATION.get(relation)
        if inverse:
            back = target.get("related") or []
            if not any(isinstance(r, dict) and r.get("id") == own_id and r.get("relation") == inverse for r in back):
                errors.append(
                    f"[editorial] related '{relation}' ke {target_id} butuh pasangan "
                    f"'{inverse}' ke {own_id} di file {target_id}"
                )
    return errors


def validate_directory(
    data_dir: Path,
    today: date,
    *,
    programs_dir: Path | None = DEFAULT_PROGRAMS_DIR,
    draft: bool = False,
    extra_dirs: tuple[Path, ...] = (),
) -> dict[str, list[str]]:
    """Validasi semua *.yaml di folder. Mengembalikan {nama_file: [error]} (hanya yang bermasalah).

    extra_dirs: folder lain yang dipakai hanya untuk menyelesaikan referensi `related`
    (mis. draf boleh merujuk janji yang sudah terbit).
    """
    schema = load_schema()
    programs, problems = load_programs(programs_dir)
    problems = dict(problems)
    seen_ids: dict[str, str] = {}

    files = sorted(data_dir.glob("*.yaml")) if data_dir.is_dir() else []
    if not files:
        return {} if draft else {str(data_dir): ["tidak ada file *.yaml ditemukan"]}

    parsed: dict[str, dict] = {}
    for path in files:
        try:
            parsed[path.name] = load_yaml(path)
        except (yaml.YAMLError, ValueError, OSError) as exc:
            problems[path.name] = [f"[parse] {exc}"]

    # Kumpulan dokumen mentah untuk resolusi `related` (folder ini + extra_dirs).
    docs: dict[str, dict] = {}
    for extra in extra_dirs:
        if extra.is_dir():
            for path in sorted(extra.glob("*.yaml")):
                try:
                    item = load_yaml(path)
                except (yaml.YAMLError, ValueError, OSError):
                    continue
                if isinstance(item.get("id"), str):
                    docs.setdefault(item["id"], item)
    for item in parsed.values():
        if isinstance(item.get("id"), str):
            docs[item["id"]] = item

    for name, data in parsed.items():
        errors = validate_structure(data, schema)
        if not errors:
            errors = validate_editorial(data, today, draft=draft, programs=programs)
            errors += _validate_related(data, docs)

        # Aturan antar-file: nama file = id, dan id unik.
        promise_id = data.get("id")
        if isinstance(promise_id, str):
            if Path(name).stem != promise_id:
                errors.append(f"[editorial] nama file '{name}' harus sama dengan id '{promise_id}.yaml'")
            if promise_id in seen_ids:
                errors.append(f"[editorial] id '{promise_id}' sudah dipakai di {seen_ids[promise_id]}")
            else:
                seen_ids[promise_id] = name

        if errors:
            problems[name] = errors
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validasi data promise tracker")
    parser.add_argument("--data", type=Path, default=None, help="folder berisi *.yaml (default data/promises, atau data/drafts dengan --drafts)")
    parser.add_argument("--drafts", action="store_true", help="validasi draf: struktur & konsistensi saja")
    parser.add_argument("--programs", type=Path, default=DEFAULT_PROGRAMS_DIR, help="folder program")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="override tanggal hari ini (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    data_dir = args.data or (DEFAULT_DRAFTS_DIR if args.drafts else DEFAULT_DATA_DIR)
    extra = (DEFAULT_DATA_DIR,) if args.drafts else ()
    problems = validate_directory(
        data_dir, args.today, programs_dir=args.programs, draft=args.drafts, extra_dirs=extra
    )
    if not problems:
        count = len(list(data_dir.glob("*.yaml"))) if data_dir.is_dir() else 0
        mode = " (draf)" if args.drafts else ""
        print(f"OK: {count} file valid{mode}")
        return 0

    for name, errors in problems.items():
        print(f"\n{name}")
        for msg in errors:
            print(f"  - {msg}")
    print(f"\nGAGAL: {len(problems)} file bermasalah")
    return 1


if __name__ == "__main__":
    sys.exit(main())
