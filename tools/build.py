"""Generator situs statis untuk promise tracker.

Membaca data/promises/*.yaml dan data/programs/*.yaml -> menulis dist/:
index.html, halaman per janji, halaman per program, dan data.json (open data).
Build SELALU memvalidasi dulu; data yang tidak lolos tidak akan pernah dipublikasikan.

Pemakaian:
    python -m tools.build [--data data/promises] [--out dist] [--today 2026-10-08]
                          [--base-url https://contoh.github.io/news-as-code] [--site-name "Promise Tracker"]

--base-url mengaktifkan JSON-LD schema.org/ClaimReview untuk janji NYATA berstatus akhir.
Data fiktif tidak pernah diberi ClaimReview dan ditandai noindex.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from tools import validate

ROOT = Path(__file__).resolve().parent.parent

STATUS_LABELS = {
    "not_started": ("Belum dimulai", "⏳"),
    "in_progress": ("Sedang berjalan", "🔧"),
    "fulfilled": ("Terpenuhi", "✅"),
    "partially_fulfilled": ("Terpenuhi sebagian", "🟡"),
    "broken": ("Tidak ditepati", "❌"),
    "unverifiable": ("Tidak dapat diverifikasi", "❔"),
}
COMMITMENT_LABELS = {
    "firm_promise": ("Janji tegas", "Pernyataan komitmen yang jelas dan bisa diuji."),
    "target": ("Target", "Angka/tenggat yang ditetapkan sebagai sasaran."),
    "aspiration": ("Harapan", "Dinyatakan sebagai harapan; tidak dinilai sebagai ingkar janji."),
    "projection": ("Proyeksi", "Perkiraan; tidak dinilai sebagai ingkar janji."),
}
EVIDENCE_LABELS = {
    "primary_document": "Dokumen primer",
    "direct_witness": "Saksi langsung",
    "media": "Media",
    "secondary": "Sumber sekunder",
}
KIND_LABELS = {
    "statement": "Pernyataan",
    "action": "Tindakan",
    "update": "Pembaruan",
    "setback": "Hambatan",
}
QUALITY_LABELS = {
    "reported": "Dilaporkan",
    "provisional": "Sementara",
    "disputed": "Dipersoalkan",
}
RELATION_LABELS = {
    "supersedes": "Menggantikan",
    "superseded_by": "Digantikan oleh",
    "follows": "Lanjutan dari",
    "part_of": "Bagian dari",
}
RESPONSE_LABELS = {
    "not_yet_sought": "Belum dimintai tanggapan",
    "requested": "Tanggapan diminta, menunggu",
    "received": "Tanggapan diterima",
    "declined": "Menolak memberi tanggapan",
    "no_reply": "Tidak ada tanggapan",
}
# Peringkat schema.org/ClaimReview (1-5). Hanya status akhir yang diberi peringkat.
CLAIM_RATING = {"broken": (1, "Tidak ditepati"), "partially_fulfilled": (3, "Terpenuhi sebagian"), "fulfilled": (5, "Terpenuhi")}
OPEN_STATUSES = {"not_started", "in_progress"}

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#5c5c5c;--line:#d9d9d9;--card:#f7f7f7;--accent:#0b5cad;--warn:#8a4b00}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#a8a8a8;--line:#333;--card:#1c1c1c;--accent:#6db3ff;--warn:#ffb866}}
*{box-sizing:border-box}
body{margin:0 auto;max-width:860px;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
a{color:var(--accent)}
h1{font-size:1.5rem;margin:.2em 0}h2{font-size:1.2rem;margin-top:1.8em}h3{font-size:1.05rem;margin:1.2em 0 .3em}
.muted{color:var(--muted);font-size:.9rem}
.banner{background:var(--card);border:1px solid var(--warn);color:var(--warn);padding:10px 12px;border-radius:8px;margin:12px 0}
.card{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:12px 14px;margin:12px 0;overflow-x:auto}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 10px;font-size:.85rem;white-space:nowrap}
.overdue,.disputed{color:var(--warn);font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left;vertical-align:top}
td:first-child{white-space:nowrap}
ol.timeline{list-style:none;padding-left:0}
ol.timeline li{border-left:3px solid var(--line);padding:2px 0 10px 12px;margin-left:4px}
blockquote{margin:.3em 0;padding-left:10px;border-left:3px solid var(--line);color:var(--muted);font-size:.85rem}
code{font-size:.8rem;word-break:break-all}
"""


