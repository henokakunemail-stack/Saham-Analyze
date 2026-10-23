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
   - peluang order limit terisi dalam 5 hari bursa menurut jarak harga beli dari penutupan
     (≤ 0,25 ATR ±78 %, 0,25–0,5 ±61 %, 0,5–1 ±41 %, > 1 ATR ±25 %; dari 23.923 rencana),
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

1. Simpan setiap rencana penutupan (Top 10 + semua LAYAK) — sebagian sudah (`plan_top_<market>`, snapshot prediksi).
2. Evaluasi otomatis tiap hari dengan simulator yang sama (jual separuh di TP1).
3. Panel "Nyata vs uji historis": rata-rata R nyata, rentang ketidakpastian (makin banyak transaksi makin sempit),
   dan aturan tegas "belum bisa dinilai sebelum ≥ 30 transaksi terisi".
4. Laporan mingguan Telegram ikut menampilkan perbandingan ini.
5. Peringatan otomatis bila hasil nyata keluar dari rentang uji historis (strategi mungkin tidak bekerja di kondisi sekarang).

---

## 5. Ketergantungan pada Yahoo (K4)

1. Ringkasan kesehatan data per scan: berapa saham gagal diunduh, terlambat, bolong, atau melompat harga.
2. Saham dengan data terlambat/bolong tidak boleh LAYAK (cek apakah `data_ok` sudah mencakup ini; tambahkan bila belum).
3. Cek silang harga penutupan dengan IHSG (hari tanpa data indeks = libur, bukan saham suspensi) — sebagian sudah.
4. Jujur di UI: "Data dari Yahoo Finance, tertunda ±15 menit; X saham bermasalah di scan ini".
   Sumber alternatif resmi (IDX) menolak akses otomatis; tidak ada sumber gratis andal lain — dicatat sebagai batasan.

---

## Urutan pengerjaan

0 → 1 → 2 → 3 → 4 → 5. Setiap bagian: tes, cek browser, dokumen, commit, installer di akhir bagian besar.
