# Hasil Akhir Fase 1–5 (revisi 23 Okt 2026, simulator diperbaiki)

Semua angka dari backtest walk-forward 126 saham IDX (29 Apr 2024 – 9 Okt 2026, 23.923 rencana, evaluasi tiap 3 hari
bursa, batas 10 hari, **tanpa biaya transaksi**). Periode awal = sebelum 11 Des 2025 (untuk memilih), periode uji =
sejak 11 Des 2025 (diuji sekali). Kalibrasi Fase 1: `docs/hasil-kalibrasi-fase1.md` (angka R di sana memakai simulator
lama — lihat revisi di bawah).

Cara mereproduksi (dari root proyek, memakai candle yang sudah tersimpan di database; ±15 menit CPU):

```bash
python -m engine.screener.calibration compute rows.pkl            # baris backtest walk-forward
python -m engine.screener.calibration report rows.pkl report.json  # pilih di periode awal, uji sekali di periode uji
```

## Revisi: bug simulator dan angka yang dikoreksi

Versi pertama dokumen ini melaporkan LAYAK **+0,341 R** di periode uji. Angka itu terlalu tinggi: setelah TP1 tersentuh,
simulator (`plan_sim`) masih bisa "naik kelas" ke TP2 **tanpa mengecek cut loss** di antaranya — trader yang menahan
untuk TP2 sebenarnya sudah kena cut loss. Bug diperbaiki dan aturan keluar posisi kini eksplisit (`plan_sim.AFTER_TP1`).

## Aturan keluar setelah TP1 (diuji, dipilih di periode awal)

| Aturan | LAYAK periode awal | LAYAK periode uji |
|---|---|---|
| Jual semua di TP1 | +0,032 R | +0,102 R |
| **Jual separuh di TP1, cut loss sisa dinaikkan ke harga beli, sisa incar TP2** | **+0,064 R** | **+0,116 R** |

Dipakai: **jual separuh** (lebih baik di kedua periode). Aplikasi, peringatan dan Telegram kini menyarankan hal ini
saat TP1 tersentuh. Order jual limit yang dilompati harga pembukaan dihitung terisi di harga pembukaan.

## Status LAYAK / TUNGGU / HINDARI (dihitung ulang)

Konfigurasi status yang sama tetap terpilih di periode awal (risiko ≤ 6 %, likuid ≥ Rp2 M/hari, tidak terlalu volatil,
vonis beli, pasar tidak krisis, tanpa ARB baru).

| | Periode awal (rencana / terisi / R / PF) | Periode uji (rencana / terisi / R / PF) |
|---|---|---|
| LAYAK | 848 / 552 / **+0,064** / 1,16 | 253 / 182 / **+0,116** / 1,29 |
| TUNGGU | 7.433 / 5.183 / +0,057 / 1,17 | 3.408 / 2.521 / −0,052 / 0,88 |
| HINDARI | 7.517 / 4.894 / +0,017 / 1,05 | 4.464 / 2.991 / −0,115 / 0,76 |

- Urutan LAYAK > TUNGGU > HINDARI terjaga di kedua periode, tetapi di periode awal LAYAK hampir sama dengan TUNGGU.
- **Biaya transaksi** (beli 0,15 % + jual 0,25 %, tidak dimodelkan di aplikasi atas permintaan pengguna) setara rata-rata
  **±0,10 R** pada rencana LAYAK (risiko ±4–6 %). Setelah biaya: periode awal ±−0,04 R, periode uji ±+0,02 R —
  **praktis impas**. Saringan LAYAK membantu menghindari rencana yang lebih buruk, tetapi belum terbukti menghasilkan
  untung bersih.
- Bobot pilar: varian terbaik periode awal ("aliran dana lebih berat") di periode uji −0,067 vs −0,079 R untuk 10 skor
  tertinggi per hari — sama-sama negatif dan selisihnya kecil → **bobot tidak diubah**. Catatan: 10 skor tertinggi
  **tanpa** saringan status merugi di periode uji; peringkat skor saja tidak cukup, status LAYAK yang menentukan.

## Kandidat perubahan level yang diuji dan TIDAK dipakai

Diuji dengan simulator yang sudah diperbaiki (jual separuh di TP1), status dinilai ulang dengan level masing-masing.

