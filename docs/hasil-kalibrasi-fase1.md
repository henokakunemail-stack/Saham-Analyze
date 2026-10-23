# Hasil Kalibrasi Fase 1 — Status LAYAK / TUNGGU / HINDARI & bobot pilar (23 Okt 2026)

> **Revisi 23 Okt 2026:** angka R di dokumen ini dihitung dengan simulator lama yang punya bug (setelah TP1 bisa naik
> ke TP2 tanpa cek cut loss), sehingga terlalu tinggi. Angka yang benar dan keputusan akhirnya ada di
> `docs/hasil-akhir-fase1-5.md` (LAYAK periode uji +0,116 R, bukan +0,341 R). Pilihan konfigurasi status tidak berubah.

Kalibrasi gerbang `engine/screener/actionability.py` dan bobot pilar `engine/screener/scoring.py`.
Pembanding: `docs/hasil-backtest-baseline.md`. Kode: `engine/screener/calibration.py`.

## Metode

- **Data:** 126 saham IDX (daftar default), candle dari cache lokal, IHSG (`^JKSE`) sebagai pembanding regime.
  Walk-forward `backtest.walk_forward` (horizon 10, evaluasi tiap 3 hari bursa), aturan simulasi rencana sama
  dengan baseline (`plan_sim`: order di harga beli 5 hari, cut loss dicek sebelum TP, tanpa biaya).
  Dihitung **sekali** (23.923 rencana, 29 Apr 2024 – 9 Okt 2026), disimpan, lalu semua varian dinilai offline
  dari baris yang sama — tidak ada indikator yang dihitung ulang.
- **Periode:** awal (in-sample) = sebelum 11 Des 2025; uji (out-of-sample) = sejak 11 Des 2025.
- **Pemilihan hanya di periode awal.** Aturan pilih (ditulis di kode sebelum melihat periode uji,
  `best_gate_variant`): di antara varian dengan rata-rata R **LAYAK > TUNGGU > HINDARI** dan ≥ 100 transaksi LAYAK
  terisi, ambil R LAYAK tertinggi; seri → varian yang tercantum lebih dulu (pasar default sebelum longgar,
  dengan gerbang volatilitas sebelum tanpa).
- **Periode uji dipakai sekali** untuk konfigurasi terpilih. Lulus bila di periode uji: LAYAK > TUNGGU > HINDARI,
  LAYAK ≥ +0,10 R, dan ≥ 100 transaksi LAYAK terisi.
- **Varian gerbang (72):** pasar {default: CRASH tahan, BEARISH hanya pemimpin · ketat: CRASH & BEARISH tahan ·
  longgar: CRASH & BEARISH boleh untuk pemimpin} × dasar sinyal {verdict akhir · raw = skor saham sebelum rem pasar,
  tetap dengan batas UPTREND_EXTENDED & tren turun kuat} × risiko ≤ {6, 8, 10} % × likuiditas ≥ {Rp2 M, Rp5 M}
  × {dengan, tanpa} gerbang volatilitas. "Pemimpin" = `pullback_state` PULLBACK_IDEAL / UPTREND_RUNNING.
  Gerbang `data_ok` tidak ikut diuji (riwayat hari ARB/suspensi belum ada di backtest).
- **Varian bobot (6):** skor dihitung ulang dari `pillar_values` tersimpan untuk pilar yang punya riwayat
  (pullback, tren, aliran dana, momentum, setup). Fundamental & sentimen tidak ada di backtest → bobotnya tidak
  disetel. Ukuran: rata-rata R 10 rencana berskor tertinggi tiap tanggal, dan R per kuintil skor.
- Ukuran per kelompok: rencana, % terisi, % kena TP dulu (dari yang terisi), rata-rata R, profit factor.
- \* *LAYAK/hari* = perkiraan jumlah saham LAYAK per hari bursa di 126 saham (jumlah LAYAK × 3 / hari bursa).

## Keseluruhan (sama dengan baseline)

| Ukuran | Semua | Periode awal | Periode uji |
|---|---|---|---|
| Rencana | 23.923 | 15.798 | 8.125 |
| Terisi | 68,3 % | 67,3 % | 70,1 % |
| Kena TP dulu | 53,7 % | 55,5 % | 50,4 % |
| Rata-rata R | +0,157 | +0,205 | +0,068 |
| Profit factor | 1,41 | 1,60 | 1,15 |

