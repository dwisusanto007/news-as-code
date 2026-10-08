# Promise Tracker (news as code)

Eksperimen open source: melacak janji pejabat publik seperti mengelola kode.
Satu janji = satu file YAML. Perubahan status = pull request. Riwayat penilaian = `git log`.

> Data di `data/promises/` saat ini adalah **contoh fiktif** untuk demonstrasi format.

## Prinsip

- **Setiap klaim punya bukti terarsip**: URL asli + snapshot (Wayback/archive.ph/perma.cc) + SHA-256.
- **Status akhir butuh standar tinggi**: ≥2 penerbit berbeda, ≥1 dokumen primer/saksi langsung, ≥2 reviewer.
- **Transparan**: siapa menilai apa dan kapan, terlihat di riwayat Git.
- **Hanya figur publik, hanya sumber publik, hanya dalam kapasitas jabatan.**

## Struktur

```
schema/promise.schema.json   # struktur data (JSON Schema)
data/promises/P-YYYY-NNNN.yaml
tools/validate.py            # skema + aturan editorial
tools/build.py               # generator situs statis -> dist/
tests/                       # pytest
.github/workflows/ci.yml     # validasi + test + build di setiap PR
```

## Memulai

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python tools/validate.py     # cek data
python -m pytest -q          # unit test
python tools/build.py        # hasil di dist/
```

## Status janji

| Status | Arti |
|---|---|
| `not_started` | Belum ada tindakan yang terbukti |
| `in_progress` | Ada tindakan/progres terbukti, belum selesai |
| `fulfilled` | Terpenuhi sesuai ukuran di janji |
| `partially_fulfilled` | Sebagian terpenuhi (jelaskan di `status_note`) |
| `broken` | Tenggat lewat atau dibatalkan resmi tanpa terpenuhi |
| `unverifiable` | Janji terlalu kabur atau bukti tidak tersedia |

Janji yang melewati tenggat tanpa status akhir otomatis ditandai "lewat tenggat" di situs.

## Keterbatasan yang disengaja

- Validator memeriksa **bentuk dan konsistensi**, bukan **kebenaran**. Kebenaran tetap dinilai manusia (reviewer).
- Independensi bukti diperiksa sebatas nama penerbit berbeda. Penerbit yang berafiliasi tetap perlu dinilai reviewer.
- Tidak ada "pendeteksi kebohongan". Yang dinilai: apakah janji ditepati, berdasarkan bukti.
- Hash hanya membuktikan snapshot tidak berubah, bukan bahwa isinya benar.

## Lisensi

Kode: MIT (`LICENSE`). Data: CC BY-SA 4.0 (`LICENSE-DATA.md`).
