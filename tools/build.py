"""Generator situs statis untuk promise tracker.

Membaca data/promises/*.yaml -> menulis dist/ (index.html, halaman per janji,
dan data.json sebagai open data). Build SELALU memvalidasi dulu; data yang
tidak lolos validasi tidak akan pernah dipublikasikan.

Pemakaian:
    python tools/build.py [--data data/promises] [--out dist] [--today 2026-10-08]
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
OPEN_STATUSES = {"not_started", "in_progress"}

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#5c5c5c;--line:#d9d9d9;--card:#f7f7f7;--accent:#0b5cad;--warn:#8a4b00}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#a8a8a8;--line:#333;--card:#1c1c1c;--accent:#6db3ff;--warn:#ffb866}}
*{box-sizing:border-box}
body{margin:0 auto;max-width:860px;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
a{color:var(--accent)}
h1{font-size:1.5rem;margin:.2em 0}h2{font-size:1.2rem;margin-top:1.8em}
.muted{color:var(--muted);font-size:.9rem}
.banner{background:var(--card);border:1px solid var(--warn);color:var(--warn);padding:10px 12px;border-radius:8px;margin:12px 0}
.card{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:12px 14px;margin:12px 0}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:1px 10px;font-size:.85rem;white-space:nowrap}
.overdue{color:var(--warn);font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left;vertical-align:top}
ol.timeline{list-style:none;padding-left:0}
ol.timeline li{border-left:3px solid var(--line);padding:2px 0 10px 12px;margin-left:4px}
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


def overdue_days(promise: dict, today: date) -> int | None:
    """Jumlah hari lewat tenggat, atau None kalau belum/tidak lewat tenggat."""
    deadline = promise["promise"].get("deadline")
    if not deadline or promise["status"] not in OPEN_STATUSES:
        return None
    delta = (today - date.fromisoformat(deadline)).days
    return delta if delta > 0 else None


def status_badge(status: str) -> str:
    label, icon = STATUS_LABELS[status]
    return f'<span class="badge">{icon} {esc(label)}</span>'


def page(title: str, body: str, *, fictional: bool = False, root: str = "") -> str:
    banner = (
        '<div class="banner" role="note"><strong>DATA CONTOH (FIKTIF).</strong> '
        "Nama, organisasi, dan tautan di halaman ini rekaan untuk demonstrasi format.</div>"
        if fictional
        else ""
    )
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
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


def render_index(promises: list[dict], today: date) -> str:
    rows = []
    for p in promises:
        late = overdue_days(p, today)
        deadline = p["promise"].get("deadline") or "-"
        late_html = f' <span class="overdue">(lewat {late} hari)</span>' if late else ""
        rows.append(
            "<tr>"
            f'<td><a href="promises/{esc(p["id"])}.html">{esc(p["title"])}</a>'
            f'<div class="muted">{esc(p["official"]["name"])} · {esc(p["official"]["institution"])}</div></td>'
            f"<td>{status_badge(p['status'])}</td>"
            f"<td>{esc(deadline)}{late_html}</td>"
            "</tr>"
        )
    counts: dict[str, int] = {}
    for p in promises:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    summary = " · ".join(f"{STATUS_LABELS[s][0]}: {n}" for s, n in sorted(counts.items()))
    body = f"""<h1>Promise Tracker</h1>
