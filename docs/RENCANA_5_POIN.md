# Rencana Peningkatan Akurasi Membaca Pergerakan Saham — 5 Poin

Status: **DISETUJUI 23 Okt 2026** — biaya transaksi DIBATALKAN atas permintaan pengguna (semua hasil = harga kotor)  ·  Dibuat: 23 Okt 2026  ·  Basis data: scan IDX 126 saham (23 Okt 2026, 07:58)

> **Status akhir (23 Okt 2026): Fase 0–5 selesai** — hasil di `docs/hasil-akhir-fase1-5.md`. Catatan yang
> menggantikan isi rencana di bawah:
> - **Ambang final LAYAK: risiko ≤ 6 % dan likuiditas ≥ Rp2 miliar/hari** (hasil kalibrasi, lihat
>   `docs/hasil-kalibrasi-fase1.md`) — menggantikan 8 % / Rp5 miliar di §3.2.
> - Biaya transaksi dibatalkan; `/api/screener/summary` tidak dibuat (UI menghitung jumlah status sendiri).
> - Pengambilan ulang data setelah split (aksi korporasi) saat ini berjalan ketika detail saham dibuka; akan
>   dipindah ke lapisan data.
> - Butir checklist yang masih `[ ]` di bawah memang belum/tidak dikerjakan (alasannya ditulis di butir itu).

Dokumen ini adalah rencana kerja lengkap untuk 5 peningkatan. Setiap poin punya: tujuan, masalah yang
terukur, desain aturan, perubahan engine / database / route / UI, posisinya di pipeline & lifecycle,
cara pengujian, kriteria lulus, risiko, dan checklist "selesai". Tidak ada aturan baru yang dipakai
untuk menilai saham sebelum lulus backtest (prinsip yang sama sejak skor v4).

---

## 0. Ringkasan

| # | Poin | Hasil yang dirasakan pengguna | Ukuran |
|---|------|-------------------------------|--------|
| 1 | Status **LAYAK / TUNGGU / HINDARI** + pemecah seri + aturan volatilitas | Top 10 menjawab "ada yang layak dibeli besok?", bukan sekadar peringkat | L |
| 2 | Garis level di grafik + peringatan **masuk zona beli** | Rencana terlihat langsung di grafik; diberi tahu saat harga turun ke zona | M |
| 3 | Deteksi hari tidak normal (ARA/ARB, suspensi, aksi korporasi) | ATR, support, dan sinyal tidak lagi dikacaukan hari terkunci / split | M |
| 4 | **Breadth** pasar + **kekuatan sektor** | Kondisi pasar dibaca dari 126 saham, bukan IHSG saja; peringatan konsentrasi sektor | L |
| 5 | Pembuktian: **"sempat masuk zona"**, backtest ulang 126 saham (tanpa biaya transaksi — dibatalkan) | Angka akurasi yang jujur, dan dasar untuk menyetel aturan poin 1–4 | L |

**Urutan pengerjaan berbeda dari urutan nomor** (lihat §7 Roadmap): bagian alat ukur dari poin 5
dikerjakan **lebih dulu** (Fase 0), karena aturan poin 1 dan 3 harus diuji dengan alat ukur itu.

### Masalah terukur saat ini (scan 23 Okt 2026)

| Fakta | Angka |
|---|---|
| Skor Top 10 | 7 saham = 55, 6 saham = 54 (mode CRASH memangkas skor ke ≤ 55) |
| Vonis | 0 bullish · 51 netral · 75 bearish |
| Risiko : untung | median 1 : 0,79 · 73/126 di bawah 1 : 1 |
| Flag `tight_room` / `wide_stop` | 86 / 97 dari 126 |
| ATR harian | median 5,8 % · 58 saham > 6 % |
| Sektor | tidak tersimpan sama sekali |
| Biaya transaksi di backtest & rekam jejak | tidak ada |
| Rekam jejak prediksi | dinilai dari harga saat sinyal, tanpa cek "sempat masuk zona beli" |

---

## 1. Arsitektur & pipeline saat ini (titik sambung tiap poin)

