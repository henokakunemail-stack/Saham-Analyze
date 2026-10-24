# Rencana Perbaikan SAHAM (24 Okt 2026)

Dasar: penilaian jujur 23 Okt 2026. Kekurangan terbesar dan perbaikannya:

| # | Kekurangan | Dijawab di |
|---|---|---|
| K1 | Keunggulan saham LAYAK kecil (+0,12 R di periode uji, ≈ impas setelah biaya) | Bagian 0, 1, 3, 4 |
| K2 | Fundamental dangkal (potret Yahoo, tanpa tren, tanpa arus kas, tanpa pembanding sektor; DER bank dihukum keliru) | Bagian 2 |
| K3 | Pola candlestick belum pernah diuji; ada salah deteksi | Bagian 1 |
| K4 | Bergantung pada Yahoo Finance (tertunda, kadang bolong) | Bagian 5 |
| K5 | Zona beli saham breakout bisa sangat sempit (AAPL: 8 sen) | Bagian 3 |
| K6 | Rekam jejak nyata masih pendek | Bagian 4 |

Aturan yang berlaku untuk semua bagian (sama seperti sebelumnya):
- Perubahan yang menggeser **skor, status, atau level** harus lolos uji historis: dipilih di periode awal
  (sebelum 11 Des 2025), diuji **sekali** di periode uji. Gagal → tidak dipakai, dicatat sebagai "ditolak".
- Yang tidak bisa diuji hanya boleh tampil sebagai **informasi/peringatan**, tidak menambah skor.
- Biaya transaksi tetap tidak dimodelkan dalam perhitungan (sesuai permintaan pengguna); hanya disebut sebagai catatan.
- Setiap bagian selesai dengan: tes otomatis, cek di browser (bursa tutup & sesi berjalan), dokumen hasil, commit.

---

## 0. Top 10: "Cek Tengah Hari" diganti "Analisa Penutupan"

**Tujuan:** patokan = harga penutupan final. Setelah tutup, aplikasi menganalisa ulang dan memberi informasi
yang jujur per saham — bukan memantau harga menit-ke-menit.

**Isi per saham (Top 10 yang tampil selama sesi + watchlist):**
1. **Hasil sesi terakhir vs rencana yang berlaku** (rekap: TP1 tercapai tanpa terisi / harga beli terisi / kena cut loss / tidak turun ke zona).
2. **Rencana untuk sesi berikutnya** dari penutupan final: harga beli (limit), cut loss, TP1, status.
3. **Penilaian jujur**, dihitung dari data uji historis, bukan kata-kata manis:
   - peluang order limit terisi dalam 5 hari bursa menurut jarak penutupan ke harga beli
     (≤ 0,25 ATR ±84 %, 0,25–0,5 ±77 %, 0,5–0,75 ±63 %, 0,75–1 ±50 %, 1–1,5 ±33 %, > 1,5 ±30 %;
     23.923 rencana, kedua periode berselisih ≤ 4 poin kecuali > 1,5 ATR yang sampelnya kecil),
   - ruang ke TP1 dibanding risiko (Rugi : Untung) dengan kalimat yang jelas bila ruangnya sempit,
   - peringatan gerak harian lebih lebar dari jarak cut loss,
   - status dan alasan utamanya.
4. Kepala panel: rata-rata historis per status (LAYAK +0,12 R, TUNGGU −0,05 R, HINDARI −0,12 R, sebelum biaya).

**Waktu:** selalu memakai penutupan final terakhir. Selama sesi berjalan, panel tetap menampilkan analisa
penutupan kemarin (dengan keterangan); harga live hanya muncul di kartu, tidak dipakai untuk menilai.

**Teknis:** endpoint `/api/plan/closing-review` (rekap + rencana + penilaian), komponen UI baru menggantikan
`PlanCheckpoint` di Top 10; rekap memakai bar final saja (bar yang belum final dibuang). Telegram "cek tengah hari"
tidak diubah. Tes: aturan penilaian, pembuangan bar non-final, endpoint.

---

## 1. Pola candlestick: perbaiki deteksi, uji historis, pakai yang terbukti saja (K3)

