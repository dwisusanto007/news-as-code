# Tata Kelola

Dokumen ini menjelaskan apa yang **ditegakkan otomatis** oleh CI dan apa yang **tetap keputusan manusia**.
Bagian bertanda *usulan* belum disepakati dan harus diputuskan sebelum kasus nyata diterbitkan.

## 1. Apa yang ditegakkan mesin

| Aturan | Alat | Catatan |
|---|---|---|
| Struktur data & tipe | `tools.validate` (JSON Schema) | Field tak dikenal ditolak |
| Konsistensi tanggal, referensi bukti, relasi antar janji | `tools.validate` | Termasuk `supersedes`/`superseded_by` berpasangan |
| Status akhir butuh ≥2 penerbit, ≥1 bukti primer/saksi, ≥2 reviewer, `status_note`, hak jawab | `tools.validate` | `fulfilled`, `partially_fulfilled`, `broken` |
| `broken` hanya untuk `firm_promise` dan `target` | `tools.validate` | Harapan/proyeksi tidak bisa "diingkari" |
| Angka berbeda di tanggal sama harus ditandai `disputed` | `tools.validate` | Mencegah memilih satu angka diam-diam |
| Arsip Wayback bertimestamp tetap, tanggal cocok `archived_at` | `tools.validate` | Bentuk "terbaru" ditolak |
| `sha256` cocok dengan snapshot sebenarnya | `tools.verify_evidence` (job `verify-evidence`) | Hanya Wayback; arsip lain "manual" |
| Reviewer di YAML = orang yang approve PR, bukan penulis PR | `tools.check_reviewers` (job `check-reviewers`) | Mencegah nama reviewer karangan |

## 2. Yang TIDAK bisa ditegakkan mesin

- **Kebenaran isi.** Validator memeriksa bentuk dan konsistensi, bukan fakta. Reviewer wajib membuka tiap sumber.
- **Independensi sumber.** "Penerbit berbeda" bukan jaminan independen: dua media yang mengutip satu siaran pers adalah satu sumber. Reviewer menilai ini.
- **Angka resmi dari pihak yang dinilai.** Bila angka hanya berasal dari instansi yang sedang dinilai, cari pembanding independen (audit BPK, data BPS, laporan LSM) atau tandai keterbatasannya di `status_note`.
- **Tepat-tidaknya `commitment`.** Reviewer memutuskan apakah suatu pernyataan janji tegas, target, harapan, atau proyeksi.
- **Hash arsip non-Wayback.** archive.ph/perma.cc dicek manual oleh reviewer.
- **Integritas pemeriksa itu sendiri.** CI menjalankan kode dari PR. PR yang mengubah `tools/`, `schema/`, `tests/`, atau `.github/` bisa melemahkan aturan di atas, jadi perubahan itu harus di-review ketat (itu alasan `CODEOWNERS` mencakup folder-folder tersebut) dan sebaiknya dipisah dari PR yang mengubah data.

## 3. Setelan GitHub (dilakukan pemilik repo, tidak bisa lewat kode)

Settings → Branches → Branch protection rule untuk `main`:

