# Serah terima RAG untuk tim: memasukkan data tambahan

Untuk siapa: Eca, Eileen, Salwa, Calzy, dan siapa pun yang mengumpulkan sumber untuk asisten "Ask SEAmon". Ditulis 2026-11-15. Latar belakang teknis ada di [RAG_DESIGN.md](RAG_DESIGN.md) dan [supabase/README.md](../../supabase/README.md); dokumen ini hanya menjawab **"data saya taruh di mana dan bagaimana masuknya?"**

## 1. Gambaran singkat

Asisten menjawab dari dua jenis sumber. Masing-masing punya pintu masuk sendiri.

| Jenis | Contoh | Taruh di | Masuk ke | Perintah |
|---|---|---|---|---|
| **Literatur** (teks) | makalah, review, catatan evidence yang sudah diperiksa | `research/corpus/<id>.md` | `rag.sources`, `rag.chunks` (dicari lewat vektor + kata kunci) | `node scripts/rag/ingest.mjs` |
| **Angka** (deret waktu per lokasi) | suhu laut MUR, NASA POWER | `research/data-access/` (format Eca) | `env.sites`, `env.daily` | `node scripts/env/load.mjs` |

Pertanyaan seperti "apa kata studi soal salinitas?" dijawab dari literatur. Pertanyaan seperti "berapa suhu laut di Maluku?" dijawab dari angka. Jangan memasukkan tabel angka ke korpus teks: asisten akan membacanya sebagai kalimat dan bisa salah mengutip. Angka selalu lewat jalur angka.

Aturan dasarnya sama untuk keduanya: **asisten hanya boleh menjawab dari apa yang ada di sini dan harus menyebut sumbernya. Kalau tidak ada, ia menjawab "belum cukup bukti".** Jadi lebih baik sedikit sumber yang sudah diverifikasi daripada banyak sumber yang belum.

## 2. Keadaan sekarang (cek dulu supaya tidak menggandakan kerja)

- **Angka sudah dimuat:** 19 lokasi, 60.268 baris. NASA POWER bulanan (11 variabel, 2003 sampai 2024) dan MUR suhu laut (satu nilai tiap 30 hari, 2003-01-01 sampai 2024-12-08). Datanya **berakhir Desember 2024**, jadi pertanyaan "minggu lalu" dijawab bahwa data tidak ada.
- **Literatur masih kosong.** `research/corpus/` hanya berisi README. Isi `research/evidence/` adalah lead yang belum terverifikasi dan sengaja **tidak** dipakai sebagai bukti.
- Belum dimuat: POWER harian, produk Copernicus, dan `results/trends.csv` (hasil tren Eca).

## 3. Menambah literatur

### 3.1 Siapkan file

Satu file Markdown per sumber di `research/corpus/`. Nama file bebas, tapi pakai `id` sumber agar mudah dicari. Format lengkap ada di [`research/corpus/README.md`](../../research/corpus/README.md). Ringkasnya:

