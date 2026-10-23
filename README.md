<div align="center">

# 📈 SAHAM — Stock Screener & Money-Flow Analyzer untuk Saham Indonesia (IDX) & US

**Screener saham IHSG open-source** yang mencari *pullback sehat dalam uptrend*, membaca **aliran uang (bandarmologi: CMF, OBV, VSA)**, lalu menyusun **rencana beli yang bisa dieksekusi** — zona entry, cut loss, take profit — sesuai **fraksi harga BEI**, lengkap dengan **status LAYAK / TUNGGU / HINDARI** yang teruji backtest, **bot Telegram**, dan **validasi AI**.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-engine-009688?logo=fastapi&logoColor=white)](#)
[![React](https://img.shields.io/badge/React%2018-Vite%20%2B%20TypeScript-61DAFB?logo=react&logoColor=black)](#)
[![Tests](https://img.shields.io/badge/pytest-288%20passed-brightgreen)](#-tes)
[![Windows](https://img.shields.io/badge/Windows-installer%20.exe-0078D6?logo=windows&logoColor=white)](#1-installer-windows-paling-mudah)
[![Docker](https://img.shields.io/badge/Docker-server%2024%2F7-2496ED?logo=docker&logoColor=white)](docs/DEPLOY_LINUX.md)
[![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)](#-bot-telegram)

*Alat bantu analisa — **bukan ajakan beli/jual**. Hasil masa lalu bukan jaminan hasil masa depan.*

</div>

---

## ✨ Kenapa SAHAM?

Kebanyakan screener hanya memberi daftar saham "bagus". SAHAM menjawab pertanyaan yang sebenarnya penting bagi trader ritel:

| Pertanyaan | Jawaban SAHAM |
|---|---|
| Beli di harga berapa? | **Zona beli + harga saran (limit)** di support nyata (swing low, EMA20/50, low 20/60 hari), sudah dibulatkan ke fraksi harga BEI |
| Salah di mana? | **Cut loss** di bawah support struktural, risiko dibatasi maks 8 % |
| Jual di mana? | **TP1 = resistance terdekat**, TP2 = resistance berikutnya — tidak digelembungkan demi R:R yang cantik |
| Boleh dieksekusi sekarang? | **LAYAK / TUNGGU / HINDARI** — syarat risiko ≤ 6 %, likuiditas ≥ Rp2 M/hari, tidak terlalu volatil, pasar tidak krisis, tanpa ARA/ARB baru |
| Rencana kemarin masih berlaku pagi ini? | Rencana **dikunci selama sesi**; harga live dibandingkan dengan rencana: *di zona beli*, *jangan dikejar*, *sudah di TP1*, *rencana batal* |
| Apakah metodenya terbukti? | **Backtest walk-forward** 126 saham IDX, 2024–2026, hasilnya dipublikasikan apa adanya di [docs/](docs/hasil-akhir-fase1-5.md) |

## 🚀 Fitur Utama

- **Screener 126 saham IDX likuid + 74 saham US** (NYSE/Nasdaq), universe bisa diubah sampai 200 saham.
- **Skor komposit 0–100 — strategi *Pullback dalam Uptrend*** dari 7 pilar: setup pullback, arah tren vs indeks, aliran uang (CMF 20, divergensi OBV, VSA), momentum (RSI, MACD), kualitas setup (konfluensi 6 gate), fundamental (ROE, margin, DER, PE, PBV), sentimen berita.
- **Mode pasar otomatis** `NORMAL → CAUTIOUS → BEARISH → CRASH` dari kondisi IHSG + berita sistemik (MSCI, trading halt, arus keluar asing).
- **Rencana trading yang realistis**: entry/cut loss/TP di level support-resistance nyata, **fraksi harga BEI** (Rp1/2/5/10/25), risiko per lot, basis setiap level dijelaskan.
- **Posisi harga hari ini vs rencana**: Top 10 otomatis menurunkan saham yang sudah menyentuh TP, menembus cut loss, atau lari jauh di atas zona beli — supaya daftar berisi rencana yang *masih bisa dijalankan hari ini*.
- **Cek tengah hari** (jeda siang BEI) dan **panduan saat bursa buka** (gap pembukaan, sesi 2).
- **Peringatan**: harga mencapai harga saran beli, menyentuh TP1, menyentuh cut loss — di aplikasi dan Telegram.
- **Deteksi kualitas data**: hari **ARA/ARB** (harga terkunci), suspensi, aksi korporasi/split — agar ATR, pivot, dan sinyal volume tidak menyesatkan.
- **Market breadth** (% saham di atas EMA50) dan **kekuatan sektor** + peringatan konsentrasi sektor.
- **Histori Prediksi**: rekam jejak nyata saham LAYAK, **uji historis** (backtest walk-forward), dan rekam jejak **validasi AI**.
- **Validasi AI** (second opinion): Claude (API key / login akun), 9router, atau endpoint kompatibel OpenAI — AI diberi level & status engine, termasuk posisi harga hari ini.
- **Bot Telegram**: rencana harian setelah penutupan, cek tengah hari, peringatan langsung, rekam jejak mingguan, perintah `/top10`, `/cek BBCA`, `/rencana`, `/pasar`, `/rekam`.
- **Grafik candlestick lokal** (lightweight-charts), radar berita RSS (CNBC Indonesia, Kontan, Antara, Yahoo, CNBC US), watchlist, glosarium istilah.
- **Desktop Windows** (installer .exe) **atau server Linux 24/7** (Docker / systemd) dengan basic-auth.

## 📊 Seberapa terbukti? (angka jujur)

Backtest walk-forward 126 saham IDX, 29 Apr 2024 – 9 Okt 2026, 23.923 rencana, evaluasi tiap 3 hari bursa, batas 10 hari, order beli limit di harga saran, **tanpa biaya transaksi**. Dipilih di periode awal (< 11 Des 2025), diuji sekali di periode uji (≥ 11 Des 2025):

| Status | Periode uji: rencana / terisi | Rata-rata R | Profit factor |
|---|---|---|---|
| **LAYAK** | 253 / 182 | **+0,116 R** | 1,29 |
| TUNGGU | 3.408 / 2.521 | −0,052 R | 0,88 |
| HINDARI | 4.464 / 2.991 | −0,115 R | 0,76 |

- Urutan LAYAK > TUNGGU > HINDARI terjaga di kedua periode → status ini **membantu menghindari rencana yang buruk**.
- Biaya transaksi (±0,4 % beli+jual) setara ±0,10 R → **setelah biaya praktis impas**. Belum ada bukti untung bersih — karena itu aplikasi menyebut angkanya apa adanya, bukan "akurasi 99 %".
- Simulator rencana memakai aturan keluar: jual separuh di TP1, cut loss sisa dinaikkan ke harga beli, sisanya incar TP2.
- Detail metode, kandidat yang **ditolak** (termasuk tweak level yang "terlihat masuk akal" tetapi lebih buruk), dan cara reproduksi: [docs/hasil-akhir-fase1-5.md](docs/hasil-akhir-fase1-5.md), [docs/hasil-backtest-baseline.md](docs/hasil-backtest-baseline.md), [docs/hasil-kalibrasi-fase1.md](docs/hasil-kalibrasi-fase1.md).

## 🧠 Cara SAHAM membaca sebuah saham

```
Harga & volume (yfinance) ──► Indikator teknikal + aliran uang + tren vs IHSG + pullback state
                                            │
Berita RSS ──► Sentimen & katalis risiko     │        Fundamental (ROE, margin, DER, PE, PBV)
                                            ▼
                       Skor komposit 0–100  +  Mode pasar (NORMAL/CAUTIOUS/BEARISH/CRASH)
                                            │
                       Level trading: zona beli · harga saran · cut loss · TP1 · TP2 (fraksi BEI)
                                            │
                       Status eksekusi: LAYAK / TUNGGU / HINDARI  (gate risiko, likuiditas, volatilitas, data)
                                            │
                       Posisi harga hari ini vs rencana  ──►  Top 10 · peringatan · Telegram · validasi AI
```

Skor dan rencana selalu dihitung dari **penutupan terakhir yang final** (BEI: ±16:45 WIB); sepanjang sesi hanya *harga* dan *posisi terhadap rencana* yang bergerak. Ini mencegah candle setengah jadi mengubah sinyal setiap lima menit.

## ⚡ Cara Menjalankan

### 1. Installer Windows (paling mudah)
Unduh/buat `dist/SAHAM_Setup_x64.exe` (lihat [Build](#-build--packaging)) lalu jalankan. Aplikasi terpasang di `C:\Program Files\SAHAM`, database di `%APPDATA%\SAHAM\saham.db`, log di `%TEMP%\saham_app.log`.

### 2. Dari source (jendela desktop)
```bash
cd ui && npm ci && npm run build && cd ..
pip install -r engine/requirements.txt
python run_desktop.py
```
Engine berjalan di `127.0.0.1:8765` dan jendela aplikasi (Edge/Chrome mode aplikasi) terbuka otomatis.

### 3. Mode development (hot reload)
```bash
python -m uvicorn engine.main:app --reload --port 8765   # terminal 1
cd ui && npm run dev                                     # terminal 2 → http://127.0.0.1:5173
```

### 4. Server Linux 24/7 (Docker) + bot Telegram
```bash
cp deploy/.env.example .env   # isi SAHAM_BASIC_AUTH=user:sandi
docker compose up -d --build
```
Panduan lengkap (VPS, SSH tunnel / HTTPS Caddy, backup, troubleshooting): [docs/DEPLOY_LINUX.md](docs/DEPLOY_LINUX.md).

## 🤖 Bot Telegram

1. Buat bot di **@BotFather**, masukkan bot ke grup Anda.
2. **Pengaturan → Bot Telegram** di aplikasi: tempel token → *Cek & simpan* → ketik `/start` di grup → pilih grup → *Aktif*.
3. Jadwal (WIB): rencana untuk besok setelah scan penutupan, cek tengah hari saat jeda siang, peringatan langsung tiap scan saat sesi berjalan, rekam jejak mingguan Jumat.

Satu instance SAHAM saja yang boleh menjalankan bot (desktop **atau** server).

## 🧪 Tes
```bash
pip install "pytest>=8" "httpx>=0.27"
python -m pytest -q        # 288 tes, offline (jaringan diblokir, database sementara)
```

## 📦 Build & Packaging
```powershell
cd ui; npm ci; npm run build; cd ..
pyinstaller -y saham.spec
& "C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi    # → dist/SAHAM_Setup_x64.exe
```

## 🗂️ Struktur Proyek

```
engine/            FastAPI engine
  collectors/      yfinance OHLCV, berita RSS, aksi korporasi, hari ARA/ARB, kualitas data
  indicators/      teknikal, money flow (CMF/OBV/VSA), pullback, tren, metrik screener
  screener/        skor, status LAYAK/TUNGGU/HINDARI, level trading, pipeline, backtest,
                   simulasi rencana, prediksi, kalibrasi, fundamental, sentimen
  ai/              klien AI (Claude / 9router / OpenAI-compatible), log validasi
  telegram/        bot Telegram (API, pesan, layanan)
  routes/          endpoint market, signals, universe, feedback, telegram, system
ui/                React 18 + Vite + TypeScript + Tailwind
tests/             pytest (offline)
docs/              rencana, hasil backtest & kalibrasi, panduan deploy
deploy/ Dockerfile docker-compose.yml   mode server
saham.spec installer.nsi run_desktop.py  desktop Windows
```

## 🙋 Kontribusi & Diskusi

Issue dan pull request terbuka — terutama untuk: data broker summary (saat ini tanpa data broker, aliran dana dibaca dari harga & volume), kalender libur BEI, dan ide gate baru **yang disertai bukti backtest** (`engine/screener/backtest.py`, `engine/screener/calibration.py`). Perubahan skor/level tanpa backtest tidak akan digabung.

## ⚠️ Disclaimer

SAHAM adalah perangkat lunak analisa untuk edukasi dan riset pribadi. Bukan rekomendasi, bukan ajakan membeli atau menjual efek, dan bukan nasihat investasi. Keputusan dan risiko sepenuhnya milik pengguna. Data harga dari Yahoo Finance (tertunda ±15 menit) bisa tidak lengkap.

---

<details>
<summary><b>English summary</b></summary>

**SAHAM** is an open-source stock screener and money-flow analyzer for the **Indonesia Stock Exchange (IDX/JKSE)** and **US stocks**. It scores stocks on a *pullback-in-uptrend* strategy (trend vs index, Chaikin Money Flow, OBV divergence, Volume Spread Analysis, momentum, fundamentals, news sentiment), builds an **executable trade plan** (entry zone, suggested limit price, stop loss, TP1/TP2 on real support/resistance, rounded to IDX tick sizes), gates it with a backtested **LAYAK / TUNGGU / HINDARI** (go / wait / avoid) status, tracks today's price against the frozen plan, and delivers everything through a Windows desktop app, a Linux/Docker server, a Telegram bot and optional AI validation (Claude / OpenAI-compatible). Walk-forward backtest results — including the candidates that were rejected — are published in `docs/`.

Keywords: Indonesia stock screener, IDX, IHSG, bandarmologi, money flow, CMF, OBV, VSA, pullback strategy, entry stop-loss take-profit, swing trading, Telegram stock bot, backtest, FastAPI, React.

</details>