- [x] Require a pull request before merging, minimal 1 approval
- [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require status checks: `validate-and-build`, `verify-evidence`, `check-reviewers`
- [x] Do not allow force pushes / deletions
- [x] Include administrators
- [ ] Require review from Code Owners: **nyalakan hanya jika ada lebih dari satu maintainer.** GitHub tidak mengizinkan penulis meng-approve PR-nya sendiri, jadi dengan satu maintainer opsi ini membuat PR miliknya sendiri tidak bisa di-merge.

Settings → Secrets and variables → Actions → Variables: isi `SITE_BASE_URL` (mis. `https://akun.github.io/news-as-code`) untuk mengaktifkan JSON-LD ClaimReview.

Catatan `check-reviewers`: job ini jalan ulang saat ada approval baru. Jika status lama masih merah setelah approval masuk, jalankan ulang job-nya dari tab Actions.

## 4. Komitmen

| Nilai | Arti | Boleh `broken`? |
|---|---|---|
| `firm_promise` | Janji tegas ("kami akan ...") | Ya |
| `target` | Angka/tenggat yang ditetapkan sebagai sasaran | Ya |
| `aspiration` | Harapan ("mudah-mudahan ...") | Tidak |
| `projection` | Perkiraan | Tidak |

Kalau ragu antara `target` dan `aspiration`, catat alasannya di `status_note` dan kutip kalimat aslinya di `evidence[].quote`.
Pernyataan yang disampaikan atas nama pihak lain diisi di `promise.on_behalf_of`.

## 5. Rubrik status (*usulan*, belum disepakati)

Untuk janji berukuran angka (`metrics`), bandingkan observasi terakhir pada tenggat dengan target awal:

| Status | Usulan ambang |
|---|---|
| `fulfilled` | ≥ 100% target pada tenggat |
| `partially_fulfilled` | ≥ 50% dan < 100% |
| `broken` | < 50%, atau dibatalkan resmi |
| `unverifiable` | Tidak ada data andal, atau definisi tak bisa dicocokkan |

Ambang ini hanya pedoman; tidak dihitung otomatis. Jika target direvisi, tampilkan keduanya (`target_revisions`) dan jelaskan penilaian terhadap target mana di `status_note`.

## 6. Hak jawab

Sebelum status akhir, pihak yang dinilai harus dimintai tanggapan:

1. Kirim permintaan tertulis melalui kanal resmi (surat, email humas, formulir). Simpan salinan sebagai bukti bila memungkinkan.
2. Isi `response.status: requested` dan `requested_at`.
3. Tunggu **minimal 7 hari**. Setelah itu: `received` (isi `received_at`, `summary`, `evidence_id`), `declined`, atau `no_reply`.
4. Tanggapan yang diterima ditampilkan di halaman apa adanya, bukan diringkas ulang secara sepihak.

## 7. Koreksi

- Kesalahan diperbaiki lewat PR, bukan diedit diam-diam.
- Setiap koreksi substantif dicatat di `corrections` (tanggal + ringkasan) dan tampil di halaman.
- Perubahan status wajib lewat PR dengan alasan di `status_note`.

## 8. Bukti dan hash

- `sha256` dihitung dari **byte mentah** snapshot Wayback bentuk `id_` (`/web/<14 digit>id_/<url>`).
- Cara termudah: `python -m tools.archive https://sumber.example/halaman --save` mencetak `archive_url`, `archived_at`, `sha256` siap tempel.
- Sama sekali jangan mengisi hash atau URL arsip dengan nilai perkiraan. Validator dan CI akan menolaknya.
- Simpan kutipan pendek (`quote`) dan letaknya (`locator`) agar pembaca bisa memeriksa tanpa membaca seluruh sumber.

## 9. Data yang saling bertentangan

- Catat setiap angka sebagai observasi terpisah dengan sumbernya.
- Tandai `quality: disputed` bila bertentangan dengan sumber lain atau definisinya berbeda; jelaskan di `definition_note`/`note`.
- Jangan "memilih" angka yang paling cocok dengan kesimpulan. Jika selisih tak bisa dijelaskan, tulis bahwa belum dijelaskan.

## 10. Risiko dan privasi

- Hanya figur publik dalam kapasitas jabatannya, hanya sumber publik. Tidak ada data pribadi.
- Tulis fakta yang bisa diuji, bukan motif atau niat.
- Handle GitHub kontributor dan reviewer bersifat **publik**. Untuk topik sensitif, kontributor boleh memakai akun pseudonim; reviewer tetap harus akun yang bisa dipertanggungjawabkan secara konsisten.
- Pencemaran nama baik dan UU ITE dapat berlaku. Proyek ini bukan nasihat hukum; konsultasikan sebelum menerbitkan penilaian yang tajam.
- Simpan repo **private** dan penilaian sebagai draf (`data/drafts/`) sampai arsip, hash, hak jawab, dan reviewer lengkap.
