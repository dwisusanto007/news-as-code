# Promise Tracker (news as code)

Eksperimen open source: melacak janji pejabat publik seperti mengelola kode.
Satu janji = satu file YAML di `data/promises/`. Lihat `README.md` dan `CONTRIBUTING.md`.

## Perintah

```bash
pip install -r requirements.txt
python tools/validate.py     # skema + aturan editorial (gerbang CI)
python -m pytest -q          # 44 test
python tools/build.py        # situs statis -> dist/
```

## Aturan penting

- Hanya figur publik, hanya sumber publik, pisahkan fakta dari dugaan.
- Jangan pindahkan draf dari `data/drafts/` ke `data/promises/` sebelum arsip, hash, dan 2 reviewer lengkap. Validator akan menolaknya.
- Jangan isi `sha256` atau `archive_url` dengan nilai karangan.
- Data contoh di `data/promises/` fiktif (`fictional: true`).

## Status saat ini

- MVP (skema, validator, build, CI) selesai dan lolos test.
- Kasus pertama: MBG. Draf `P-2026-0003` (target 82,9 juta akhir 2025) dan `P-2026-0004` (target 82,9 juta 2026) ada di `data/drafts/`.
- Sisa: snapshot arsip + hash tiap bukti (semua bertanda `TODO`), review dua orang, lalu pindahkan ke `data/promises/`.

## Ide berikutnya

- Skrip bantu: arsipkan URL ke Wayback dan hitung sha256 otomatis (butuh jaringan, jalankan lokal).
- Janji MBG lain: anggaran 2026 (Rp335 triliun turun ke sekitar Rp219-230 triliun) dan target jumlah SPPG. Perlu riset tambahan.
- Form web yang membuat PR otomatis (opsi hybrid).