```
Auto-scan / tombol Scan (engine/main.py::_run_scan)
 ├─ fetch_rss_news, get_benchmark_context (IHSG/S&P + market_mode)
 ├─ prefetch_daily (batch 50 saham/permintaan)            ← [P3] deteksi hari tidak normal setelah clean
 ├─ _analyze_single_ticker (per saham, 6 thread)
 │    ├─ fetch_stock_ohlcv → clean_ohlcv (data_quality)   ← [P3] classify_bars
 │    ├─ compute_technical_indicators → compute_trade_levels (rencana dikunci saat sesi)
 │    │                                                    ← [P1] aturan volatilitas, [P2] ladder S/R, [P3] ATR bersih
 │    ├─ compute_money_flow, compute_trend_direction, pullback
 │    ├─ fetch_and_evaluate_financials (cache 7 hari)      ← [P4] sektor & industri
 │    ├─ compute_composite_score → verdict, build_reading
 │    └─ compute_screen_metrics                            ← [P1] assess_actionability
 ├─ urutkan (skor)                                          ← [P1] rank_key (pemecah seri)
 ├─ pass ke-2: berita per saham top 20
 ├─ save_prediction_snapshot(select_predictions)            ← [P1] hanya LAYAK, [P5] dievaluasi dgn fill
 ├─ notifications.on_scan_complete                          ← [P2] alert entry_zone
 └─ (baru) compute_breadth + sector_strength               ← [P4]
API → UI: Screener · Top 10 (+ PlanCheckpoint) · Detail saham · Watchlist · Histori Prediksi · Notifikasi
```

Penyimpanan: `screener_cache` (kolom + JSON `direction_data`, kunci di `DIRECTION_KEYS`),
`candles`, `fundamentals_cache`, `alert_state`, `alerts`, `prediction_snapshots`, `ai_validations`,
`data_quality_reports`, `app_settings`.

### Lifecycle harian (setelah semua poin selesai)

| Waktu (WIB) | Yang terjadi |
|---|---|
| 08:45–09:00 | Pra-pembukaan: rencana = penutupan final kemarin (status LAYAK/TUNGGU/HINDARI sudah ada sejak semalam) |
| 09:00–16:00 | Scan tiap 5 menit: rencana dikunci; posisi harga live; **alert masuk zona beli** [P2]; flag ARA/ARB hari ini [P3]; breadth intraday [P4] |
| 12:00–13:30 (Jumat 11:30–14:00) | Cek Tengah Hari (sudah ada) + status LAYAK per saham |
| 16:50–17:50 | Scan penutupan: rencana baru, status baru [P1], breadth & sektor harian disimpan [P4], snapshot prediksi (LAYAK saja) [P1/P5] |
| Malam | Data stabil; scan manual memberi hasil sama |
| Mingguan (Sabtu) | Refresh fundamental+sektor+aksi korporasi [P3/P4]; backtest/simulasi ulang di latar belakang [P5] |

---

## 2. FASE 0 — Alat ukur (bagian dari Poin 5, dikerjakan pertama)

> **Perubahan 23 Okt 2026:** model biaya transaksi (costs.py, pengaturan biaya, R bersih) **tidak dikerjakan** atas
> permintaan pengguna. Semua R dan return adalah harga kotor. Halaman Histori Prediksi sekaligus disederhanakan
> menjadi 3 tab (Prediksi · Uji Historis · Validasi AI).

### 2.1 Tujuan
Mesin simulasi rencana yang realistis — biaya, pengisian order, cut loss/TP — dipakai untuk menguji
setiap aturan baru di poin 1–4 dan untuk rekam jejak di aplikasi.

### 2.2 Desain

**Model biaya** (`engine/screener/costs.py`)
- IDX default: beli 0,15 %, jual 0,25 % (termasuk PPh final 0,1 %), slippage 1 fraksi harga per sisi.
- US default: komisi 0 %, slippage 0,05 % per sisi.
- Bisa diubah di Pengaturan (fee broker berbeda-beda). Disimpan di `app_settings` key `trading_costs`.
- Fungsi: `net_return(entry, exit, market, costs) -> float` dan `cost_in_r(entry, stop, market) -> float`.

**Simulasi rencana** (`engine/screener/plan_sim.py`) — satu fungsi dipakai backtest, rekam jejak prediksi,
dan rekam jejak AI:
```
simulate_plan(plan, future_bars, market, costs, fill_days=5, horizon=10) -> {
  filled: bool, fill_date, fill_price,            # limit di recommended_entry; open < limit → isi di open
  status: NOT_FILLED | STOPPED_OUT | HIT_TP1 | HIT_TP2 | EXPIRED | IN_PROGRESS,
  exit_price, exit_date, r_gross, r_net, return_net_pct, bars_held
}
```
Aturan: order beli berlaku `fill_days` hari bursa; batal bila harga menyentuh cut loss sebelum terisi;
setelah terisi, bar yang menyentuh cut loss dan TP sekaligus dihitung cut loss (konservatif, sama
dengan sekarang); gap di bawah cut loss keluar di harga open.

