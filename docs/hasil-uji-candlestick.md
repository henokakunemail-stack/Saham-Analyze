# Hasil Uji Pola Candlestick (24 Okt 2026)

**Pertanyaan:** apakah pola candlestick yang dibaca aplikasi benar-benar mendahului kenaikan/penurunan di saham IDX?

## Masalah deteksi lama (diperbaiki)

- Hari terkunci satu harga (ARA/ARB) terbaca **Hammer / Hanging Man** — "Hanging Man" lama tampak +7 % (10 hari)
  karena sebenarnya hari ARA yang terkunci.
- Doji dengan ekor bawah terbaca Hammer (Doji dicek terlambat); Doji kecil di dalam candle merah terbaca Harami.
- Pola pembalikan tanpa syarat "ada yang dibalik" (bullish harus setelah turun, bearish setelah naik) dan tanpa ukuran minimum.
- Pola bullish jauh lebih banyak dari bearish (tidak ada Bearish Engulfing, Dark Cloud Cover, Three Black Crows).

Deteksi baru: `engine/indicators/candles.py` (tes: `tests/test_candles.py`).

## Uji peristiwa — 126 saham IDX, 29 Apr 2024 – 9 Okt 2026

Setiap bar harian diberi label pola; hasil = return 10 hari ke depan **dibanding rata-rata semua saham di hari yang sama**
(menghilangkan arah pasar). Periode awal < 11 Des 2025, periode uji sesudahnya.

| Pola (deteksi baru) | Arah buku teks | Periode awal | Periode uji | Kesimpulan |
|---|---|---|---|---|
| Bullish Engulfing | naik | −1,45 % (n 268) | +0,16 % (n 220) | tidak terbukti |
| Hammer | naik | −0,76 % (n 1.261) | −0,52 % (n 604) | tidak terbukti |
| Morning Star | naik | −0,79 % (n 545) | −0,81 % (n 196) | tidak terbukti |
| Piercing Line | naik | −1,85 % (n 261) | −0,47 % (n 119) | tidak terbukti |
| Bullish Harami | naik | −0,85 % (n 993) | −0,58 % (n 519) | tidak terbukti |
| Inverted Hammer | naik | −0,91 % | −0,16 % | tidak terbukti |
| Three White Soldiers | naik | −1,14 % (n 113) | +0,98 % (n 43) | data kurang |
| Shooting Star | turun | +0,45 % | +0,15 % | tidak terbukti |
| Bearish Engulfing | turun | −0,23 % | +0,71 % | tidak terbukti |
| Evening Star | turun | −0,88 % | +0,81 % | tidak terbukti |
| Dark Cloud Cover | turun | +0,48 % | −0,23 % | tidak terbukti |
| Three Black Crows | turun | −1,10 % (n 380) | −0,31 % (n 176) | cenderung lebih buruk (selisih kecil) |

**Kesimpulan:** di IDX periode ini, pola candlestick **tidak memberi keunggulan yang konsisten** — pola "bullish" justru
sedikit lebih buruk dari rata-rata (sesuai temuan sebelumnya: kekuatan jangka pendek di IDX cenderung berbalik).

## Pengaruh ke skor & status (kalibrasi walk-forward, jual separuh di TP1)

| Varian | LAYAK periode awal | LAYAK periode uji |
|---|---|---|
| Candle di skor, deteksi lama (sebelumnya) | 848 rencana, +0,064 R | 253, +0,116 R |
| Tanpa candle di skor | 846, +0,055 R | 246, +0,063 R |
| **Candle di skor, deteksi baru (dipakai)** | 844, +0,062 R | 247, +0,116 R |

- Mencabut candle dari skor memperburuk LAYAK di kedua periode → candle **tetap** di skor (bobotnya kecil, pilar setup 5 %).
- Deteksi baru vs lama: −0,002 R di periode awal, sama di periode uji — dalam batas kebetulan. Dipakai karena memperbaiki
  kesalahan nyata (hari terkunci terbaca Hammer, Doji terbaca Hammer/Harami). Ini satu-satunya keputusan yang tidak murni
  "pilih yang terbaik di periode awal", dan dicatat di sini dengan alasannya.

## Di aplikasi

- Setiap pola menampilkan rekam jejaknya di IDX ("tidak terbukti mendahului kenaikan: 10 hari setelahnya rata-rata −0,8 %
  dan −0,5 % dibanding saham lain"), dari `engine/data/candle_stats.json`.
- Label "Keandalan pola: tinggi" (dari buku teks) dihapus; warna pola dibuat netral.

Skrip: `candle_study.py`, `candle_calib.py`, `make_candle_stats.py` (scratchpad sesi 24 Okt 2026).