def esc(value: object) -> str:
    """Escape semua teks dari data sebelum masuk HTML (data berasal dari kontributor)."""
    return escape(str(value), quote=True)


def safe_url(url: str) -> str:
    """Hanya http(s) yang boleh jadi href. Selain itu diganti '#'. Lapis kedua setelah schema."""
    return url if urlparse(url).scheme in {"http", "https"} else "#"


def link(url: str, text: str) -> str:
    return f'<a href="{esc(safe_url(url))}" rel="noopener noreferrer nofollow">{esc(text)}</a>'


def fmt_number(value: float) -> str:
    """Format angka gaya Indonesia: maksimal 2 desimal, koma sebagai pemisah desimal."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def overdue_days(promise: dict, today: date) -> int | None:
    """Jumlah hari lewat tenggat, atau None kalau belum/tidak lewat tenggat."""
    deadline = promise["promise"].get("deadline")
    if not deadline or promise["status"] not in OPEN_STATUSES:
        return None
    delta = (today - date.fromisoformat(deadline)).days
    return delta if delta > 0 else None


def metric_progress(metric: dict) -> dict:
    """Capaian observasi terakhir terhadap target awal (dan target revisi bila ada)."""
    last = metric["observations"][-1]
    revisions = metric.get("target_revisions") or []
    revised = revisions[-1]["value"] if revisions else None
    return {
        "date": last["date"],
        "value": last["value"],
        "quality": last["quality"],
        "target": metric["target"]["value"],
        "pct": last["value"] / metric["target"]["value"] * 100,
        "revised_target": revised,
        "revised_pct": last["value"] / revised * 100 if revised else None,
    }


def status_badge(status: str) -> str:
    label, icon = STATUS_LABELS[status]
    return f'<span class="badge">{icon} {esc(label)}</span>'


def commitment_badge(commitment: str) -> str:
    label, hint = COMMITMENT_LABELS[commitment]
    return f'<span class="badge" title="{esc(hint)}">{esc(label)}</span>'


def latest_review_date(promises: list[dict]) -> str | None:
    dates = [p["review"]["reviewed_at"] for p in promises if p["review"].get("reviewed_at")]
    return max(dates) if dates else None


def jsonld_script(obj: dict) -> str:
    """JSON-LD aman untuk disisipkan di <script>: karakter pembuka tag di-escape agar '</script>' tak bisa lolos."""
    raw = json.dumps(obj, ensure_ascii=False, indent=2)
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">\n{raw}\n</script>'


def claim_review_jsonld(p: dict, base_url: str | None, site_name: str) -> dict | None:
    """schema.org/ClaimReview untuk janji nyata berstatus akhir; None jika tidak berlaku."""
    if not base_url or p.get("fictional") or p["status"] not in CLAIM_RATING:
        return None
    rating, label = CLAIM_RATING[p["status"]]
    base = base_url.rstrip("/")
    source = next(e for e in p["evidence"] if e["id"] == p["promise"]["source_evidence_id"])
    official = p["official"]
    person: dict = {"@type": "Person", "name": official["name"], "jobTitle": official["position"]}
    if official.get("wikidata_id"):
        person["sameAs"] = f"https://www.wikidata.org/wiki/{official['wikidata_id']}"
    return {
        "@context": "https://schema.org",
        "@type": "ClaimReview",
        "url": f"{base}/promises/{p['id']}.html",
        "datePublished": p["review"]["reviewed_at"],
        "inLanguage": "id",
        "author": {"@type": "Organization", "name": site_name, "url": base},
        "claimReviewed": p["promise"]["statement"],
        "itemReviewed": {
            "@type": "Claim",
            "author": person,
            "datePublished": p["promise"]["made_at"],
            "appearance": {"@type": "CreativeWork", "url": source["url"]},
        },
        "reviewRating": {
            "@type": "Rating",
            "ratingValue": rating,
            "bestRating": 5,
            "worstRating": 1,
            "alternateName": label,
        },
    }


def page(title: str, body: str, *, fictional: bool = False, root: str = "", head_extra: str = "") -> str:
    banner = (
        '<div class="banner" role="note"><strong>DATA CONTOH (FIKTIF).</strong> '
        "Nama, organisasi, dan tautan di halaman ini rekaan untuk demonstrasi format.</div>"
        if fictional
        else ""
    )
    robots = '<meta name="robots" content="noindex">' if fictional else ""
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{robots}
<title>{esc(title)}</title>
<style>{CSS}</style>
{head_extra}
</head>
<body>
<p class="muted"><a href="{root}index.html">Promise Tracker</a> · eksperimen open source</p>
{banner}
{body}
<hr>
<p class="muted">Setiap penilaian dapat ditelusuri ke bukti terarsip dan riwayat perubahannya di repositori.
Kode: MIT · Data: CC BY-SA 4.0.</p>
</body>
</html>
"""