**Backtest 126 saham** (`engine/screener/backtest.py` + `engine/routes/signals.py::compute_backtest`)
- Data 3 tahun via **batch** (`prefetch_daily(tickers, "3y")`) — saat ini 3y diambil satu per satu.
- `walk_forward` menambah kolom rencana per tanggal (levels lengkap) lalu `simulate_plan`.
- Ringkasan baru: fill rate, win rate, rata-rata R bersih, expectancy, profit factor, drawdown
  portofolio risiko-sama, dikelompokkan per: status [P1], market_mode, sektor [P4], kelompok ATR %, flag.
- Pembagian **in-sample / out-of-sample** dikunci di depan: 2 tahun pertama in-sample, 1 tahun terakhir
  out-of-sample. Ambang aturan hanya boleh dipilih dari in-sample.
- Peringatan survivorship: daftar 126 = saham yang *masih* likuid hari ini; ditampilkan di laporan.

### 2.3 Route
| Method | Path | Perubahan |
|---|---|---|
| GET | `/api/backtest?market&horizon&refresh` | + `plan_sim` (ringkasan setelah biaya), + `by_status`, `by_sector`, `by_atr_bucket` |
| GET | `/api/backtest/reliability` | + `fill_rate`, `avg_r_net` per rentang skor |
| GET | `/api/predictions/history` | evaluasi memakai `simulate_plan` (+ `filled`, `r_net`) |
| GET/PUT | `/api/settings/trading-costs` | baru — baca/ubah model biaya |

### 2.4 Database
- `prediction_snapshots`: kolom baru `entry_low REAL, entry_high REAL, recommended_entry REAL` (migrasi
  pola `PRAGMA table_info` + `ALTER TABLE` yang sudah ada). Snapshot lama tanpa kolom ini dievaluasi
  dengan aturan lama dan diberi label "tanpa cek zona".
- `app_settings.trading_costs` (JSON).

### 2.5 UI
- **Histori Prediksi → BacktestPanel**: kartu baru "Simulasi Rencana (setelah biaya)": fill rate, win
  rate, R bersih, expectancy; tab per status / mode / sektor; catatan survivorship.
- **Histori Prediksi → daftar prediksi**: kolom "Terisi?" (✓ / "tidak sempat masuk zona"), hasil R bersih.
- **Rekam Jejak Validasi AI**: memakai `simulate_plan` untuk kolom "TP1 dulu".
- **Pengaturan → Biaya transaksi**: 4 isian (fee beli, fee jual, slippage, berlaku untuk IDX/US).

### 2.6 Pengujian & kriteria lulus
- Unit: biaya (angka contoh manual), `simulate_plan` (tidak terisi, gap-down terisi di open, SL dulu,
  TP1→TP2, expired, in-progress), migrasi kolom.
- Integrasi: `/api/backtest` dengan data sintetis.
- **Lulus Fase 0** bila: hasil lama (+0,02 R kotor) direproduksi ±0,01 R dengan biaya = 0, dan angka
  setelah biaya dilaporkan apa adanya (boleh negatif).

### 2.7 Selesai bila
- [ ] costs.py + pengaturan biaya — **dibatalkan** (tanpa biaya transaksi)
- [x] plan_sim.py dipakai backtest dan prediksi
- [ ] plan_sim.py untuk rekam jejak AI — belum; Validasi AI masih memakai pengukuran TP1/cut loss sendiri
- [x] backtest 126 saham 3 tahun via batch, laporan in/out-of-sample
- [x] migrasi `prediction_snapshots`
- [x] UI BacktestPanel, Histori Prediksi (3 tab); Pengaturan biaya tidak ada (dibatalkan)
- [x] laporan baseline tersimpan (`docs/hasil-backtest-baseline.md`) sebagai pembanding fase berikut

---

## 3. POIN 1 — Status LAYAK / TUNGGU / HINDARI, pemecah seri, aturan volatilitas

> **Revisi 23 Okt 2026 setelah Fase 0** (lihat `docs/hasil-backtest-baseline.md`):
> - Gerbang `rr_ok` (R:R ≥ 1) **tidak dipasang begitu saja** — data menunjukkan rata-rata R sama di semua kelompok
>   R:R; diganti gerbang risiko (`risk_pct` ≤ 8 %) dan R:R hanya informasi, kecuali uji in-sample membuktikan lain.
> - Gerbang `market_ok` diuji dua varian (CRASH = tahan vs CRASH boleh untuk pemimpin), karena CRASH +0,22 R dan
>   BEARISH +0,04 R.
> - **Skor asli sebelum rem pasar** (`raw_score`) disimpan dan dipakai sebagai pemecah seri.
> - **Penyetelan bobot pilar** masuk Fase 1: hanya pilar yang punya riwayat (pullback, tren, aliran dana,
>   momentum, setup) yang bisa disetel; fundamental & sentimen tidak punya riwayat → bobot tetap, diberi catatan.
> - Kalibrasi: ambang dipilih di periode awal (s/d 11 Des 2025), diuji **sekali** di periode uji. Lulus bila
>   R rata-rata LAYAK > TUNGGU > HINDARI dan LAYAK ≥ +0,10 R di periode uji.
> - Pesan Telegram (rencana harian, /top10) memakai status LAYAK/TUNGGU/HINDARI setelah fase ini.