```markdown
---
id: doi:10.xxxx-yyyy                 # huruf, angka, dan . _ : -   (tanpa garis miring)
title: Judul lengkap sumber
citation: Penulis (tahun). Judul. Jurnal volume(halaman). doi
doi: 10.xxxx/yyyy
url: https://doi.org/10.xxxx/yyyy
publisher: Penerbit
year: 2026
species: [Kappaphycus alvarezii]     # takson seperti yang ditulis sumber
countries: [Philippines]
evidence_grade: B                    # sesuai research/evidence/README.md
license: CC-BY-4.0                   # yang BOLEH kita simpan; ragu = tanya dulu
verified_by: Nama Pemeriksa          # kosongkan sampai sudah diperiksa
verified_on: 2026-11-20              # YYYY-MM-DD, selalu berpasangan dengan verified_by
---
## Methods
Isi bagian ini, hanya sejauh lisensi mengizinkan. Pakai heading `##`;
judul heading muncul sebagai "bagian" pada kutipan.
```

Yang wajib: `id`, `title`, `citation`, `license`. Salah ketik nama field (misalnya `verfied_by`) **menghentikan** proses, jadi tidak ada sumber yang diam-diam lolos tanpa verifikasi.

### 3.2 Apa yang boleh dimasukkan

- Hanya teks yang lisensinya mengizinkan kita menyimpan dan menampilkan ulang. Banyak makalah berbayar **tidak** boleh disalin utuh. Pilihannya: kutipan pendek dengan nomor halaman, atau cari salinan akses terbuka. Kalau ragu, tanyakan sebelum menaruh teksnya di repo. Repo ini privat sekarang, tapi teks yang masuk ke database juga bisa dikutip asisten di situs publik, dan repo bisa saja dibuka nanti.
- Bahasa Inggris lebih baik. Model embedding (gte-small) hampir hanya paham bahasa Inggris, jadi sumber berbahasa Indonesia akan sulit ditemukan.
- Tulis hanya yang dikatakan sumber. Jangan menambah ringkasan atau tafsiran sendiri di dalam file korpus: asisten akan menganggapnya kutipan sumber.

### 3.3 Verifikasi sebelum mengisi `verified_by`

Sumber baru boleh dimuat tanpa `verified_by` (tersimpan tapi **tidak pernah dicari**). Isi `verified_by` dan `verified_on` hanya setelah pemeriksa mencocokkan dengan dokumen aslinya:

- sitasi dan DOI benar
- spesies/strain yang diteliti dan nama takson
- lokasi dan konteks lingkungan
- rancangan studi, lama paparan, ukuran efek dan batas statistiknya
- ambang atau satuan hanya jika sumber memang menyatakannya
- lisensi, dan apakah kita boleh menyimpan teksnya

Daftar lengkap ada di [`research/evidence/README.md`](../../research/evidence/README.md). Catatan penting dari brief: studi Tawi-Tawi tidak menemukan korelasi signifikan untuk sebagian besar variabel. Jangan mengubah asosiasi umum menjadi aturan suhu yang berlaku di mana-mana.

### 3.4 Memasukkannya

**Cara yang disarankan (tanpa berbagi kunci):** buat pull request berisi file `.md` di `research/corpus/`, lalu Radit (atau siapa pun yang memegang kunci Supabase) menjalankan ingest. Dengan begitu isi korpus ikut ditinjau.

Kalau kamu memegang kuncinya sendiri:

```bash
export SUPABASE_URL=...                # dari Radit; jangan di-commit
export SUPABASE_SERVICE_ROLE_KEY=...   # JWT service_role lama; rahasia
node scripts/rag/ingest.mjs --dry-run  # periksa format dan jumlah potongan, tanpa jaringan
node scripts/rag/ingest.mjs            # embed dan simpan
```

Aman dijalankan ulang: teks yang tidak berubah tidak di-embed ulang, hanya metadatanya yang diperbarui (misalnya setelah `verified_by` diisi). Setelah selesai tiap file mencetak jumlah potongan dan status "verified" atau "NOT verified".

### 3.5 Mengecek hasilnya

Buka https://seamon.seagis.app, tanyakan sesuatu yang **jawabannya ada di sumber tadi**, dengan kata-kata yang berbeda dari teksnya, dalam bahasa Inggris dan Indonesia. Periksa:

- jawaban menyebut sitasi bernomor, dan tautannya benar
- kalimat yang dikutip memang didukung potongan teks itu (sistem hanya memastikan kutipan berasal dari sumber yang diambil, **bukan** bahwa kalimatnya benar)
- pertanyaan yang jawabannya tidak ada di sumber dijawab "belum cukup bukti", bukan ditebak

Catat pertanyaan yang gagal. Pertanyaan-pertanyaan itu menjadi set evaluasi (lihat bagian 6).

## 4. Menambah data angka

Pintu masuknya format Eca di [`research/data-access/`](../../research/data-access/README.md): `sites.json` (daftar lokasi), `data/power_monthly.csv`, `data/mur_sst.csv`, dan `power/daily/<site>.csv`.

```bash
node scripts/env/load.mjs --dry-run             # parse dan validasi, tanpa jaringan
node scripts/env/load.mjs                       # muat lalu bandingkan database dengan file
node scripts/env/load.mjs --daily PRECTOTCORR   # POWER harian untuk variabel pilihan saja
```

- **Lokasi baru:** tambahkan ke `sites.json` dan sediakan file datanya; pemuat menolak lokasi yang tidak dikenal atau koordinat yang berpindah.
- **Aman diulang:** baris di-upsert. Di akhir, pemuat membandingkan jumlah dan rentang tanggal tiap seri dengan isi file.
- **Tidak ada pengisian atau interpolasi.** Nilai kosong tetap kosong (null), satuan tetap satuan sumber.
- **POWER harian tidak dimuat secara default:** satu variabel sekitar 153.000 baris. Pilih variabel yang memang dibutuhkan pertanyaan.
- **Produk baru** (Copernicus, hasil tren `trends.csv`) belum didukung pemuat. Menambahkannya butuh perubahan kode kecil, dan keputusan produk: tren adalah hasil turunan dengan catatan sendiri, bukan data mentah. Hubungi Radit atau Eca sebelum mengerjakannya.
- Nama produk membawa resolusi waktu (`POWER-monthly`, `MUR-30d`) karena asisten membacanya. Beri nama yang jujur untuk produk baru.

## 5. Aturan yang tidak boleh dilanggar

- **Jangan menaruh kunci di repo, chat, atau issue.** `SUPABASE_SERVICE_ROLE_KEY` bisa melakukan hampir apa saja di database. Pakai variabel lingkungan atau secret manager.
- **Hanya project staging `nasa-seagis`.** Jangan arahkan skrip ke project IoT produksi.
- **Jangan menandai sumber "verified" supaya cepat muncul.** Itu satu-satunya hal yang menahan asisten agar tidak mengutip klaim yang belum diperiksa.
- **Jangan menulis ambang, tingkat risiko, atau penyebab wabah ke file korpus** kecuali sumber aslinya menyatakannya, lengkap dengan spesies, tempat, dan kondisinya.
- Perubahan di `scripts/**`, `worker/**`, atau `earth-globe/**` yang di-merge ke `main` otomatis **deploy ke produksi**. Perubahan hanya di `research/**` dan `docs/**` tidak.

## 6. Yang masih terbuka (bantuan sangat diterima)

- **Sumber pertama.** 5 sampai 10 sumber terverifikasi: makalah acuan dari brief (DOI `10.1007/s10499-026-02486-2`) ditambah makalah tentang *Kappaphycus*, ice-ice, dan suhu atau salinitas. Siapa memilih, siapa memverifikasi?
- **Set evaluasi.** 40 sampai 60 pertanyaan yang ditulis orang yang paham domainnya, dengan jawaban yang diharapkan: jawab dengan sumber X, atau memang harus "belum cukup bukti". Belum ada, dan inilah yang dipakai untuk memilih model dan menyetel ambang kemiripan (`MIN_SIMILARITY`, tebakan awal 0,8).
- **Lisensi dan penyimpanan teks** (bagian 3.2), dan **lama penyimpanan log pertanyaan**. Log sekarang hanya mencatat nama tool dan id potongan, tanpa teks pertanyaan dan alamat.
- Pada branch `feat/live-seagis-data`, mock level hanya aktif dengan `?demo=levels`. Jalur default membaca seri observasi melalui `/api/environment`; level biologis tetap `Insufficient Data` sampai aturan spesies ditinjau dan diaktifkan. Jangan menafsirkan observasi sebagai diagnosis penyakit.

## 7. Masalah yang sering muncul

| Gejala | Penyebab biasa |
|---|---|
| `front matter needs "title"` / `unknown front matter key` | field wajib hilang atau nama field salah ketik |
| `verified_by and verified_on go together` | isi keduanya atau kosongkan keduanya |
| `id ... may only use letters, digits and . _ : -` | ada `/` di `id`; ganti dengan `-` |
| Sumber dimuat tapi tidak pernah muncul di jawaban | belum `verified_by`, atau teksnya jauh dari kata-kata pertanyaan (model embedding lemah di bahasa non-Inggris) |
| Asisten menjawab "belum cukup bukti" padahal sumbernya ada | ambang kemiripan terlalu ketat, atau potongan terlalu panjang/umum; catat pertanyaannya untuk set evaluasi |
| `/api/ask` menjawab 503 atau 502 | rahasia Worker belum terpasang, atau semua model gratis sedang sibuk; halaman otomatis memakai jawaban bawaan |
| Skrip menolak lokasi/tanggal/nilai | data tidak cocok dengan `sites.json`; perbaiki sumbernya, jangan melonggarkan pemuat |

## 8. Peta file

| Path | Isi |
|---|---|
| `research/corpus/` | sumber literatur (`.md`), README format |
| `research/data-access/` | data angka Eca (CSV, `sites.json`) |
| `research/evidence/` | lead dan daftar periksa verifikasi (belum terverifikasi) |
| `scripts/rag/ingest.mjs` | memuat korpus teks |
| `scripts/env/load.mjs` | memuat data angka |
| `supabase/` | migrasi, fungsi `embed`, README keadaan terakhir |
| `worker/` | endpoint `/api/ask` (model, tool, validasi jawaban) |
| `docs/Radit/RAG_DESIGN.md` | rancangan dan alasan keputusan |
