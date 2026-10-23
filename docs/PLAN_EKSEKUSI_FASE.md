# Rencana Eksekusi Fase 1–5 (paralel)

> **STATUS 23 Okt 2026: SELESAI.** Hasil & keputusan: `docs/hasil-akhir-fase1-5.md`, kalibrasi: `docs/hasil-kalibrasi-fase1.md`.
> Ambang final LAYAK: **risiko ≤ 6 %, likuiditas ≥ Rp2 miliar/hari** (menggantikan 8 % / Rp5 miliar di bawah).

Dibuat 23 Okt 2026. Melengkapi `docs/RENCANA_5_POIN.md` (desain) dan `docs/hasil-backtest-baseline.md` (pembanding).

## Cara kerja paralel

Proyek ini bukan repo git, jadi semua pekerja berbagi satu folder. Supaya aman:

1. **4 pekerja jalan bersamaan**, masing-masing hanya menyentuh **file miliknya** (tabel di bawah) dan file baru
   yang ia buat sendiri. File bersama tidak disentuh pekerja.
2. **Integrator** (sesi utama) memegang file bersama dan menyatukan hasil tiap pekerja lewat kontrak antarmuka
   di bagian "Kontrak" — urut: F1 → F2 → F3 → F4.
3. **Fase 5** (kalibrasi akhir + laporan) berjalan setelah semua tersatukan, karena butuh semua aturan.
4. Setiap pekerja menjalankan test miliknya saja; integrator menjalankan seluruh test, build UI, verifikasi
   browser, lalu installer.

## Kepemilikan file

| Pemilik | File (boleh diubah / dibuat) |
|---|---|
| **P1 – Fase 1 engine & UI status** | `engine/screener/actionability.py` (baru), `engine/screener/scoring.py`, `engine/screener/backtest.py`, `engine/screener/calibration.py` (baru), `ui/src/components/ActionStatusBadge.tsx`, `ActionGates.tsx`, `PillarBars.tsx` (baru), `tests/test_actionability.py`, `tests/test_calibration.py` (baru) |
| **P2 – Fase 2 hari tidak normal** | `engine/collectors/abnormal_days.py`, `engine/collectors/corp_actions.py` (baru), `ui/src/components/AbnormalDaysChip.tsx` (baru), `tests/test_abnormal_days.py` (baru) |
| **P3 – Fase 3 grafik & alert** | `ui/src/components/ChartView.tsx`, `engine/notifications.py`, `ui/src/components/NotificationCenter.tsx`, `tests/test_entry_zone_alert.py` (baru) |
| **P4 – Fase 4 breadth & sektor** | `engine/market_breadth.py`, `engine/sectors.py`, `engine/data/sector_map.json`, `engine/routes/market.py` (baru), `ui/src/components/MarketBreadthPanel.tsx`, `ui/src/api/market.ts` (baru), `tests/test_breadth_sectors.py` (baru) |
| **Integrator** | `engine/main.py`, `engine/db.py`, `engine/screener/trade_levels.py`, `engine/indicators/technical.py`, `engine/indicators/trend.py`, `engine/screener/predictions.py`, `engine/telegram/*`, `ui/src/types/*`, `Top10Potential.tsx`, `StockDetailModal.tsx`, `ScreenerTable.tsx`, `ScreenerFilters.tsx`, `lib/*`, `App.tsx`, dokumen |

## Kontrak antarmuka (dipakai lintas fase)

**Baris hasil scan** (`_analyze_single_ticker` → `screener_cache`, `/api/screener`): sudah berisi `ticker, market, price,
score, verdict, is_speculative, market_mode, pullback_state, levels{…}, screen{avg_value_20d, illiquid, rs_60d, atr_pct, …}`.
Fase-fase menambah:

| Kunci baru | Dari | Bentuk |
|---|---|---|
| `raw_score` | F1 (scoring) | skor sebelum rem pasar (int) |
| `pillar_values` | F1 (scoring) | `{pullback, trend, money_flow, momentum, setup, fundamental?, sentiment?}` nilai −1..1 |
| `action` | F1 (actionability.assess) | `{status: LAYAK/TUNGGU/HINDARI, reasons: [str], gates: {nama: bool}}` |
| `rank` | F1 (rank_key, ditulis integrator) | 1..N |
| `levels.flags += "too_volatile"` | integrator (trade_levels) | bila batas 8 % memaksa jarak cut loss < 1 ATR |
| `levels.ladder` | integrator (trade_levels) | `{supports: [{price, label}], resistances: [{price, label}]}` maks. 3 masing-masing |
| `abnormal_recent` | F2 | `[{date: "YYYY-MM-DD", kind, label}]` 20 hari terakhir |
| `sector`, `sector_rank` | F4 | `"Energi"`, 1..N |

**Fungsi yang disediakan pekerja untuk integrator:**

- F1: `actionability.assess(row) -> dict`, `actionability.rank_key(row) -> tuple`, konstanta ambang di bagian atas modul.
- F2: `abnormal_days.classify_bars(df, market) -> pd.Series[str|None]` (satu label per bar),
  `abnormal_days.recent(df, market, days=20) -> list`, `abnormal_days.clean_true_range(df, kinds) -> pd.Series`,
  `abnormal_days.pivot_mask(kinds) -> np.ndarray[bool]` (False = bar tidak boleh jadi swing),
  `corp_actions.fetch_splits(ticker) -> list` (+ cache mingguan).
- F3: `ChartView` props `levels?: TradeLevels`, `showPlan?`, `showLadder?`, `markers?: {time, kind, label}[]`;
  notifikasi jenis `entry_zone` (deteksi di `notifications.on_scan_complete`, memakai `levels.live` & rencana beku).
- F4: `market_breadth.compute_today(results, market)`, `market_breadth.history(market, days)`, `sectors.sector_of(ticker)`,
  `sectors.sector_strength(results)`, `sectors.concentration(tickers, results)`; router `/api/market/breadth`, `/api/market/sectors`.

## Pekerjaan per fase

### Fase 1 — Status LAYAK/TUNGGU/HINDARI, skor asli, bobot (P1 + integrator)
1. `scoring.py`: simpan `raw_score` (sebelum rem pasar/spekulatif/tren turun) dan `pillar_values` di keluaran.
2. `actionability.py`: gerbang `market_ok`, `signal_ok`, `risk_ok` (risk_pct ≤ 8 % awal → **final ≤ 6 %**), `vol_ok`
   (bukan `too_volatile`), `liquid_ok` (≥ Rp5 miliar awal → **final ≥ Rp2 miliar** / US$20 jt; lihat
   `docs/hasil-kalibrasi-fase1.md`), `data_ok` (tanpa ARB/suspensi 3 hari — dari F2, opsional bila belum ada);
   aturan HINDARI/TUNGGU; `rank_key` (status → raw_score → skor → R:R → likuiditas).
3. `backtest.py`: baris walk-forward menyimpan `raw_score`, `pillar_values`, `risk_pct`, `avg_value_20d`, `action`.
4. `calibration.py`: hitung baris backtest sekali (disimpan), uji varian gerbang & bobot **di periode awal**,
   uji **sekali** di periode uji; tulis `docs/hasil-kalibrasi-fase1.md`. Konstanta pemenang dipasang di
   `actionability.py`/`scoring.py` hanya bila lulus (LAYAK > TUNGGU > HINDARI, LAYAK ≥ +0,10 R di periode uji).
5. UI: `ActionStatusBadge`, `ActionGates` (✓/✗ + alasan), `PillarBars` (batang per pilar).
6. Integrator: panggil `assess` di scan, urut `rank_key`, simpan `action/rank/raw_score/pillar_values`
   (DIRECTION_KEYS), `select_predictions` hanya LAYAK (bila kalibrasi lulus), Top 10 (ringkasan
   "N LAYAK · N TUNGGU · N HINDARI", kondisi kosong, filter), detail saham (gerbang + pilar), Screener (kolom status,
   preset "Layak"), Telegram (status di rencana & /top10), prompt AI.