### 3.1 Tujuan
Setiap saham punya status tindakan yang jelas dan alasannya. Top 10 berani mengatakan
"0 saham layak hari ini".

### 3.2 Aturan (ambang awal — disetel di Fase 0 in-sample)

> **Ambang final:** `vol_ok` risiko ≤ **6 %**, `liquid_ok` ≥ **Rp2 miliar/hari** (lihat `docs/hasil-kalibrasi-fase1.md`).
> Angka 8 % / Rp5 miliar di tabel ini adalah ambang awal sebelum kalibrasi.

`engine/screener/actionability.py::assess(row) -> {status, reasons[], gates{}}`

**LAYAK** — semua gerbang lolos:
| Gerbang | Aturan awal | Alasan bila gagal |
|---|---|---|
| `market_ok` | mode ≠ CRASH; mode BEARISH hanya untuk "pemimpin" (RS 60h ≥ +5 %) | "Pasar krisis — tahan pembelian" |
| `signal_ok` | verdict MILD/STRONG_BULLISH, tidak spekulatif | "Belum ada sinyal beli (vonis NETRAL)" |
| `rr_ok` | R:R ke TP1 setelah biaya ≥ 1,0 | "Ruang naik sempit: R:R 0,44" |
| `vol_ok` | jarak cut loss ≥ 1,0 × ATR **dan** ≤ 8 % | "Terlalu volatil: gerak harian 11 % > jarak cut loss 8,4 %" |
| `liquid_ok` | nilai transaksi 20h ≥ Rp5 miliar (US ≥ US$20 jt) | "Kurang likuid" |
| `data_ok` | tidak ada hari terkunci ARA/ARB/suspensi dalam 3 hari terakhir [P3], data tidak basi | "Ada ARB 19 Okt — tunggu stabil" |

**HINDARI** — salah satu: vonis MILD/STRONG_BEARISH; harga live di bawah cut loss; terkunci ARB
dalam 3 hari; tren rusak (struktur LL/LH + di bawah EMA200).
**TUNGGU** — selain itu (daftar gerbang yang gagal menjadi alasannya).

**Aturan volatilitas di `trade_levels.py`**: hitung `stop_atr = (recommended − stop) / ATR`. Bila batas
8 % memaksa `stop_atr < 1,0` → flag baru `too_volatile` (menggantikan sebagian makna `wide_stop`).
Varian yang diuji di Fase 0: ambang 1,0 / 1,25 / 1,5 ATR.

**Pemecah seri** `rank_key(row)` (dipakai backend untuk urutan, disimpan sebagai `rank`):
1. status (LAYAK > TUNGGU > HINDARI) → 2. skor → 3. R:R bersih → 4. likuiditas → 5. jarak ke zona beli (dekat dulu).

### 3.3 Engine & data
- `actionability.py` (baru), dipanggil di `_analyze_single_ticker` setelah `compute_screen_metrics`.
- Hasil disimpan di JSON `direction_data` — tambah `"action"` ke `DIRECTION_KEYS` (tanpa migrasi kolom).
- `_run_scan`: urut dengan `rank_key`; `rank` ditulis ke setiap baris.
- `select_predictions`: hanya status LAYAK (dengan batas 10). Hari tanpa LAYAK = tanpa prediksi.
- `build_reading` (`reading.stance`): selaras dengan status (sekarang 125 dari 126 saham "TAHAN").
- Prompt AI (`validate_signal_with_ai`): sertakan status + gerbang yang gagal.
- `plan_checkpoint` (Cek Tengah Hari): sertakan status.

### 3.4 Route
| Path | Perubahan |
|---|---|
| `/api/screener` | baris + `action{status,reasons,gates}`, `rank`; urutan default = `rank` |
| `/api/stock/{t}/analysis` | `composite.action` |
| `/api/screener/summary` (baru) | `{layak, tunggu, hindari, market_mode, as_of}` untuk header Top 10 |

### 3.5 UI
- **Komponen baru** `ActionStatusBadge.tsx` (hijau LAYAK / abu TUNGGU / merah HINDARI, ikon + teks, bukan warna saja).
- **Top 10** (`Top10Potential.tsx`):
  - Pakai urutan `rank` dari backend (hapus pengurutan skor di klien).
  - Pita ringkasan: "0 LAYAK · 7 TUNGGU · 3 HINDARI".
  - Kondisi kosong: "Tidak ada setup layak hari ini — ini 10 saham terbaik yang masih perlu ditunggu."
  - Filter pill: Semua / Layak / Tunggu.