Kondisi pasar per periode (jumlah rencana): awal NORMAL 10.287 · BEARISH 3.504 · CAUTIOUS 2.007 · **CRASH 0**;
uji NORMAL 3.600 · CRASH 2.408 · BEARISH 1.149 · CAUTIOUS 968.

## Gerbang — hasil

Dari 72 varian, hanya 16 yang urut (LAYAK > TUNGGU > HINDARI) dengan ≥ 100 transaksi LAYAK di periode awal —
**semuanya memakai batas risiko 6 %**. Dengan batas 8 % atau 10 %, LAYAK justru di bawah TUNGGU.
Tabel memuat konfigurasi awal, semua varian yang beda satu pengaturan darinya, dan varian terpilih.

#### Periode awal (in-sample)

| Varian (pasar · sinyal · risiko · likuiditas · vol) | LAYAK rencana | LAYAK terisi | Terisi % | TP dulu % | R LAYAK | PF LAYAK | R TUNGGU | R HINDARI | Urut? | LAYAK/hari* |
|---|---|---|---|---|---|---|---|---|---|---|
| default · verdict · ≤8% · ≥Rp5M · vol (awal) | 1.313 | 865 | 65,9 | 50,8 | +0,187 | 1,48 | +0,238 | +0,175 | tidak | 9,3 |
| default · raw · ≤8% · ≥Rp5M · vol | 1.372 | 904 | 65,9 | 50,4 | +0,180 | 1,46 | +0,240 | +0,175 | tidak | 9,7 |
| default · verdict · ≤10% · ≥Rp5M · vol | 2.627 | 1.776 | 67,6 | 51,2 | +0,183 | 1,52 | +0,252 | +0,175 | tidak | 18,6 |
| default · verdict · ≤6% · ≥Rp2M · vol **(dipilih)** | 850 | 552 | 64,9 | 50,0 | +0,239 | 1,61 | +0,230 | +0,175 | ya | 6,0 |
| default · verdict · ≤6% · ≥Rp5M · vol | 773 | 509 | 65,8 | 48,9 | +0,236 | 1,59 | +0,230 | +0,175 | ya | 5,5 |
| default · verdict · ≤8% · ≥Rp2M · vol | 1.419 | 923 | 65,0 | 51,5 | +0,194 | 1,51 | +0,237 | +0,175 | tidak | 10,1 |
| default · verdict · ≤8% · ≥Rp5M · tanpa vol | 1.319 | 871 | 66,0 | 50,6 | +0,200 | 1,51 | +0,236 | +0,175 | tidak | 9,3 |
| ketat · verdict · ≤8% · ≥Rp5M · vol | 1.246 | 819 | 65,7 | 50,4 | +0,185 | 1,47 | +0,238 | +0,175 | tidak | 8,8 |
| longgar · raw · ≤6% · ≥Rp2M · vol | 892 | 578 | 64,8 | 50,0 | +0,236 | 1,61 | +0,230 | +0,175 | ya | 6,3 |
| longgar · verdict · ≤8% · ≥Rp5M · vol | 1.313 | 865 | 65,9 | 50,8 | +0,187 | 1,48 | +0,238 | +0,175 | tidak | 9,3 |

#### Periode uji (out-of-sample)

Hanya baris "dipilih" yang menentukan keputusan; baris lain ditampilkan sebagai informasi dan **tidak** dipakai
untuk memilih ulang.