| Kandidat | LAYAK periode awal | LAYAK periode uji | Keputusan |
|---|---|---|---|
| Sekarang | 849 rencana, +0,064 R | 253, +0,116 R | dipakai |
| H1 cut loss di bawah zona support tempat entry berdiri (risiko median 7,1 % → 5,7 %) | 1.328, +0,017 R | 408, +0,027 R | tidak (lebih banyak LAYAK, tetapi lebih buruk) |
| M1 zona support/resistance tidak "berantai" (maks. 0,5 ATR dari dasar zona) | 1.562, +0,037 R | 447, −0,008 R | tidak |
| M2 TP1 harus di atas harga penutupan | 849, +0,069 R | 253, +0,106 R | tidak (selisih kecil, tidak konsisten) |
| H1 + M1 (+ M2) | 1.789, +0,026 R | 532, +0,000–0,004 R | tidak |

Sakelar tetap tersedia dan mati: `SAHAM_STOP_NEAR_ZONE`, `SAHAM_MERGE_FROM_BOTTOM`, `SAHAM_TP_ABOVE_CLOSE`,
`SAHAM_CLEAN_LEVELS`. Skrip uji: `variants.py` (di luar repo, scratchpad sesi 23 Okt 2026).

## Keputusan lain (dari putaran pertama, diukur dengan simulator lama)

| Aturan | Status |
|---|---|
| Syarat "tanpa ARB/limit-down/suspensi 3 hari terakhir" | dipakai (pengaman logis; hari terkunci juga tidak lagi dibaca sebagai sinyal VSA) |
| Peringkat: status → **layak dipasang order dari harga sekarang** → skor asli → skor → R:R → likuiditas. Tingkat: 0 = entry ≤ 0,5 ATR di bawah harga & TP1 masih di atas harga; 1 = entry 0,5–1 ATR di bawah harga **atau** TP1 sudah ≤ harga; 2 = harga > 1 ATR di atas zona; 3 = TP sudah tersentuh / cut loss tembus hari ini | dipakai |

Bukti jarak entry (23.923 rencana, order limit 5 hari): terisi **77–81 %** bila entry ≤ 0,25 ATR di bawah penutupan, 58–62 % pada 0,25–0,5 ATR, **38–42 %** pada 0,5–1 ATR, 23–27 % di atas 1 ATR — konsisten di kedua periode. Di periode uji rencana LAYAK yang entry-nya jauh juga merugi (0,25–0,5 ATR −0,12 R; 0,5–1 ATR −0,39 R; n kecil) sementara yang dekat +0,24 R. Rencana dengan TP1 ≤ penutupan: sampel kecil (19 / 7 LAYAK), diturunkan atas dasar logika (target sudah tercapai), bukan bukti. Tingkat ini hanya mengubah **urutan**, bukan status. |
| TP sudah tersentuh hari ini → TUNGGU | dipakai (aturan intraday) |
| ATR & pivot "bersih" (`CLEAN_LEVELS`) | tidak dipakai — perlu diuji ulang dengan simulator baru sebelum dipertimbangkan lagi |
| Breadth ≥ 30 % sebagai rem | tidak dipakai — sama, perlu diuji ulang |
| Kekuatan sektor ke skor | tidak bisa diuji (tidak ada riwayat) → hanya informasi |

## Keseluruhan rencana (semua status, simulator baru)

| | Semua | Periode awal | Periode uji |
|---|---|---|---|
| Rencana | 23.923 | 15.798 | 8.125 |
| Terisi | 68,2 % | 67,3 % | 70,1 % |
| TP1 dulu | 53,4 % | 55,2 % | 50,1 % |
| Rata-rata | −0,002 R | +0,039 R | −0,080 R |
| Profit factor | 0,99 | 1,11 | 0,83 |

Kesimpulan jujur: tanpa saringan, rencana teknis rata-rata impas sebelum biaya dan merugi di periode krisis
(Des 2025 – Okt 2026). Status LAYAK memisahkan rencana yang lebih baik, tetapi keunggulannya kecil dan habis oleh biaya
transaksi. Hasil masa lalu bukan jaminan; rekam jejak nyata (Histori Prediksi, hanya saham LAYAK) adalah ukuran yang
harus dipantau sebelum memakai uang sungguhan dalam jumlah berarti.