- **Detail saham**: daftar gerbang ✓/✗ dengan alasan (gaya sama dengan "Gerbang Konfluensi").
- **Screener**: kolom "Status" memakai `action.status`; preset filter "✅ Layak dieksekusi"; kolom ATR %.
- **PlanCheckpoint** dan **Watchlist**: badge status.
- Glosarium (`lib/glossary.ts`): entri "LAYAK/TUNGGU/HINDARI", "Terlalu volatil", "Pemecah seri".

### 3.6 Pengujian & kriteria lulus
- Unit: setiap gerbang (lolos/gagal), prioritas HINDARI > TUNGGU, `rank_key`, flag `too_volatile`.
- Backtest (Fase 0, in-sample → out-of-sample):
  - **Lulus** bila rata-rata R bersih: LAYAK > TUNGGU > HINDARI (monoton) di out-of-sample, dengan
    ≥ 100 transaksi LAYAK terisi; dan LAYAK punya R bersih ≥ 0.
  - Bila tidak lulus: status tetap ditampilkan sebagai *kondisi* (bukan klaim keunggulan), label di UI
    "belum terbukti", dan prediksi tetap memakai aturan lama. Tidak ada penyetelan ulang berkali-kali
    di out-of-sample.
- Browser: Top 10 dengan 0 LAYAK (kondisi krisis sekarang) dan dengan data sintetis berisi LAYAK.

### 3.7 Risiko
- Terlalu ketat → hampir selalu 0 LAYAK. Mitigasi: laporan backtest menunjukkan frekuensi LAYAK per bulan; target 2–10 per minggu di pasar normal.
- Pengguna mengira LAYAK = pasti naik. Mitigasi: teks "syarat teknis terpenuhi, bukan jaminan" + rekam jejak per status.

### 3.8 Selesai bila
- [x] actionability.py + flag too_volatile + rank_key, tersimpan di DIRECTION_KEYS
- [x] select_predictions, reading.stance, prompt AI, checkpoint memakai status
- [x] route + tipe TS (`ActionInfo`) — kecuali `/api/screener/summary` (tidak dibuat; UI menghitung status sendiri)
- [x] UI: badge, Top 10 (ringkasan, kosong, filter), detail (gerbang), screener (kolom, preset)
- [x] backtest lulus (LAYAK > TUNGGU > HINDARI di periode uji)

---

## 4. POIN 2 — Garis level di grafik + peringatan masuk zona beli

### 4.1 Tujuan
Rencana (zona beli, cut loss, TP) dan tangga support/resistance terlihat di grafik; pengguna diberi
tahu saat harga turun masuk zona beli.

### 4.2 Engine
- `compute_trade_levels` mengembalikan juga `ladder`: 3 support & 3 resistance terdekat
  `{price, label, kind}` (data sudah dihitung di `build_ladder`, hanya belum dikirim).
- Endpoint chart sudah ada; `levels` diambil dari `analysis.composite.levels` (tanpa request tambahan).

### 4.3 Alert `entry_zone`
- `notifications.py`: jenis baru `entry_zone` = "Harga masuk zona beli".
- Deteksi (per scan, saat sesi berjalan): untuk watchlist **dan** saham berstatus LAYAK/TUNGGU di Top 10:
  harga sebelumnya > `entry_high` dan sekarang di `[entry_low, entry_high]` dan > cut loss.
- Isi pesan: "PTBA masuk zona beli 2.930–3.020 (harga 2.990). Cut loss 2.790, TP1 3.150. Status: LAYAK."
- Cooldown 12 jam (mekanisme ada). Preferensi on/off di NotificationCenter (otomatis via `KINDS`).
- `alert_state`: kolom baru `entry_low REAL, entry_high REAL` (migrasi).
- Tidak memicu saat rencana belum dikunci (bar belum final) — memakai rencana beku.

### 4.4 UI
- `ChartView.tsx` props baru `levels?: TradeLevels`, `showPlan`, `showLadder`:
  - `candleSeries.createPriceLine` untuk: zona beli (2 garis hijau putus-putus + label "Zona beli"),
    cut loss (merah), TP1/TP2 (hijau tua), support/resistance (abu tipis, label sumber "EMA50", "Swing").
  - Garis dibuat ulang saat `levels` berubah; dihapus saat toggle mati.
  - Penanda (`setMarkers`) untuk hari ARA/ARB/suspensi [P3].
- `StockDetailModal.tsx`: dua toggle di header grafik: "Rencana" dan "Support/Resistance".
- Interval intraday (1H/15M/5M): garis sama (level harian), dengan catatan kecil "level dari grafik harian".
- `NotificationCenter.tsx`: ikon & warna untuk `entry_zone`.