**Masalah yang sudah ditemukan di kode (`engine/indicators/technical.py`):**
- Hari terkunci satu harga (ARA/ARB) terbaca **Hammer / Hanging Man**.
- Doji dengan ekor bawah terbaca Hammer (cek Hammer dijalankan sebelum Doji).
- Konteks tren hanya "harga sekarang vs 10 hari lalu".
- Pola bullish jauh lebih banyak dari bearish (tidak ada Bearish Engulfing, Dark Cloud Cover, Three Black Crows) → bacaan berat sebelah.
- Bullish Engulfing tanpa syarat lokasi (di support/setelah turun) dan tanpa ukuran minimum.
- Pola ikut menambah skor (pilar setup) padahal belum pernah diuji.

**Langkah:**
1. Perbaiki deteksi: bar terkunci → "Terkunci", Doji dicek sebelum Hammer, ukuran badan dibanding ATR,
   konteks = posisi terhadap EMA20/swing low dan penurunan 5 hari, tambah pola bearish yang setara.
2. Uji peristiwa (event study) 126 saham IDX, 2024–2026: setiap kemunculan pola → return 5 & 10 hari,
   peluang naik, dan hasil rencana (terisi / TP1 dulu / R) dibanding semua hari lain; dipisah periode awal/uji,
   juga dipisah "di area support" vs "di tempat lain".
3. Aturan keputusan: pola dianggap **terbukti** bila di kedua periode lebih baik dari rata-rata dengan
   ≥ 100 kejadian dan arah sama. Yang terbukti boleh tetap/mulai memengaruhi skor (diuji ulang bersama status);
   yang tidak terbukti **dicabut dari skor** dan tampil sebagai informasi.
4. UI: setiap pola menampilkan rekam jejaknya di IDX ("setelah pola ini: naik 10 hari 54 % vs rata-rata 49 %, n = 812").
5. Hasil: `docs/hasil-uji-candlestick.md`.

---

## 2. Laporan keuangan yang lebih dalam (K2)

**Data:** Yahoo menyediakan laporan laba rugi, neraca, dan arus kas tahunan (4–5 tahun) dan ±5 kuartal terakhir
untuk saham IDX (dicek 24 Okt 2026: BBCA, PTBA, ERAA, VICI). Nama baris arus kas berbeda antar emiten
(perlu pemetaan). Disimpan di database, diperbarui mingguan, dengan tanda "data tidak lengkap" bila kosong.

**Metrik baru:**
- Pertumbuhan: pendapatan & laba bersih (tahunan dan TTM vs tahun lalu), konsistensi 3 tahun.
- Kualitas laba: arus kas operasi ÷ laba bersih; arus kas bebas.
- Kesehatan neraca: DER dari neraca (bank & lembaga keuangan **dikecualikan** — DER tinggi wajar untuk bank),
  current ratio, interest coverage.
- Valuasi dibanding **median sektor** di universe (PER, PBV), bukan ambang tetap.
- Bendera merah: rugi beruntun, laba turun 2 tahun, laba naik tapi arus kas operasi negatif, ekuitas negatif.

**Perbaikan logika yang ada:** DER bank tidak lagi dihukum; ambang valuasi relatif sektor.

**Uji historis (sebagian bisa):** laporan tahunan sejak 2021 + jeda publikasi 90 hari → bendera merah
(laba turun, kualitas laba buruk) diuji sebagai saringan status dengan aturan yang sama. Lolos → dipakai sebagai
syarat HINDARI/TUNGGU; tidak lolos → hanya peringatan.

**UI:** bagian "Laporan Keuangan" di detail saham: tabel ringkas 4 tahun + 4 kuartal, grafik kecil
pendapatan/laba, bendera merah dalam bahasa awam, perbandingan sektor.

---

## 3. Uji ulang aturan level dengan simulator yang sudah benar (K5, K1)

1. **Zona beli breakout:** kandidat lebar minimum zona (0,25 / 0,5 ATR) dan harga beli di level breakout.
2. **ATR & pivot "bersih"** (tanpa hari ARA/ARB) — dulu diukur dengan simulator lama.
3. **Rem breadth** (pasar sangat lemah) — dulu diukur dengan simulator lama.
4. **Syarat jarak harga beli** sebagai syarat LAYAK (bukan hanya urutan): mis. LAYAK hanya bila harga beli ≤ 0,5 ATR
   dari penutupan — data awal menunjukkan rencana LAYAK yang jauh merugi di periode uji.