def _progress_cell(p: dict) -> str:
    if not p.get("metrics"):
        return "-"
    m = p["metrics"][0]
    prog = metric_progress(m)
    text = f"{fmt_number(prog['value'])} / {fmt_number(prog['target'])} {m['unit']} ({fmt_number(prog['pct'])}%)"
    extra = ""
    if prog["quality"] == "disputed":
        extra += ' <span class="disputed" title="Angka dipersoalkan">⚠</span>'
    if prog["revised_target"] is not None:
        extra += f'<div class="muted">target direvisi: {esc(fmt_number(prog["revised_target"]))}</div>'
    return f"{esc(text)}{extra}"


def _promise_rows(promises: list[dict], today: date, *, prefix: str) -> str:
    rows = []
    for p in promises:
        late = overdue_days(p, today)
        deadline = p["promise"].get("deadline") or "-"
        late_html = f' <span class="overdue">(lewat {late} hari)</span>' if late else ""
        rows.append(
            "<tr>"
            f'<td><a href="{prefix}{esc(p["id"])}.html">{esc(p["title"])}</a>'
            f'<div class="muted">{esc(p["official"]["name"])} · {esc(p["official"]["institution"])}</div></td>'
            f"<td>{status_badge(p['status'])}<div>{commitment_badge(p['commitment'])}</div></td>"
            f"<td>{_progress_cell(p)}</td>"
            f"<td>{esc(deadline)}{late_html}</td>"
            "</tr>"
        )
    return "".join(rows)


_TABLE_HEAD = "<thead><tr><th>Janji</th><th>Status</th><th>Progres</th><th>Tenggat</th></tr></thead>"


def render_index(promises: list[dict], today: date, programs: dict[str, dict] | None = None) -> str:
    counts: dict[str, int] = {}
    for p in promises:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    summary = " · ".join(f"{STATUS_LABELS[s][0]}: {n}" for s, n in sorted(counts.items()))
    reviewed = latest_review_date(promises)
    freshness = f"data terakhir direview {esc(reviewed)}" if reviewed else "belum ada data yang direview"

    used = sorted({p["program"] for p in promises})
    program_links = " · ".join(
        f'<a href="programs/{esc(slug)}.html">{esc((programs or {}).get(slug, {}).get("name", slug))}</a>' for slug in used
    )
    body = f"""<h1>Promise Tracker</h1>
<p>Pelacak janji pejabat publik. Setiap janji punya bukti terarsip, timeline, dan reviewer.</p>
<p class="muted">{esc(len(promises))} janji · {esc(summary)} · {freshness} · situs dibangun {esc(today.isoformat())}</p>
<p class="muted">Program: {program_links}</p>
<div class="card"><table>
{_TABLE_HEAD}
<tbody>{_promise_rows(promises, today, prefix="promises/")}</tbody></table></div>
<p><a href="data.json">Unduh data (JSON)</a></p>"""
    return page("Promise Tracker", body, fictional=any(p.get("fictional") for p in promises))