### 4.5 Pengujian & kriteria lulus
- Unit: deteksi entry_zone (masuk dari atas, gap langsung ke bawah cut loss tidak memicu, cooldown).
- Browser: garis tampil di detail saham (IDX & US), toggle bekerja, tidak ada error konsol; alert
  muncul setelah dua scan buatan.
- Tidak butuh backtest (tampilan & pemberitahuan, bukan aturan penilaian).

### 4.6 Selesai bila
- [x] ladder di levels + tipe TS
- [x] ChartView garis + toggle + marker
- [x] alert entry_zone + migrasi alert_state + preferensi
- [x] verifikasi browser

---

## 5. POIN 3 — Hari tidak normal: ARA/ARB, suspensi, aksi korporasi

### 5.1 Tujuan
Hari yang tidak mencerminkan transaksi normal tidak lagi merusak ATR, support/resistance, dan sinyal.

### 5.2 Deteksi (`engine/collectors/abnormal_days.py::classify_bars(df, market)`)
| Jenis | Ciri (berbasis pola, bukan hanya persentase) |
|---|---|
| `LOCK_DOWN` | open = high = low = close dan turun dari close sebelumnya |
| `LOCK_UP` | open = high = low = close dan naik |
| `LIMIT_DOWN` / `LIMIT_UP` | close = low (atau high) dan perubahan ≥ 90 % dari batas auto-rejection pita harganya |
| `SUSPENSION_GAP` | jeda > 3 hari bursa tanpa bar (selain libur panjang Lebaran) |
| `CORP_ACTION` | lompatan > 35 % yang tidak kembali **dan** cocok dengan data split/aksi korporasi Yahoo |

- Batas auto-rejection BEI per pita harga disimpan sebagai konstanta di `config.py` dengan catatan
  "cocokkan dengan idx.co.id"; deteksi `LOCK_*` tidak bergantung angka ini.
- Aksi korporasi: `yf.Ticker(t).actions` diambil bersama fundamental (mingguan), disimpan di
  `fundamentals_cache.corp_actions` (JSON). Bila ada split setelah data cache dibuat → cache candle saham
  itu diunduh ulang penuh.

### 5.3 Dampak ke perhitungan
- ATR "bersih": bar `LOCK_*` diganti rata-rata TR 14 hari sebelumnya (tidak dibuang, supaya urutan hari tetap).
- `find_pivots`: bar `LOCK_*` tidak boleh menjadi swing high/low.
- `actionability`: gerbang `data_ok` [P1].
- `levels.abnormal_recent`: daftar `{date, kind}` 20 hari terakhir.
- `data_quality` report: ringkasan jumlah hari tidak normal.

### 5.4 Route & UI
- `/api/stock/{t}/analysis`: `abnormal_days` (20 hari terakhir).
- `/api/stock/{t}/chart`: `markers` untuk grafik.
- UI: chip di detail & kartu Top 10 "⚠ ARB 19 Okt"; marker di grafik [P2]; tooltip penjelasan ARA/ARB
  di glosarium.

### 5.5 Pengujian & kriteria lulus
- Unit: data sintetis tiap jenis; VICI 19 Okt (o=h=l=c=885) → `LOCK_DOWN`.
- Backtest: ATR bersih vs lama — **lulus** bila persentase kena cut loss pada saham yang punya hari
  terkunci tidak memburuk dan R bersih tidak turun (out-of-sample). Bila memburuk, deteksi tetap
  ditampilkan tapi ATR lama dipertahankan.

### 5.6 Selesai bila
- [x] abnormal_days.py + konstanta pita + aksi korporasi mingguan
- [x] ATR bersih + pivot + gerbang data_ok — ATR/pivot bersih dibangun & diuji, tetapi dimatikan (`CLEAN_LEVELS`)
  karena tidak lebih baik di periode uji; gerbang data_ok dipakai
- [x] route (abnormal_days, markers) + UI chip/marker/glosarium
- [x] uji backtest
- [ ] pengambilan ulang candle setelah split masih terjadi saat detail saham dibuka — akan dipindah ke lapisan data

---

## 6. POIN 4 — Breadth pasar & kekuatan sektor

### 6.1 Tujuan
Membaca "kesehatan" pasar dari seluruh universe dan tahu sektor mana yang kuat/lemah.

