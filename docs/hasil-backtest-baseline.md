# Hasil Backtest Baseline — Fase 0 (23 Okt 2026)

Pembanding untuk semua perubahan aturan di Fase 1–5. Dihitung dengan `engine/screener/plan_sim.py`
melalui `compute_backtest("IDX", 10)`.

**Aturan simulasi:** rencana dibuat dari penutupan hari itu (tanpa melihat masa depan); order beli di harga saran
berlaku 5 hari bursa; batal bila harga dibuka di bawah cut loss sebelum terisi; setelah terisi diberi 10 hari bursa;
cut loss diperiksa sebelum TP; TP tidak dihitung pada hari pengisian; setelah TP1 masih boleh naik ke TP2.
**Tanpa biaya transaksi** (keputusan pengguna). Sentimen berita & fundamental tidak ikut (tidak ada riwayat).

Data: 126 saham IDX (daftar default), 29 Apr 2024 – 8 Okt 2026, evaluasi tiap 3 hari bursa. Waktu hitung ±15 menit.
Catatan survivorship: daftar = saham yang masih likuid pada Okt 2026.

## Keseluruhan

| Ukuran | Semua | Periode awal (s/d 11 Des 2025) | Periode uji (sejak 11 Des 2025) |
|---|---|---|---|
| Rencana | 23.912 | 15.798 | 8.114 |
| Sempat terisi | 68,3 % | 67,3 % | 70,1 % |
| Kena TP dulu (dari yang terisi) | 53,7 % | 55,5 % | 50,5 % |
| Rata-rata hasil | **+0,157 R** (≈ +1,01 %) | +0,205 R | **+0,069 R** |
| Profit factor | 1,41 | 1,60 | 1,15 |
| Lama memegang rata-rata | 4,9 hari | 5,1 | 4,6 |

Hasil melemah di periode uji (termasuk krisis MSCI Okt 2026).

## Per kelompok (rata-rata R · kena TP dulu)

| Skor | R | TP dulu |
|---|---|---|
| 0–34 | +0,122 | 51,2 % |
| 35–44 | +0,130 | 57,8 % |
| 45–54 | +0,158 | 58,5 % |
| 55–64 | +0,202 | 54,4 % |
| 65–74 | +0,173 | 50,4 % |
| 75–100 | **+0,268** | 49,3 % |

| Risiko:untung | Rencana | R | TP dulu |
|---|---|---|---|
| < 0,5 | 9.604 | +0,158 | 67,5 % |
| 0,5–1 | 7.683 | +0,158 | 50,9 % |
| 1–1,5 | 3.620 | +0,160 | 37,7 % |
| ≥ 1,5 | 3.005 | +0,150 | 22,6 % |

| Kondisi pasar | R | TP dulu |
|---|---|---|
| Normal | +0,201 | 56,4 % |
| Waspada | +0,095 | 51,3 % |
| Bearish | **+0,044** | 48,3 % |
| Krisis | +0,221 | 52,6 % |

| ATR % | R | TP dulu |
|---|---|---|
| < 3 % | +0,135 | 56,3 % |
| 3–5 % | +0,156 | 56,9 % |
| 5–8 % | +0,179 | 50,1 % |
| ≥ 8 % | +0,175 | 39,6 % |

## Implikasi untuk Fase 1 (harus dikonfirmasi di periode uji)

1. **Syarat R:R ≥ 1 tidak didukung data.** Rata-rata R hampir sama di semua kelompok R:R (+0,15–0,16); R:R
   tinggi hanya menurunkan peluang kena TP. Gerbang `rr_ok` perlu diuji ulang atau dihapus.
2. **Skor tinggi sedikit lebih baik** (75–100: +0,27 R vs 0–34: +0,12 R) — layak dipakai sebagai pemecah seri.
3. **Mode BEARISH paling lemah** (+0,04 R); mode krisis justru +0,22 R (rebound setelah panik) — aturan
   "CRASH = tahan" perlu diuji, bukan diasumsikan.
4. **ATR ≥ 8 %**: peluang TP turun ke 39,6 % meski R rata-rata tidak memburuk → label "volatil" sebagai informasi,
   bukan penghapus.