5. **Syarat ruang ke TP1** (Rugi:Untung minimum) diuji ulang dengan simulator baru.

Semua lewat `engine/screener/calibration.py` (pilih di periode awal, uji sekali), hasil di `docs/hasil-akhir-fase1-5.md`.

---

## 4. Rekam jejak nyata yang bisa dipercaya (K6, K1)

**Tujuan:** menjawab dengan jujur "apakah aturan yang dipakai sekarang benar-benar menghasilkan di pasar nyata?" —
bukan menunggu feeling, dan tidak menyimpulkan terlalu cepat.

**Kondisi sekarang:** snapshot prediksi (saham LAYAK, maks. 10/hari) sudah disimpan dan dievaluasi dengan simulator yang
sama. Masalahnya: aturan berubah beberapa kali minggu ini, dan snapshot lama tidak mencatat aturan mana yang dipakai —
mencampur semuanya akan menyesatkan.

**Patokan dari uji historis (aturan sekarang, termasuk Rugi:Untung ≥ 1:1,2):** 164 transaksi LAYAK terisi, rata-rata
**+0,36 R**, simpangan **1,53 R** per transaksi, menang 51 %. Karena hasil per transaksi sangat bervariasi, rentang 90 %
rata-rata setelah n transaksi nyata kira-kira: 10 → ±0,80 R · 30 → ±0,46 R · 50 → ±0,36 R · 100 → ±0,25 R.
Dengan ±1 saham LAYAK per hari dan ±70 % terisi, **30 transaksi butuh ±6–8 minggu**; kepastian yang lebih kuat butuh bulan.

**Langkah:**
1. **Versi aturan per prediksi.** Kolom baru `rules_version` di `prediction_snapshots`; konstanta `RULES_VERSION`
   (mis. `2026-10-24`) dinaikkan setiap kali aturan status/level berubah. Prediksi lama tetap ada, ditandai "aturan lama".
2. **Rekam jejak kumulatif** (`engine/screener/track_record.py`): semua prediksi dengan versi aturan sekarang dievaluasi
   (simulator yang sama: order limit 5 hari, jual separuh di TP1), menghasilkan: jumlah rencana, terisi, selesai, masih
   berjalan, rata-rata R, menang %, profit factor, rentang 90 % rata-rata R.
3. **Penilaian dengan aturan tegas (ditulis sebelum datanya ada):**
   - < 30 transaksi selesai → **"Belum cukup data"** (tampilkan kemajuan n/30 dan rata-rata sementara apa adanya);
   - ≥ 30: batas atas rentang < 0 → **"Merugi di pasar nyata"** (peringatan kuat);
   - ≥ 30: batas atas < +0,36 R → **"Di bawah harapan uji historis"**;
   - ≥ 30: batas bawah > 0 → **"Terbukti positif"**;
   - selain itu → **"Sesuai harapan, belum pasti"**.
4. **Tampilan:** panel paling atas di Histori Prediksi "Nyata vs uji historis" (kemajuan, rata-rata nyata ± rentang,
   patokan uji historis, kalimat penilaian), dan satu baris ringkas di Analisa Penutupan.
5. **Peringatan otomatis:** notifikasi di aplikasi + Telegram saat penilaian berubah menjadi "Merugi" atau "Di bawah harapan".
6. **Laporan mingguan Telegram** ikut menampilkan rekam jejak kumulatif + penilaiannya.
7. Tes: versi aturan tersimpan, pengelompokan per versi, aturan penilaian di tiap ambang, endpoint.

---

## 5. Kesehatan data Yahoo (K4)

**Tujuan:** pengguna tahu kapan data bermasalah, dan saham dengan data yang tidak bisa dipercaya tidak pernah LAYAK.

**Kondisi sekarang:** setiap saham punya laporan kualitas data (`data_quality_reports`: volume nol, tanggal bolong,
lompatan harga, data terlambat), rata-rata skor 99, terendah 72 (PACK, TRUE, BNBR). Tetapi: data **terlambat** tidak
menghalangi LAYAK, tidak ada ringkasan per scan, dan saham yang **gagal diunduh** hilang diam-diam dari daftar.

