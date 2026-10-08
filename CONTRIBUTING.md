# Panduan Kontribusi

Aturan lengkap tentang apa yang ditegakkan mesin dan apa yang dinilai manusia ada di [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md).

**Cara termudah, tanpa Git:** buka Issues → New issue → *Usulkan janji pejabat publik* dan isi formulirnya.
Cara berikut untuk yang ingin langsung menulis data.

## Aturan etika (tidak bisa ditawar)

1. **Hanya figur publik dalam kapasitas jabatannya.** Tidak ada alamat, keluarga, kesehatan, atau data pribadi.
2. **Hanya sumber publik.** Tidak ada data bocoran atau hasil peretasan.
3. **Fakta ≠ dugaan.** Jangan menulis motif, niat, atau "pasti bohong". Tulis apa yang dijanjikan dan apa yang terbukti dilakukan.
4. **Rumusan netral dan bisa diuji.** "Memperbaiki 50 km jalan sebelum akhir 2026" bagus. "Membangun daerah yang maju" tidak bisa dinilai, beri status `unverifiable`.
5. **Adil pada kekuatan komitmen.** Kutip kalimat aslinya. Kalau berbunyi "mudah-mudahan" atau "diperkirakan", itu `aspiration`/`projection`, bukan janji tegas.
6. **Koreksi itu normal.** Catat di `corrections`; jangan menyunting diam-diam.

Isu hukum (mis. pencemaran nama baik) dapat berlaku di yurisdiksi Anda. Proyek ini bukan nasihat hukum.

## Menambah janji

1. Buat file `data/drafts/P-<tahun>-<nomor 4 digit>.yaml` (nama file = `id`). Gunakan contoh di `data/promises/` sebagai acuan. Pastikan `program` ada di `data/programs/`.
2. Isi `commitment`, `promise.on_behalf_of` (jika atas nama pihak lain), dan metrik di `metrics` untuk janji berukuran angka.
3. Untuk **setiap** bukti, arsipkan dan hitung hash:
   ```bash
   python -m tools.archive https://sumber.example/halaman --save
   ```
   Tempel `archive_url`, `archived_at`, `sha256` yang dicetak. Isi juga `quote` (≤400 karakter) dan `locator`.
4. Minta tanggapan pihak yang dinilai (hak jawab) dan isi `response`. Tunggu minimal 7 hari sebelum `no_reply`.
5. Jalankan `python -m tools.validate --drafts` dan `python -m pytest -q`.
6. Buka PR. Setelah siap terbit: pindahkan file ke `data/promises/`, isi `review.reviewers` dengan **handle GitHub reviewer yang akan meng-approve PR**, dan jalankan `python -m tools.validate`.

## Standar bukti

Urutan bobot: dokumen primer > saksi langsung > media > sumber sekunder.

Status `fulfilled`, `partially_fulfilled`, `broken` hanya lolos jika:

- bukti dari minimal 2 penerbit berbeda, minimal satu primer/saksi langsung
- minimal 2 reviewer, `reviewed_at` terisi, dan keduanya benar-benar meng-approve PR (dicek CI)
- penulis PR bukan salah satu reviewer
- `status_note` menjelaskan alasan penilaian
- ada event tindakan/pembaruan/hambatan di timeline
- `response.status` adalah `received`, `declined`, atau `no_reply`
- `archive_url` Wayback bertimestamp tetap, dan `sha256` cocok dengan snapshot (dicek CI)
- `broken` hanya untuk `commitment` `firm_promise` atau `target`

## Review

- Reviewer memeriksa bukti satu per satu dan mencocokkan angka ke sumber aslinya, bukan hanya membaca ringkasan.
- Reviewer menilai independensi sumber: media yang saling mengutip dihitung satu sumber.
- Perbedaan penilaian dibahas di komentar PR, bukan diselesaikan dengan mengubah status diam-diam.
- Angka yang saling bertentangan ditandai `quality: disputed`, jangan dipilih salah satu.