### 6.2 Breadth (`engine/market_breadth.py`)
Per tanggal (dihitung dari `candles` 126 saham; 120 hari terakhir untuk riwayat):
- % saham di atas EMA20 / EMA50 / EMA200
- naik vs turun (advance/decline) dan garis A/D kumulatif
- jumlah high 20 hari baru vs low 20 hari baru
- % saham dengan CMF > 0
Tabel baru `market_breadth(market, date, metrics JSON, updated_at, PRIMARY KEY(market,date))`.
Dihitung di akhir `_run_scan` (hari ini) + backfill 120 hari saat pertama kali / bila kosong.

### 6.3 Sektor
- Sumber: `info["sector"]`, `info["industry"]` dari Yahoo (sudah dipanggil saat ambil fundamental) →
  kolom baru `fundamentals_cache.sector`, `industry` (migrasi).
- Label Indonesia: peta `engine/data/sector_map.json` (Energy → Energi, Basic Materials → Barang Baku,
  Financial Services → Keuangan, dst., mendekati klasifikasi IDX-IC). Saham tanpa data → "Lainnya"
  dan bisa diisi manual di peta.
- Kekuatan sektor (`sector_strength`): per sektor — median return 20h & 60h, % di atas EMA50, median
  skor, jumlah LAYAK; peringkat 1..N.
- Konsentrasi: peringatan bila ≥ 3 saham dari Top 10 (atau watchlist) satu sektor.

### 6.4 Integrasi ke penilaian (bertahap)
- Tahap A (rilis pertama): **tampilan saja** — tidak mengubah skor/mode.
- Tahap B (setelah backtest): kandidat aturan — mode CAUTIOUS bila % di atas EMA50 < 30 %;
  bonus kecil untuk sektor peringkat atas. Dipakai hanya bila lulus out-of-sample.

### 6.5 Route
| Method | Path | Isi |
|---|---|---|
| GET | `/api/market/breadth?market&days=120` | riwayat breadth + nilai hari ini |
| GET | `/api/market/sectors?market` | kekuatan sektor + anggota |
| — | `/api/screener` | baris + `sector`, `sector_rank` |

### 6.6 UI
- **Screener**: panel lipat di atas tabel "Kondisi Pasar & Sektor":
  - Kartu breadth: % di atas EMA50 (angka + grafik garis 120 hari vs IHSG), naik/turun hari ini, high/low baru.
  - Tabel/heatmap sektor: peringkat, return 20h/60h, % di atas EMA50, jumlah LAYAK; klik sektor → filter tabel.
  - Kolom "Sektor" + filter sektor di `ScreenerFilters.tsx`.
- **Top 10**: chip sektor di tiap kartu; peringatan konsentrasi sektor.
- **Watchlist**: peringatan konsentrasi sektor.
- **Sidebar/Header**: ringkasan satu baris "Breadth 28 % di atas EMA50 (lemah)".
- Grafik memakai `lightweight-charts` yang sudah ada (tanpa library baru).

### 6.7 Pengujian & kriteria lulus
- Unit: breadth dari data sintetis (angka dihitung manual), peta sektor, konsentrasi.
- Kinerja: hitung breadth harian ≤ 1 detik untuk 126 saham; backfill 120 hari ≤ 10 detik.
- Backtest Tahap B: aturan breadth/sektor dipakai hanya bila menaikkan R bersih out-of-sample.

### 6.8 Selesai bila
- [x] market_breadth.py + tabel + backfill
- [x] sektor + peta + sector_strength
- [x] route + tipe TS
- [x] UI panel pasar & sektor, kolom & filter, chip & peringatan konsentrasi (Top 10)
- [x] (Tahap B) hasil backtest dicatat; breadth sebagai rem **ditolak**, sektor tidak bisa diuji → hanya informasi

---

## 7. Roadmap & ketergantungan

> **Status 23 Okt 2026 (akhir):** Fase 0–5 ✅ selesai — lihat `docs/hasil-akhir-fase1-5.md`. Fase 0 ✅ selesai (tanpa biaya transaksi). Di luar rencana awal juga selesai:
> **bot Telegram** (rencana harian, cek tengah hari, peringatan zona beli/TP/CL, rekam jejak mingguan, perintah grup)
> dan **mode server Linux** (`docs/DEPLOY_LINUX.md`). Peringatan "masuk zona beli" sudah ada di Telegram; versi
> notifikasi di dalam aplikasi tetap di Fase 3.

```
Fase 0  Alat ukur (P5 inti)  ─┬─► Fase 1  P1 status + volatilitas ─┬─► Fase 4  P4 breadth & sektor (tampilan)
                              │                                     │
                              └─► Fase 2  P3 hari tidak normal  ────┘
Fase 3  P2 garis grafik + alert entry_zone   (bisa paralel dengan Fase 1/2; alert butuh status P1)
Fase 5  Kalibrasi akhir: backtest ulang semua aturan, Tahap B P4, laporan akhir & rilis
```