**Langkah:**
1. **Ringkasan per scan** (`scan_progress` / endpoint `/api/data/health`): saham di-scan, berhasil, gagal diunduh,
   data terlambat (bar terakhir bukan sesi terakhir), dan yang punya masalah kualitas (per jenis), plus waktu scan.
2. **Syarat baru "data segar"** di status: bar terakhir harus sesi bursa terakhir (selisih 0 hari bursa). Terlambat →
   TUNGGU dengan alasan "Data harga terlambat N hari". Tidak memengaruhi uji historis (data historis selalu lengkap).
3. **Skor kualitas rendah** (< 80) → peringatan di kartu & detail (sudah ada di detail; ditambah di kartu).
4. **Tampilan:** satu baris di kepala Top 10 / Screener: "Data: 124 dari 126 saham segar · 2 terlambat · 1 gagal"
   dengan rincian saat diklik; tetap menyebut sumbernya (Yahoo, tertunda ±15 menit).
5. **Batasan yang dicatat jujur:** sumber resmi BEI menolak akses otomatis; tidak ada sumber gratis andal lain. Aplikasi
   tidak bisa memperbaiki data yang salah dari sumbernya — hanya mendeteksi dan menahan status.
6. Tes: deteksi terlambat, syarat data segar, ringkasan scan, endpoint.

---

## Status (24 Okt 2026)

| Bagian | Status |
|---|---|
| 0 Analisa Penutupan | ✅ selesai — peluang terisi dihitung dari jarak ke harga beli (tabel diperbarui) |
| 1 Candlestick | ✅ deteksi diperbaiki, diuji: tidak ada pola yang konsisten di IDX; candle tetap di skor (mencabutnya memperburuk); setiap pola menampilkan rekam jejaknya — `docs/hasil-uji-candlestick.md` |
| 2 Laporan keuangan | ✅ bagian "Laporan keuangan" di detail saham (mata uang laporan, bank dikecualikan dari utang, valuasi vs sektor); bendera merah tidak dipakai sebagai syarat — `docs/hasil-uji-fundamental.md`. Ditemukan & diperbaiki: PBV mustahil di 38 dari 200 saham (emiten berlaporan USD) yang membuat penilaian kesehatan keliru |
| 3 Aturan level & syarat | ✅ zona breakout & level "bersih" ditolak; **syarat Rugi:Untung ≥ 1:1,2 dipakai** (keputusan pengguna 24 Okt; kuat di kedua periode, sampel periode uji 37 transaksi — dipantau di Bagian 4) |
| 4 Rekam jejak nyata | ✅ `rules_version` per prediksi (aturan sekarang `2026-10-24`; 28 prediksi lama dipisah sebagai "aturan lama"); `engine/screener/track_record.py` + `/api/predictions/track-record`; panel "Nyata vs uji historis" di Histori Prediksi, satu baris di Analisa Penutupan; notifikasi + Telegram sekali saat penilaian menjadi "Merugi"/"Di bawah harapan"; laporan mingguan Telegram ikut menampilkan penilaian. Penilaian pertama yang berarti: setelah 30 transaksi selesai (±6–8 minggu) |
| 5 Kesehatan data Yahoo | ✅ syarat ke-8 "Data harga terbaru" (`fresh_ok`): ketinggalan dihitung dari bar indeks sendiri, jadi libur bursa tidak dianggap terlambat; hanya di scan nyata (uji historis tidak berubah). Ringkasan per scan + `/api/data/health`; baris "Data: X dari Y saham segar …" (bisa diklik) di Top 10 & Screener; chip "Data terlambat / kurang baik" di kartu & tabel. Ditemukan & diperbaiki: satu saham berdata terlambat dulu membuat snapshot prediksi hari itu tidak tersimpan sama sekali; sekarang dipakai tanggal terbaru yang dimiliki mayoritas saham. Juga: syarat Rugi:Untung (Bagian 3) belum punya label di daftar syarat — sudah ditambahkan |

## Urutan pengerjaan

0 → 1 → 2 → 3 → 4 → 5. Setiap bagian: tes, cek browser, dokumen, commit, installer di akhir bagian besar.
