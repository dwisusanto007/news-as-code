# Panduan Kontribusi

## Aturan etika (tidak bisa ditawar)

1. **Hanya figur publik dalam kapasitas jabatannya.** Tidak ada alamat, keluarga, kesehatan, atau data pribadi.
2. **Hanya sumber publik.** Tidak ada data bocoran atau hasil peretasan.
3. **Fakta ≠ dugaan.** Jangan menulis motif, niat, atau "pasti bohong". Tulis apa yang dijanjikan, apa yang terbukti dilakukan.
4. **Rumusan netral dan bisa diuji.** "Memperbaiki 50 km jalan sebelum akhir 2026" bagus. "Membangun daerah yang maju" tidak bisa dinilai, beri status `unverifiable`.
5. **Koreksi itu normal.** Bukti baru atau kesalahan bisa dikoreksi lewat PR; riwayatnya tetap publik.

Isu hukum (mis. pencemaran nama baik) dapat berlaku di yurisdiksi Anda. Proyek ini bukan nasihat hukum.

## Menambah janji

1. Salin file contoh ke `data/promises/P-<tahun>-<nomor 4 digit>.yaml`. Nama file harus sama dengan `id`.
2. Hapus `fictional: true` untuk data nyata.
3. Untuk **setiap** bukti: simpan snapshot ke Wayback Machine/archive.ph/perma.cc, lalu isi `archive_url`, `archived_at`, dan `sha256` (hash file snapshot, mis. `sha256sum snapshot.html`).
4. Jalankan `python tools/validate.py` dan `python -m pytest -q` sebelum PR.

## Standar bukti

Urutan bobot: dokumen primer > saksi langsung > media > sumber sekunder.

Status `fulfilled`, `partially_fulfilled`, `broken` hanya lolos jika:

- bukti dari minimal 2 penerbit berbeda, minimal satu primer/saksi langsung
- minimal 2 reviewer dan `reviewed_at` terisi
- `status_note` menjelaskan alasan penilaian
- ada event tindakan/pembaruan/hambatan di timeline

## Review

- Reviewer memeriksa bukti satu per satu, bukan hanya membaca ringkasan.
- Penulis PR tidak boleh menjadi reviewernya sendiri.
- Perbedaan penilaian dibahas di komentar PR, bukan diselesaikan dengan mengubah status diam-diam.