| Varian (pasar · sinyal · risiko · likuiditas · vol) | LAYAK rencana | LAYAK terisi | Terisi % | TP dulu % | R LAYAK | PF LAYAK | R TUNGGU | R HINDARI | Urut? | LAYAK/hari* |
|---|---|---|---|---|---|---|---|---|---|---|
| default · verdict · ≤8% · ≥Rp5M · vol (awal) | 405 | 289 | 71,4 | 51,9 | +0,155 | 1,34 | +0,089 | +0,042 | ya | 5,6 |
| default · raw · ≤8% · ≥Rp5M · vol | 459 | 332 | 72,3 | 50,3 | +0,123 | 1,25 | +0,093 | +0,042 | ya | 6,3 |
| default · verdict · ≤10% · ≥Rp5M · vol | 828 | 593 | 71,6 | 52,1 | +0,114 | 1,26 | +0,092 | +0,042 | ya | 11,4 |
| default · verdict · ≤6% · ≥Rp2M · vol **(dipilih)** | 248 | 176 | 71,0 | 53,4 | +0,341 | 1,89 | +0,079 | +0,042 | ya | 3,4 |
| default · verdict · ≤6% · ≥Rp5M · vol | 228 | 169 | 74,1 | 52,7 | +0,325 | 1,83 | +0,081 | +0,042 | ya | 3,1 |
| default · verdict · ≤8% · ≥Rp2M · vol | 430 | 296 | 68,8 | 52,4 | +0,168 | 1,37 | +0,088 | +0,042 | ya | 5,9 |
| default · verdict · ≤8% · ≥Rp5M · tanpa vol | 411 | 294 | 71,5 | 51,4 | +0,310 | 1,67 | +0,070 | +0,042 | ya | 5,7 |
| ketat · verdict · ≤8% · ≥Rp5M · vol | 361 | 249 | 69,0 | 51,8 | +0,204 | 1,45 | +0,086 | +0,042 | ya | 5,0 |
| longgar · raw · ≤6% · ≥Rp2M · vol | 321 | 230 | 71,7 | 53,0 | +0,291 | 1,75 | +0,078 | +0,042 | ya | 4,4 |
| longgar · verdict · ≤8% · ≥Rp5M · vol | 405 | 289 | 71,4 | 51,9 | +0,155 | 1,34 | +0,089 | +0,042 | ya | 5,6 |

#### Konfigurasi terpilih — periode awal

| Status | Rencana | Terisi | Terisi % | TP dulu % | Rata-rata R | Profit factor |
|---|---|---|---|---|---|---|
| LAYAK | 850 | 552 | 64,9 | 50,0 | +0,239 | 1,61 |
| TUNGGU | 7.433 | 5.189 | 69,8 | 55,5 | +0,230 | 1,71 |
| HINDARI | 7.515 | 4.898 | 65,2 | 56,1 | +0,175 | 1,49 |

#### Konfigurasi terpilih — periode uji (sekali)

| Status | Rencana | Terisi | Terisi % | TP dulu % | Rata-rata R | Profit factor |
|---|---|---|---|---|---|---|
| LAYAK | 248 | 176 | 71,0 | 53,4 | **+0,341** | 1,89 |
| TUNGGU | 3.407 | 2.528 | 74,2 | 52,8 | +0,079 | 1,18 |
| HINDARI | 4.470 | 2.994 | 67,0 | 48,2 | +0,042 | 1,09 |

## Bobot pilar — hasil

| Varian | pullback | tren | aliran dana | momentum | setup | Top-10 terisi | TP dulu % | R top-10 | PF | R per kuintil skor (rendah→tinggi) | Monoton |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sekarang (awal) | 35% | 20% | 10% | 10% | 5% | 1.819 | 51,7 | +0,310 | 1,82 | +0,196 / +0,163 / +0,175 / +0,256 / +0,234 | 0,50 |
| pullback-dominan (awal) | 50% | 20% | 10% | 10% | 10% | 1.812 | 52,2 | +0,305 | 1,82 | +0,196 / +0,158 / +0,192 / +0,249 / +0,230 | 0,50 |
| tren-lebih-berat (awal) | 30% | 35% | 10% | 15% | 10% | 1.828 | 50,4 | +0,325 | 1,85 | +0,205 / +0,142 / +0,182 / +0,217 / +0,278 | 0,75 |
| aliran-dana-lebih-berat (awal) | 30% | 20% | 25% | 15% | 10% | 1.846 | 50,4 | +0,280 | 1,74 | +0,164 / +0,186 / +0,194 / +0,236 / +0,243 | 1,00 |
| momentum-setup-lebih-berat (awal) | 30% | 15% | 10% | 25% | 20% | 1.833 | 52,6 | +0,315 | 1,87 | +0,177 / +0,192 / +0,200 / +0,217 / +0,238 | 1,00 |
| rata (awal) | 20% | 20% | 20% | 20% | 20% | 1.839 | 50,0 | +0,305 | 1,81 | +0,162 / +0,193 / +0,194 / +0,222 / +0,253 | 1,00 |
| sekarang (uji) | 35% | 20% | 10% | 10% | 5% | 1.353 | 45,8 | +0,083 | 1,15 | -0,043 / +0,086 / +0,094 / +0,141 / +0,060 | 0,75 |
| tren-lebih-berat (uji) | 30% | 35% | 10% | 15% | 10% | 1.347 | 44,9 | +0,080 | 1,14 | -0,064 / +0,093 / +0,093 / +0,131 / +0,085 | 0,50 |

