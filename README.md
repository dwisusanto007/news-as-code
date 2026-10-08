# Promise Tracker (news as code)

Eksperimen open source: melacak janji pejabat publik seperti mengelola kode.
Satu janji = satu file YAML. Perubahan status = pull request. Riwayat penilaian = `git log`.

> Data di `data/promises/` adalah **contoh fiktif**. Kasus nyata pertama (MBG) masih berupa **draf** di `data/drafts/`
> dan belum boleh dibaca sebagai penilaian: arsip, hash, hak jawab, dan reviewer belum lengkap.

## Mode saat ini: pengumpulan data

Prioritas awal adalah mengumpulkan data, jadi CI otomatis hanya memeriksa **bentuk file terhadap skema** (`ci.yml`).
Aturan editorial penuh, verifikasi hash, dan pencocokan reviewer ada di `ci-full.yml` dan dijalankan **manual** dari tab Actions
saat data siap terbit. Selama mode ini, simpan semua entri di `data/drafts/` dan jangan beri status akhir tanpa review.

Tidak paham Git? Buka **Issues → New issue → Usulkan janji pejabat publik**; maintainer yang mengubahnya jadi data.

## Prinsip

- **Setiap klaim punya bukti terarsip**: URL asli + snapshot Wayback bertimestamp + SHA-256 (diverifikasi oleh `ci-full` saat dijalankan).
- **Status akhir butuh standar tinggi**: ≥2 penerbit berbeda, ≥1 dokumen primer/saksi, ≥2 reviewer yang benar-benar approve PR, dan hak jawab sudah diupayakan (ditegakkan oleh `ci-full`).
- **Adil terhadap yang dinilai**: tiap janji punya `commitment` (janji tegas / target / harapan / proyeksi). Harapan dan proyeksi tidak bisa dinilai "ingkar".
- **Angka terstruktur dan jujur soal ketidakpastian**: metrik punya definisi, target (beserta revisinya), dan mutu data (`reported` / `provisional` / `disputed`).
- **Transparan**: koreksi dicatat di halaman; riwayat lengkap ada di Git.
- **Hanya figur publik, hanya sumber publik, hanya dalam kapasitas jabatan.**

## Struktur

```
schema/promise.schema.json     # struktur janji (JSON Schema)
schema/program.schema.json     # struktur program/topik
data/promises/P-YYYY-NNNN.yaml # janji yang sudah terbit (standar penuh)
data/drafts/                   # draf; hanya diperiksa konsistensinya
data/programs/<slug>.yaml      # program yang mengelompokkan janji
tools/validate.py              # skema + aturan editorial
tools/build.py                 # situs statis -> dist/ (+ ClaimReview JSON-LD)
tools/verify_evidence.py       # cocokkan sha256 dengan snapshot Wayback
tools/check_reviewers.py       # cocokkan reviewer YAML dengan approval PR
tools/archive.py               # bantu kontributor: arsipkan URL + hitung hash
docs/GOVERNANCE.md             # apa yang ditegakkan mesin vs manusia, setelan GitHub
tests/                         # pytest
```

## Memulai

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m tools.validate             # data terbit (gerbang CI)
python -m tools.validate --drafts    # draf
python -m pytest -q                  # unit test
python -m tools.build                # hasil di dist/
python -m tools.build --base-url https://akun.github.io/news-as-code   # + JSON-LD ClaimReview
python -m tools.archive https://sumber.example/halaman --save          # archive_url, archived_at, sha256
```

Gunakan `python -m tools.<nama>` (bukan `python tools/<nama>.py`) agar impor antar modul berfungsi.

## Status janji

| Status | Arti |
|---|---|
| `not_started` | Belum ada tindakan yang terbukti |
| `in_progress` | Ada tindakan/progres terbukti, belum selesai |
| `fulfilled` | Terpenuhi sesuai ukuran di janji |
| `partially_fulfilled` | Sebagian terpenuhi (jelaskan di `status_note`) |
| `broken` | Tenggat lewat atau dibatalkan resmi tanpa terpenuhi (hanya `firm_promise`/`target`) |
| `unverifiable` | Janji terlalu kabur atau bukti tidak tersedia |

Janji terbuka yang melewati tenggat otomatis ditandai "lewat tenggat" di situs.

## Keterbatasan yang disengaja

- Validator memeriksa **bentuk dan konsistensi**, bukan **kebenaran**. Kebenaran dinilai reviewer manusia.
- "Penerbit berbeda" bukan jaminan independen (dua media yang mengutip satu siaran pers = satu sumber). Reviewer menilainya.
- Verifikasi hash otomatis hanya untuk Wayback; arsip lain diperiksa manual.
- `tools/archive.py` diuji dengan fetcher palsu, belum terhadap layanan Wayback sungguhan.
- Tidak ada "pendeteksi kebohongan". Yang dinilai: apakah janji ditepati, berdasarkan bukti.
- Penegakan reviewer dan status check butuh setelan branch protection di GitHub (lihat `docs/GOVERNANCE.md`).

## Lisensi

Kode: MIT (`LICENSE`). Data: CC BY-SA 4.0 (`LICENSE-DATA.md`). Sitasi: `CITATION.cff`.