<p>Pelacak janji pejabat publik. Setiap janji punya bukti terarsip, timeline, dan reviewer.</p>
<p class="muted">{esc(len(promises))} janji · {esc(summary)} · diperbarui {esc(today.isoformat())}</p>
<div class="card"><table>
<thead><tr><th>Janji</th><th>Status</th><th>Tenggat</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p><a href="data.json">Unduh data (JSON)</a></p>"""
    return page("Promise Tracker", body, fictional=any(p.get("fictional") for p in promises))


def render_promise(p: dict, today: date) -> str:
    evidence = {e["id"]: e for e in p["evidence"]}
    late = overdue_days(p, today)
    late_html = f'<p class="overdue">Melewati tenggat {late} hari tanpa status akhir.</p>' if late else ""
    note = f"<p><strong>Catatan penilaian:</strong> {esc(p['status_note'])}</p>" if p.get("status_note") else ""

    timeline = []
    for ev in p["timeline"]:
        refs = ", ".join(
            f'<a href="#{esc(i.lower())}">{esc(i)}</a>' for i in ev["evidence_ids"]
        )
        timeline.append(
            f'<li><time datetime="{esc(ev["date"])}">{esc(ev["date"])}</time> '
            f'<span class="badge">{esc(KIND_LABELS[ev["kind"]])}</span><br>{esc(ev["summary"])} '
            f'<span class="muted">Bukti: {refs}</span></li>'
        )

    ev_rows = []
    for e in p["evidence"]:
        pub = e.get("published_at") or "-"
        ev_rows.append(
            f'<tr id="{esc(e["id"].lower())}">'
            f'<td>{esc(e["id"])}</td>'
            f'<td>{link(e["url"], e["title"])}<div class="muted">{esc(e["publisher"])} · {esc(pub)}</div></td>'
            f'<td>{esc(EVIDENCE_LABELS[e["type"]])}</td>'
            f'<td>{link(e["archive_url"], "arsip")}<div class="muted">{esc(e["archived_at"])}</div>'
            f'<code>{esc(e["sha256"][:16])}…</code></td>'
            "</tr>"
        )

    source = evidence[p["promise"]["source_evidence_id"]]
    reviewers = ", ".join(esc(r) for r in p["review"]["reviewers"]) or "-"
    reviewed_at = p["review"].get("reviewed_at") or "belum"
    deadline = p["promise"].get("deadline") or "tidak ditentukan"

    body = f"""<h1>{esc(p['title'])}</h1>
<p>{status_badge(p['status'])} <span class="muted">{esc(p['id'])}</span></p>
{late_html}
<div class="card">
<p><strong>Janji:</strong> {esc(p['promise']['statement'])}</p>
<p class="muted">{esc(p['official']['name'])}, {esc(p['official']['position'])}, {esc(p['official']['institution'])}<br>
Diucapkan {esc(p['promise']['made_at'])} · Tenggat {esc(deadline)} · Sumber janji: <a href="#{esc(source['id'].lower())}">{esc(source['id'])}</a></p>
{note}
</div>
<h2>Timeline</h2>
<ol class="timeline">{''.join(timeline)}</ol>
<h2>Bukti</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>Sumber</th><th>Jenis</th><th>Arsip &amp; hash</th></tr></thead>
<tbody>{''.join(ev_rows)}</tbody></table></div>
<p class="muted">Reviewer: {reviewers} · direview {esc(reviewed_at)}</p>"""
    return page(p["title"], body, fictional=bool(p.get("fictional")), root="../")


def build(data_dir: Path, out_dir: Path, today: date) -> None:
    """Validasi lalu tulis situs. Melempar ValueError kalau data tidak valid."""
    problems = validate.validate_directory(data_dir, today)
    if problems:
        lines = [f"{name}: {msg}" for name, errs in problems.items() for msg in errs]
        raise ValueError("Data tidak valid, build dibatalkan:\n" + "\n".join(lines))

    promises = [validate.load_yaml(path) for path in sorted(data_dir.glob("*.yaml"))]

    (out_dir / "promises").mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render_index(promises, today), encoding="utf-8")
    for p in promises:
        (out_dir / "promises" / f"{p['id']}.html").write_text(render_promise(p, today), encoding="utf-8")

    export = {"generated_on": today.isoformat(), "license": "CC BY-SA 4.0", "promises": promises}
    (out_dir / "data.json").write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build situs statis promise tracker")
    parser.add_argument("--data", type=Path, default=validate.DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    try:
        build(args.data, args.out, args.today)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Build selesai -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
