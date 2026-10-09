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

**Fase pengumpulan data.** CI otomatis hanya cek skema (`ci.yml`); CI penuh manual (`ci-full.yml`). Alat Python tidak dipakai
pemilik repo; Claude yang menjalankannya sebagai QA lokal (`python -m tools.validate --drafts`) sebelum push. Pemilik repo memakai
Java/Spring Boot dan memilih tanpa tooling kode untuk awal; jangan tambah kerumitan yang menghambat pengumpulan data.

- Skema v2, validator, build, alat verifikasi, dan CODEOWNERS selesai dan lolos test (200). CI penuh hanya jalan manual.
- Kasus pertama: MBG, program `mbg`, semua di `data/drafts/`:
  - `P-2026-0003` penerima 82,9 juta akhir 2025 (usulan `partially_fulfilled`, 66%) -> `P-2026-0004` penerima 82,9 juta 2026 (`in_progress`)
  - `P-2026-0005` SPPG 31.000 akhir 2025 (usulan `partially_fulfilled`, 62%) -> `P-2026-0006` SPPG 32.000 akhir April 2026 (usulan `partially_fulfilled`, 87%)
  - `P-2026-0007` anggaran MBG 2026 Rp335 T dan revisinya (`in_progress`); cakupan "MBG" vs "total BGN" belum dipisahkan
- Terverifikasi lewat kliping (`clippings/mbg.md`): Dadan Hindayana dicopot 2 Jun 2026 dan ditetapkan tersangka Kejagung 3 Jun (dugaan, belum putusan); Nanik S Deyang Kepala BGN 8 Jun-22 Jul 2026; Sudaryono Kepala BGN sejak 22 Jul. BGN menghapus target penerima (21 Jul 2026), yang berdampak ke P-0004. Insentif SPPG Rp6 juta/hari diganti Rp2.000/porsi (5 Okt 2026). Draf P-0003 s.d. 0007 perlu penyesuaian penanggung jawab dan status.
- Pemicu usulan dari publik: formulir Issue "Usulkan janji". Ubah isi issue jadi draf YAML, jangan menyalin mentah.
- Sisa untuk draf MBG (lihat komentar TODO di tiap file): snapshot arsip + hash tiap bukti, cocokkan kutipan ke sumber asli, kirim permintaan hak jawab ke BGN, rekonsiliasi definisi "penerima manfaat" dan angka 61,99 vs 57 juta, cari sumber revisi target 74,56 juta, cari bukti primer janji Agustus 2025 (rekaman/transkrip) dan pembanding independen (BPK/BPS), dua reviewer.
- Setelan GitHub (branch protection, variabel `SITE_BASE_URL`) dilakukan manual oleh pemilik repo.

## Fokus saat ini

Kumpulkan kliping berita, kelompokkan per topik, urut kronologis: `clippings/<program>.md`. Aturan hash/reviewer/hak jawab ditunda sampai ada entri yang siap terbit.

## Ide berikutnya

- Janji MBG lain: insentif SPPG Rp6 juta/hari, sertifikasi SLHS SPPG, target 3T (480 dapur mulai 2 Okt 2026), pagu indikatif 2027.
- Grafik tren metrik di halaman janji.
- Form web yang membuat PR otomatis (opsi hybrid).
- Deploy otomatis ke GitHub Pages.
