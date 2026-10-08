# Promise Tracker (news as code)

Eksperimen open source: melacak janji pejabat publik seperti mengelola kode.
Satu janji = satu file YAML. Baca `README.md`, `CONTRIBUTING.md`, dan `docs/GOVERNANCE.md`.

## Perintah

Selalu pakai `python -m tools.<nama>` (bukan `python tools/<nama>.py`; impor antar modul gagal).

```bash
pip install -r requirements.txt
python -m tools.validate            # data/promises, standar penuh (gerbang CI)
python -m tools.validate --drafts   # data/drafts, konsistensi saja
python -m pytest -q                 # semua test, tanpa jaringan
python -m tools.build               # situs -> dist/ (--base-url untuk JSON-LD ClaimReview)
python -m tools.archive URL --save  # cetak archive_url/archived_at/sha256 (butuh jaringan)
python -m tools.verify_evidence     # cocokkan sha256 dengan Wayback (butuh jaringan)
```

## Aturan penting

- Hanya figur publik, hanya sumber publik, pisahkan fakta dari dugaan.
- Jangan pindahkan draf dari `data/drafts/` ke `data/promises/` sebelum arsip bertimestamp, hash asli, hak jawab, dan 2 reviewer lengkap. Validator akan menolaknya.
- Jangan pernah mengisi `sha256` atau `archive_url` dengan nilai karangan.
- `commitment` `aspiration`/`projection` tidak boleh berstatus `broken`.
- Angka berbeda di tanggal sama wajib `quality: disputed`.
- Data contoh di `data/promises/` fiktif (`fictional: true`); data fiktif tidak diberi ClaimReview dan ditandai noindex.
- Setiap perubahan aturan/skema harus disertai test.

## Status saat ini

- Skema v2, validator, build, CI (validate, verify-evidence, check-reviewers), CODEOWNERS selesai dan lolos test.
- Kasus pertama: MBG, program `mbg`. Draf `P-2026-0003` (target 82,9 juta akhir 2025, `superseded_by` 0004) dan `P-2026-0004` (target 82,9 juta 2026) di `data/drafts/`.
- Sisa untuk draf MBG (lihat komentar TODO di tiap file): snapshot arsip + hash tiap bukti, cocokkan kutipan ke sumber asli, kirim permintaan hak jawab ke BGN, rekonsiliasi definisi "penerima manfaat" dan angka 61,99 vs 57 juta, cari sumber revisi target 74,56 juta, cari bukti primer janji Agustus 2025 (rekaman/transkrip) dan pembanding independen (BPK/BPS), dua reviewer.
- Setelan GitHub (branch protection, variabel `SITE_BASE_URL`) dilakukan manual oleh pemilik repo.

## Ide berikutnya

- Janji MBG lain: anggaran 2026 (Rp335 triliun turun ke sekitar Rp219-230 triliun) dan target jumlah SPPG. Perlu riset tambahan.
- Grafik tren metrik di halaman janji.
- Form web yang membuat PR otomatis (opsi hybrid).
- Deploy otomatis ke GitHub Pages.
