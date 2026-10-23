# Hasil Uji Laporan Keuangan (24 Okt 2026)

**Pertanyaan:** apakah "bendera merah" laporan keuangan tahunan memisahkan rencana trading yang baik dan buruk?

**Data:** 23.923 rencana walk-forward (126 saham IDX, 29 Apr 2024 – 9 Okt 2026, simulator yang sudah diperbaiki:
jual separuh di TP1). Laporan tahunan dari Yahoo (126/126 saham tersedia) dibaca **point-in-time**: laporan tahun buku
dianggap baru diketahui 90 hari setelah akhir tahun buku. 23.854 rencana punya laporan yang sudah terbit saat itu.

## Hasil per bendera (semua status; R rata-rata per transaksi, sebelum biaya)

Rata-rata semua rencana: periode awal **+0,039 R**, periode uji **−0,080 R**.

| Bendera | Periode awal | Periode uji | Konsisten lebih buruk? |
|---|---|---|---|
| Rugi tahun terakhir | +0,048 R (n 458) | −0,317 R (n 253) | tidak (arah berbalik) |
| Rugi berulang (2 dari 3 thn) | +0,063 R | +0,011 R | tidak |
| Laba turun 2 dari 3 thn | +0,136 R | −0,071 R | tidak |
| Laba positif, kas operasi negatif | +0,063 R | −0,013 R | tidak |
| Kas operasi < ½ laba | +0,041 R | −0,206 R | tidak |
| **Utang > 2× ekuitas (non-bank)** | **−0,050 R** (n 648) | **−0,208 R** (n 626) | **ya** |
| Current ratio < 1 | +0,103 R | −0,038 R | tidak |
| Laba operasi < 1,5× bunga | +0,087 R | −0,031 R | tidak |
| Ekuitas negatif | +0,298 R (n 112) | +0,253 R (n 58) | tidak (sampel kecil) |

## Gerbang kandidat untuk status LAYAK

| | Periode awal | Periode uji |
|---|---|---|
| LAYAK sekarang | 848 rencana, +0,064 R | 253 rencana, +0,116 R |
| LAYAK tanpa bendera apa pun | 701, +0,068 R | 155, +0,151 R |
| LAYAK tanpa utang tinggi | 830, +0,047 R | 248, +0,126 R |

- "Tanpa bendera apa pun": selisih periode awal hanya +0,004 R (praktis sama) dan membuang 17–39 % rencana LAYAK → **tidak dipakai**.
- "Tanpa utang tinggi": di periode awal **lebih buruk** (+0,047 vs +0,064 R; hanya 18 rencana LAYAK yang berutang tinggi) → **tidak dipakai** sesuai aturan (pilih di periode awal).

## Keputusan

- Laporan keuangan **ditampilkan sebagai informasi** di halaman detail saham: tren pendapatan/laba 4–5 tahun, kas operasi ÷ laba,
  utang ÷ ekuitas (bank dikecualikan), bendera merah dalam bahasa awam, dan valuasi dibanding median sektor.
- **Tidak mengubah skor maupun status.** Untuk trading 10 hari, kualitas laporan keuangan tidak konsisten memengaruhi hasil;
  ini bukan berarti laporan keuangan tidak penting untuk investasi jangka panjang — hanya tidak terbukti untuk strategi ini.
- Bendera "utang tinggi" diberi catatan bahwa secara umum hasil tradingnya lebih buruk di uji historis.
- Bank & lembaga keuangan tidak dinilai dari utang/current ratio (simpanan nasabah membuat "utang" besar secara wajar).

Skrip: `fundamental_study.py` (scratchpad sesi 24 Okt 2026), modul `engine/screener/financial_statements.py`.