| Fase | Isi | Ketergantungan | Ukuran | Rilis installer |
|---|---|---|---|---|
| 0 | Biaya, plan_sim, backtest 126 saham, rekam jejak dengan fill | — | L | ya (Histori Prediksi baru) |
| 1 | Status LAYAK/TUNGGU/HINDARI, pemecah seri, too_volatile | Fase 0 (penyetelan ambang) | L | ya |
| 2 | ARA/ARB/suspensi/aksi korporasi, ATR bersih | Fase 0 (uji) | M | digabung dengan Fase 1 bila selesai bersamaan |
| 3 | Garis level di grafik, alert entry_zone | status dari Fase 1 untuk isi alert | M | ya |
| 4 | Breadth & sektor (tampilan) | — (status P1 untuk jumlah LAYAK per sektor) | L | ya |
| 5 | Kalibrasi akhir, Tahap B P4, laporan | semua | M | ya |

Fase 3 bagian grafik dan Fase 4 bisa dikerjakan di sesi terpisah secara paralel karena menyentuh file
yang berbeda (ChartView/StockDetailModal vs market_breadth/Screener).

---

## 8. Hal lintas-poin

### 8.1 Kontrak data (TypeScript `ui/src/types/stock.ts`)
- `TradeLevels` + `ladder`, `abnormal_recent`, flag `too_volatile`
- `ActionInfo { status: 'LAYAK'|'TUNGGU'|'HINDARI'; reasons: string[]; gates: Record<string, boolean> }`
- `ScreenerItem` + `action`, `rank`, `sector`, `sector_rank`
- `BreadthPoint`, `SectorStrength`, `PlanSimSummary`, `TradingCosts`

### 8.2 Migrasi database (semua idempoten, pola yang sudah ada)
| Tabel | Perubahan | Fase |
|---|---|---|
| `prediction_snapshots` | + entry_low, entry_high, recommended_entry | 0 |
| `alert_state` | + entry_low, entry_high | 3 |
| `fundamentals_cache` | + sector, industry, corp_actions | 2/4 |
| `market_breadth` | tabel baru | 4 |
| `direction_data` (JSON) | + action, rank (via DIRECTION_KEYS) | 1 |

### 8.3 Pengaturan baru
- Biaya transaksi (Fase 0), toggle garis grafik (Fase 3, disimpan per pengguna di localStorage),
  preferensi alert `entry_zone` (Fase 3, ikut mekanisme alert yang ada).

### 8.4 Kinerja (anggaran)
- Scan IDX 126 saham: tetap ≤ 30 detik setelah scan pertama (tambahan P1/P3/P4 < 3 detik).
- Backtest 3 tahun 126 saham: job latar belakang ≤ 5 menit, hasil disimpan, tidak memblokir UI.

### 8.5 Pipeline rilis per fase
1. `python -m pytest -q` lulus semua (jumlah tes: lihat `python -m pytest -q`).
2. `npm run build` (tsc tanpa error).
3. Verifikasi browser (`preview_start saham-engine`) untuk perubahan tampilan; tidak ada error konsol/server.
4. `pyinstaller -y saham.spec` → `makensis installer.nsi` → `dist/SAHAM_Setup_x64.exe`.
5. Catatan perubahan singkat untuk pengguna + pembaruan memori proyek.

### 8.6 Risiko umum & mitigasi
| Risiko | Mitigasi |
|---|---|
| Overfitting ambang | in/out-of-sample dikunci di depan; satu kali uji out-of-sample per aturan |
| Data Yahoo bolong / terlambat | sudah ada data_quality; P3 menambah deteksi; label "data tertunda ±15 menit" |
| Sektor Yahoo kosong untuk sebagian saham IDX | peta manual `sector_map.json` + kategori "Lainnya" |
| Batas permintaan Yahoo | batch download (sudah), aksi korporasi mingguan, backtest di latar belakang |
| Pasar krisis → hampir selalu 0 LAYAK | itu jawaban yang benar; UI menjelaskan dan menampilkan "terbaik untuk ditunggu" |

---

## 9. Keputusan yang dibutuhkan dari pengguna sebelum mulai

1. ~~Fee broker~~ — dibatalkan (tanpa biaya transaksi).
2. **Ambang R:R untuk LAYAK**: mulai 1,0 (akan diuji 0,8 / 1,0 / 1,2).
3. **Prediksi resmi hanya dari status LAYAK?** (disarankan ya — rekam jejak jadi jujur; hari krisis = tanpa prediksi).
4. **Breadth/sektor boleh memengaruhi skor setelah lulus backtest?** (disarankan ya, Tahap B).
5. **Rilis per fase atau sekaligus?** (disarankan per fase, agar bisa dipakai dan dinilai bertahap).