### Fase 2 — Hari tidak normal (P2 + integrator)
1. `abnormal_days.py`: `LOCK_DOWN/LOCK_UP` (o=h=l=c), `LIMIT_DOWN/UP` (close di ekstrem & ≥ 90 % batas pita),
   `SUSPENSION_GAP` (> 3 hari bursa tanpa bar), `CORP_ACTION` (lompatan > 35 % tak kembali + split Yahoo).
   Konstanta pita auto-rejection BEI di modul (catatan: cocokkan idx.co.id).
2. `corp_actions.py`: split/dividen Yahoo, cache tabel sendiri (mingguan); bila split baru → minta unduh ulang.
3. `AbnormalDaysChip.tsx`: chip "⚠ ARB 19 Okt" + tooltip.
4. Integrator: ATR bersih & pivot mask di `trade_levels`/`trend`, `abnormal_recent` di baris & analisis, `markers`
   di endpoint chart, gerbang `data_ok`, chip di Top 10 & detail.
5. Uji: VICI 19 Okt → LOCK_DOWN; backtest ATR bersih vs lama (lulus bila kena-CL tidak memburuk & R tidak turun).

### Fase 3 — Grafik & peringatan masuk zona (P3 + integrator)
1. `ChartView.tsx`: garis zona beli/CL/TP1/TP2, tangga S/R, marker hari tidak normal, toggle dari props.
2. `notifications.py`: jenis `entry_zone` (watchlist + Top 10 LAYAK/TUNGGU), migrasi `alert_state` (entry_low/high)
   di modul sendiri, cooldown yang ada.
3. `NotificationCenter.tsx`: ikon & label `entry_zone`.
4. Integrator: `levels.ladder` di trade_levels, toggle "Rencana" & "Support/Resistance" di detail saham.

### Fase 4 — Breadth & sektor (P4 + integrator)
1. `market_breadth.py`: % di atas EMA20/50/200, naik/turun, high/low 20 hari baru, % CMF>0; tabel sendiri; backfill 120 hari.
2. `sectors.py` + `sector_map.json`: sektor Yahoo → label Indonesia (IDX-IC), tabel cache sendiri (mingguan),
   kekuatan sektor, konsentrasi (≥ 3 saham satu sektor).
3. `routes/market.py`: `/api/market/breadth?market&days`, `/api/market/sectors?market`.
4. `MarketBreadthPanel.tsx` (+ `api/market.ts`): kartu breadth (+ grafik garis), tabel sektor (klik = filter).
5. Integrator: router, hitung breadth di akhir scan, `sector/sector_rank` di baris, kolom & filter sektor di Screener,
   chip sektor & peringatan konsentrasi di Top 10, ringkasan breadth di sidebar.
   Tahap B (breadth/sektor memengaruhi skor) hanya bila lulus kalibrasi Fase 5.

### Fase 5 — Kalibrasi akhir & laporan (integrator, setelah 1–4)
1. Backtest ulang 126 saham dengan semua aturan (ATR bersih, status, Tahap B kandidat).
2. Bandingkan dengan baseline; aturan yang tidak lulus periode uji → dimatikan / diberi label "belum terbukti".
3. `docs/hasil-akhir-fase1-5.md`, perbarui memori proyek, installer.

## Kriteria selesai keseluruhan
- [x] Semua test lulus (`python -m pytest -q`), `npm run build` tanpa error
- [x] Verifikasi browser: Top 10 (status, ringkasan, chip sektor/ARB), detail (gerbang, pilar, garis grafik, marker),
      Screener (kolom & filter status/sektor, panel breadth), notifikasi entry_zone, Telegram memakai status
- [x] Laporan kalibrasi Fase 1 & laporan akhir Fase 5 tersimpan; aturan yang gagal tidak dipakai untuk menilai
- [x] Installer baru