def render_program(slug: str, program: dict | None, promises: list[dict], today: date) -> str:
    mine = [p for p in promises if p["program"] == slug]
    name = program["name"] if program else slug
    desc = esc(program["description"]) if program else ""
    meta = ""
    if program:
        tags = ", ".join(esc(t) for t in program.get("tags", [])) or "-"
        meta = f'<p class="muted">{esc(program["institution"])} · tag: {tags}</p>'
    table = (
        f'<div class="card"><table>{_TABLE_HEAD}<tbody>{_promise_rows(mine, today, prefix="../promises/")}</tbody></table></div>'
        if mine
        else '<p class="muted">Belum ada janji untuk program ini.</p>'
    )
    body = f"<h1>{esc(name)}</h1><p>{desc}</p>{meta}{table}"
    fictional = bool(program.get("fictional")) if program else False
    return page(name, body, fictional=fictional, root="../")


def _render_metric(metric: dict) -> str:
    prog = metric_progress(metric)
    unit = esc(metric["unit"])
    target = metric["target"]
    lines = [
        f"<h3>{esc(metric['name'])} <span class=\"muted\">({unit})</span></h3>",
        f'<p class="muted">{esc(metric["definition"])}</p>',
        f"<p>Target awal: <strong>{esc(fmt_number(target['value']))}</strong> {unit} "
        f"(ditetapkan {esc(target['set_on'])}, <a href=\"#{esc(target['evidence_id'].lower())}\">{esc(target['evidence_id'])}</a>)</p>",
    ]
    for rev in metric.get("target_revisions", []):
        note = f" {esc(rev['note'])}" if rev.get("note") else ""
        lines.append(
            f"<p>Target direvisi menjadi <strong>{esc(fmt_number(rev['value']))}</strong> {unit} "
            f"pada {esc(rev['date'])} (<a href=\"#{esc(rev['evidence_id'].lower())}\">{esc(rev['evidence_id'])}</a>).{note}</p>"
        )
    rows = []
    for obs in metric["observations"]:
        pct = obs["value"] / target["value"] * 100
        quality_cls = ' class="disputed"' if obs["quality"] == "disputed" else ""
        notes = "".join(
            f'<div class="muted">{esc(n)}</div>' for n in (obs.get("definition_note"), obs.get("note")) if n
        )
        rows.append(
            "<tr>"
            f"<td>{esc(obs['date'])}</td>"
            f"<td>{esc(fmt_number(obs['value']))}</td>"
            f"<td>{esc(fmt_number(pct))}%</td>"
            f"<td{quality_cls}>{esc(QUALITY_LABELS[obs['quality']])}</td>"
            f"<td><a href=\"#{esc(obs['evidence_id'].lower())}\">{esc(obs['evidence_id'])}</a>{notes}</td>"
            "</tr>"
        )
    lines.append(
        '<table><thead><tr><th>Tanggal</th><th>Nilai</th><th>% target awal</th><th>Mutu data</th><th>Sumber &amp; catatan</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    if any(o["quality"] == "disputed" for o in metric["observations"]):
        lines.append('<p class="muted">⚠ Angka bertanda "Dipersoalkan" bertentangan dengan sumber lain atau definisinya tidak konsisten.</p>')
    return "\n".join(lines)


def _render_response(p: dict) -> str:
    resp = p.get("response") or {"status": "not_yet_sought"}
    label = RESPONSE_LABELS[resp["status"]]
    parts = [f"<p><strong>{esc(label)}</strong>"]
    if resp.get("requested_at"):
        parts.append(f" · diminta {esc(resp['requested_at'])}")
    if resp.get("received_at"):
        parts.append(f" · diterima {esc(resp['received_at'])}")
    parts.append("</p>")
    if resp.get("summary"):
        ref = f' (<a href="#{esc(resp["evidence_id"].lower())}">{esc(resp["evidence_id"])}</a>)' if resp.get("evidence_id") else ""
        parts.append(f"<p>{esc(resp['summary'])}{ref}</p>")
    return "".join(parts)


def _render_corrections(p: dict) -> str:
    items = p.get("corrections") or []
    if not items:
        return '<p class="muted">Belum ada koreksi. Seluruh riwayat perubahan tercatat di Git.</p>'
    lis = "".join(f"<li><time datetime=\"{esc(c['date'])}\">{esc(c['date'])}</time> {esc(c['summary'])}</li>" for c in items)
    return f"<ul>{lis}</ul>"


def _render_related(p: dict, known_ids: set[str] | None) -> str:
    items = p.get("related") or []
    if not items:
        return ""
    lis = []
    for rel in items:
        target = esc(rel["id"])
        ref = f'<a href="{target}.html">{target}</a>' if known_ids is None or rel["id"] in known_ids else target
        lis.append(f"<li>{esc(RELATION_LABELS[rel['relation']])}: {ref}</li>")
    return f"<h2>Terkait</h2><ul>{''.join(lis)}</ul>"


def render_promise(
    p: dict,
    today: date,
    *,
    known_ids: set[str] | None = None,
    program: dict | None = None,
    base_url: str | None = None,
    site_name: str = "Promise Tracker",
) -> str:
    evidence = {e["id"]: e for e in p["evidence"]}
    late = overdue_days(p, today)
    late_html = f'<p class="overdue">Melewati tenggat {late} hari tanpa status akhir.</p>' if late else ""
    note = f"<p><strong>Catatan penilaian:</strong> {esc(p['status_note'])}</p>" if p.get("status_note") else ""

    timeline = []
    for ev in p["timeline"]:
        refs = ", ".join(f'<a href="#{esc(i.lower())}">{esc(i)}</a>' for i in ev["evidence_ids"])
        timeline.append(
            f'<li><time datetime="{esc(ev["date"])}">{esc(ev["date"])}</time> '
            f'<span class="badge">{esc(KIND_LABELS[ev["kind"]])}</span><br>{esc(ev["summary"])} '
            f'<span class="muted">Bukti: {refs}</span></li>'
        )

    ev_rows = []
    for e in p["evidence"]:
        pub = e.get("published_at") or "-"
        extras = ""
        if e.get("quote"):
            extras += f"<blockquote>“{esc(e['quote'])}”</blockquote>"
        if e.get("locator"):
            extras += f'<div class="muted">Letak: {esc(e["locator"])}</div>'
        lang = f" · {esc(e['language'])}" if e.get("language") else ""
        ev_rows.append(
            f'<tr id="{esc(e["id"].lower())}">'
            f'<td>{esc(e["id"])}</td>'
            f'<td>{link(e["url"], e["title"])}<div class="muted">{esc(e["publisher"])} · {esc(pub)}{lang}</div>{extras}</td>'
            f'<td>{esc(EVIDENCE_LABELS[e["type"]])}</td>'
            f'<td>{link(e["archive_url"], "arsip")}<div class="muted">{esc(e["archived_at"])}</div>'
            f'<code>{esc(e["sha256"][:16])}…</code></td>'
            "</tr>"
        )

    source = evidence[p["promise"]["source_evidence_id"]]
    reviewers = ", ".join(esc(r) for r in p["review"]["reviewers"]) or "-"
    reviewed_at = p["review"].get("reviewed_at") or "belum"
    deadline = p["promise"].get("deadline") or "tidak ditentukan"
    behalf = (
        f" · atas nama/permintaan: {esc(p['promise']['on_behalf_of'])}" if p["promise"].get("on_behalf_of") else ""
    )
    program_html = (
        f'<a href="../programs/{esc(p["program"])}.html">{esc(program["name"] if program else p["program"])}</a>'
    )
    metrics_html = ""
    if p.get("metrics"):
        metrics_html = "<h2>Metrik</h2>" + "\n".join(_render_metric(m) for m in p["metrics"])

    body = f"""<h1>{esc(p['title'])}</h1>
<p>{status_badge(p['status'])} {commitment_badge(p['commitment'])} <span class="muted">{esc(p['id'])} · {program_html}</span></p>
{late_html}
<div class="card">
<p><strong>Janji:</strong> {esc(p['promise']['statement'])}</p>
<p class="muted">{esc(p['official']['name'])}, {esc(p['official']['position'])}, {esc(p['official']['institution'])}{behalf}<br>
Diucapkan {esc(p['promise']['made_at'])} · Tenggat {esc(deadline)} · Sumber janji: <a href="#{esc(source['id'].lower())}">{esc(source['id'])}</a></p>
{note}
</div>
{metrics_html}
<h2>Timeline</h2>
<ol class="timeline">{''.join(timeline)}</ol>
<h2>Bukti</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>Sumber</th><th>Jenis</th><th>Arsip &amp; hash</th></tr></thead>
<tbody>{''.join(ev_rows)}</tbody></table></div>
<h2>Tanggapan pihak terkait (hak jawab)</h2>
{_render_response(p)}
<h2>Riwayat koreksi</h2>
{_render_corrections(p)}
{_render_related(p, known_ids)}
<p class="muted">Reviewer: {reviewers} · direview {esc(reviewed_at)}</p>"""

    ld = claim_review_jsonld(p, base_url, site_name)
    return page(p["title"], body, fictional=bool(p.get("fictional")), root="../", head_extra=jsonld_script(ld) if ld else "")


def build(
    data_dir: Path,
    out_dir: Path,
    today: date,
    *,
    programs_dir: Path | None = validate.DEFAULT_PROGRAMS_DIR,
    base_url: str | None = None,
    site_name: str = "Promise Tracker",
) -> None:
    """Validasi lalu tulis situs. Melempar ValueError kalau data tidak valid."""
    if base_url is not None and urlparse(base_url).scheme not in {"http", "https"}:
        raise ValueError(f"base_url harus http(s): {base_url!r}")
    problems = validate.validate_directory(data_dir, today, programs_dir=programs_dir)
    if problems:
        lines = [f"{name}: {msg}" for name, errs in problems.items() for msg in errs]
        raise ValueError("Data tidak valid, build dibatalkan:\n" + "\n".join(lines))

    promises = [validate.load_yaml(path) for path in sorted(data_dir.glob("*.yaml"))]
    programs, _ = validate.load_programs(programs_dir)
    known_ids = {p["id"] for p in promises}

    (out_dir / "promises").mkdir(parents=True, exist_ok=True)
    (out_dir / "programs").mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_index(promises, today, programs), encoding="utf-8")
    for p in promises:
        html = render_promise(
            p, today, known_ids=known_ids, program=(programs or {}).get(p["program"]), base_url=base_url, site_name=site_name
        )
        (out_dir / "promises" / f"{p['id']}.html").write_text(html, encoding="utf-8")

    slugs = sorted(set(programs or {}) | {p["program"] for p in promises})
    for slug in slugs:
        html = render_program(slug, (programs or {}).get(slug), promises, today)
        (out_dir / "programs" / f"{slug}.html").write_text(html, encoding="utf-8")

    export = {
        "schema": "v2",
        "built_on": today.isoformat(),
        "last_reviewed_on": latest_review_date(promises),
        "license": "CC BY-SA 4.0",
        "programs": list((programs or {}).values()),
        "promises": promises,
    }
    (out_dir / "data.json").write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build situs statis promise tracker")
    parser.add_argument("--data", type=Path, default=validate.DEFAULT_DATA_DIR)
    parser.add_argument("--programs", type=Path, default=validate.DEFAULT_PROGRAMS_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--base-url", default=None, help="URL dasar situs; mengaktifkan JSON-LD ClaimReview")
    parser.add_argument("--site-name", default="Promise Tracker")
    args = parser.parse_args(argv)

    try:
        build(args.data, args.out, args.today, programs_dir=args.programs, base_url=args.base_url or None, site_name=args.site_name)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Build selesai -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