(Bobot ditulis sebagai porsi relatif di antara 5 pilar backtest; skor varian tanpa bonus konfluensi & rem pasar.)

## Keputusan

**Gerbang: LULUS → dipasang** di `actionability.py`:

| Konstanta | Sebelum | Sesudah | Dasar |
|---|---|---|---|
| `MAX_RISK_PCT` | 8,0 | **6,0** | satu-satunya batas yang membuat status urut di periode awal |
| `MIN_VALUE_IDX` | 5e9 | **2e9** | pemenang periode awal (selisih vs Rp5 M hanya 0,003 R) |
| `MARKET_BLOCKED_MODES` / `MARKET_LEADERS_ONLY_MODES` | CRASH / BEARISH | tetap | lihat catatan CRASH |
| `SIGNAL_BASIS` | verdict | tetap | raw sedikit lebih rendah di periode awal (+0,236 vs +0,239) |
| `REQUIRE_NOT_VOLATILE` | True | tetap | seri (pada batas 6 % rencana `too_volatile` sudah gagal di risiko); dipertahankan sebagai pengaman |
| `MIN_VALUE_US` | 20e6 | tetap | tidak dikalibrasi (tidak ada uji US) |

Periode uji (sekali): LAYAK **+0,341 R** (176 transaksi terisi, PF 1,89) > TUNGGU +0,079 > HINDARI +0,042
→ ketiga syarat terpenuhi (urut, ≥ +0,10 R, ≥ 100 transaksi).

**Bobot pilar: TIDAK diubah.** Varian terbaik periode awal ("tren-lebih-berat", +0,325 vs +0,310 R top-10)
tidak lebih baik di periode uji (+0,080 vs +0,083 R), jadi `PILLAR_WEIGHTS` tetap. Fundamental (12 %) dan
sentimen (8 %) tidak bisa dikalibrasi (tanpa riwayat).

## Catatan & keterbatasan (wajib dibaca sebelum memakai status untuk prediksi)

1. **Pemisahan di periode awal tipis.** LAYAK hanya +0,009 R di atas TUNGGU di periode awal (+0,239 vs +0,230);
   pemisahan besar baru terlihat di periode uji. Status lulus kriteria yang disepakati, tetapi rekam jejak per
   status perlu dipantau (Fase 5 / pelacak prediksi) sebelum dianggap kuat.
2. **CRASH tidak bisa diuji di periode awal** (0 hari CRASH). Aturan "CRASH = tahan" dipertahankan sebagai
   pilihan konservatif. Sebagai informasi, varian longgar + sinyal raw di periode uji: +0,291 R (230 terisi) —
   tidak lebih baik dari konfigurasi terpilih.
3. **BEARISH:** LAYAK saat BEARISH hanya 32 rencana di periode awal (+0,446 R) dan 21 di periode uji (+0,032 R)
   — sampel terlalu kecil untuk disimpulkan.
4. **HINDARI masih positif** (+0,175 / +0,042 R): rencana beli di support tetap rata-rata untung tipis walau vonis
   bearish; HINDARI berarti "paling lemah", bukan "pasti rugi".
5. **Frekuensi:** perkiraan ±3–6 saham LAYAK per hari bursa (126 saham) — di atas target awal 2–10 per minggu;
   batas risiko 6 % menggagalkan 66 % rencana di gerbang risiko (median risiko 7,8 %).
6. **Survivorship:** daftar saham = yang masih likuid Okt 2026, sehingga ambang likuiditas Rp2 M vs Rp5 M sulit
   dibedakan oleh data ini; keduanya lulus di periode uji (+0,341 vs +0,325 R).
7. Tanpa biaya transaksi; `data_ok` (ARB/suspensi) belum ikut diuji — dinilai ulang di Fase 5 setelah Fase 2.

Ulang hitung: `python -m engine.screener.calibration compute <rows.pkl>` (±4 menit, 6 proses) lalu
`python -m engine.screener.calibration report <rows.pkl> <hasil.json>`.
