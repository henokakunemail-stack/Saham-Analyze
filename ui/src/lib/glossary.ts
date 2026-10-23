/**
 * Glosarium istilah yang tampil di SAHAM (Bahasa Indonesia, untuk non-ahli).
 *
 * Setiap entri: apa itu, cara membaca, ambang umum, dan peringatan.
 * Ambang angka mengikuti logika engine (engine/screener/scoring.py,
 * engine/indicators/money_flow.py, engine/indicators/trend.py).
 */

export type GlossaryCategory =
  | 'Skor'
  | 'Arah Tren'
  | 'Momentum'
  | 'Aliran Dana'
  | 'Sinyal VSA'
  | 'Rencana Trading'
  | 'Gerbang Konfluensi'
  | 'Fundamental';

export interface GlossaryEntry {
  key: string;
  term: string;
  category: GlossaryCategory;
  /** Apa itu (1 kalimat). */
  what: string;
  /** Cara membaca. */
  read: string;
  /** Ambang / nilai umum. */
  thresholds?: string;
  /** Peringatan / keterbatasan. */
  caution?: string;
  /** Kata kunci tambahan untuk pencarian. */
  aliases?: string[];
}

const E = (e: GlossaryEntry): GlossaryEntry => e;

const ENTRIES: GlossaryEntry[] = [
  // ── Skor ────────────────────────────────────────────────────────────────
  E({
    key: 'composite_score',
    term: 'Skor Komposit (0–100)',
    category: 'Skor',
    what: 'Ringkasan berbobot dari pilar-pilar: pullback, tren, aliran uang, momentum, setup, fundamental, sentimen — lalu diredam bila pasar sedang lemah.',
    read: '50 = netral. Di atas 50 kondisi cenderung mendukung, di bawah 50 cenderung menekan.',
    thresholds: '≥80 potensi tinggi · 65–79 sinyal awal · 45–64 konsolidasi · 30–44 tekanan jual · <30 distribusi. Saham spekulatif dibatasi maks. 60.',
    caution: 'Skor menggambarkan kondisi saat ini, bukan ramalan. Uji balik (backtest) belum membuktikan skor ini mampu memprediksi kenaikan 10 hari ke depan.',
    aliases: ['skor potensi', 'score', 'verdict'],
  }),
  E({
    key: 'verdict',
    term: 'Verdict / Label Sinyal',
    category: 'Skor',
    what: 'Label teks dari skor komposit (mis. "Sinyal Naik Awal", "Konsolidasi").',
    read: 'Hanya terjemahan rentang skor ke kata-kata; tidak menambah informasi baru.',
    caution: 'Bukan rekomendasi beli/jual.',
    aliases: ['badge', 'kesimpulan'],
  }),
  E({
    key: 'pillar_pullback',
    term: 'Pilar Pullback (Diskon dalam Tren Naik)',
    category: 'Skor',
    what: 'Menilai apakah saham dengan tren naik jangka panjang sedang terkoreksi ke area yang wajar. Bobot terbesar dalam skor (0,35).',
    read: 'Positif = koreksi sehat di tren naik yang utuh. Negatif = tren patah, tidak ada tren naik, atau harga sudah terlalu jauh di atas rata-rata.',
    caution: 'Pullback bisa berlanjut menjadi penurunan; tunggu pemicu pembalikan.',
    aliases: ['pullback'],
  }),
  E({
    key: 'market_mode',
    term: 'Mode Pasar',
    category: 'Skor',
    what: 'Kondisi indeks acuan (IHSG / S&P 500) yang dipakai untuk meredam skor saham.',
    read: 'NORMAL = tidak ada penyesuaian. CAUTIOUS = indeks melemah, skor diredam. BEARISH = indeks turun tajam. CRASH = indeks turun ≥20% dalam 60 hari.',
    caution: 'Saat BEARISH/CRASH sebagian besar saham ikut turun, termasuk yang skornya bagus — prioritaskan menjaga modal.',
    aliases: ['market mode', 'bearish', 'crash', 'krisis', 'cautious', 'ihsg'],
  }),
  E({
    key: 'pillar_trend',
    term: 'Pilar Tren',
    category: 'Skor',
    what: 'Seberapa jelas dan searah tren harga (EMA, ADX, struktur swing, tren mingguan).',
    read: 'Skala −1 s/d +1. Positif = tren naik, negatif = tren turun. Bobot terbesar dalam skor.',
    thresholds: '≥ +0,5 tren naik kuat · ≤ −0,5 tren turun kuat (skor dibatasi maks. 55).',
    aliases: ['trend'],
  }),
  E({
    key: 'pillar_money_flow',
    term: 'Pilar Aliran Uang',
    category: 'Skor',
    what: 'Indikasi uang masuk/keluar dari CMF, OBV dan pola volume (VSA).',
    read: 'Positif = dominan akumulasi, negatif = dominan distribusi.',
    caution: 'Berbasis data harga & volume harian, bukan data transaksi broker sebenarnya.',
    aliases: ['money_flow', 'aliran dana'],
  }),
  E({
    key: 'pillar_momentum',
    term: 'Pilar Momentum',
    category: 'Skor',
    what: 'Kekuatan dorongan harga terkini (RSI, MACD, divergensi RSI).',
    read: 'Positif = dorongan naik sehat; negatif = melemah atau jenuh.',
    aliases: ['momentum'],
  }),
  E({
    key: 'pillar_setup',
    term: 'Pilar Kualitas Setup',
    category: 'Skor',
    what: 'Seberapa "rapi" titik masuk: jarak ke support/EMA, pola candle, squeeze, rasio risiko/imbal hasil.',
    read: 'Positif = posisi harga relatif menguntungkan untuk masuk; negatif = terlalu jauh / R:R buruk.',
    aliases: ['setup'],
  }),
  E({
    key: 'pillar_fundamental',
    term: 'Pilar Fundamental',
    category: 'Skor',
    what: 'Kesehatan keuangan emiten (laba, ROE, utang).',
    read: 'Sehat ≈ +0,7 · Stabil ≈ +0,1 · Tertekan ≈ −0,8.',
    caution: 'Data fundamental bisa terlambat beberapa bulan dari laporan terbaru.',
    aliases: ['fundamental'],
  }),
  E({
    key: 'pillar_sentiment',
    term: 'Pilar Sentimen',
    category: 'Skor',
    what: 'Nada berita terbaru tentang saham ini (positif/negatif).',
    read: 'Positif = berita cenderung baik. Kosong jika tidak ada berita.',
    caution: 'Analisis teks otomatis bisa salah membaca konteks; cek berita aslinya.',
    aliases: ['sentiment', 'berita'],
  }),

  // ── Arah Tren ───────────────────────────────────────────────────────────
  E({
    key: 'direction_score',
    term: 'Skor Arah Tren (−100 s/d +100)',
    category: 'Arah Tren',
    what: 'Gabungan 7 komponen arah: struktur EMA, ADX/DMI, regresi linear, struktur swing, momentum, tren mingguan, kekuatan vs indeks.',
    read: 'Positif = arah naik, negatif = arah turun, dekat 0 = belum ada arah.',
    thresholds: '≥ +50 uptrend kuat · +20..+49 cenderung naik · −19..+19 sideways · −20..−49 cenderung turun · ≤ −50 downtrend kuat.',
    caution: 'Menggambarkan arah yang sudah terjadi; tren bisa berbalik kapan saja.',
    aliases: ['arah tren', 'direction'],
  }),
  E({
    key: 'regime',
    term: 'Regime Pasar',
    category: 'Arah Tren',
    what: 'Jenis kondisi harga saat ini: trending naik, trending turun, sideways, atau squeeze.',
    read: 'Trending = ADX ≥ 20 dan arah jelas. Sideways = tidak ada arah dominan. Squeeze = volatilitas sangat sempit.',
    caution: 'Strategi yang cocok untuk tren sering gagal saat sideways, dan sebaliknya.',
    aliases: ['ranging', 'trending'],
  }),
  E({
    key: 'confidence',
    term: 'Keyakinan Arah',
    category: 'Arah Tren',
    what: 'Seberapa kompak komponen arah menunjuk ke arah yang sama, ditambah kekuatan tren (ADX).',
    read: '0–100%. Tinggi = komponen sepakat; rendah = sinyal saling bertentangan.',
    thresholds: '<40% lemah · 40–65% sedang · >65% kompak.',
    caution: 'Bukan peluang keberhasilan. 80% tidak berarti 80% kemungkinan naik.',
    aliases: ['keyakinan'],
  }),
  E({
    key: 'adx',
    term: 'ADX (+DI / −DI)',
    category: 'Arah Tren',
    what: 'ADX mengukur KEKUATAN tren (bukan arahnya). +DI dan −DI menunjukkan sisi mana yang dominan.',
    read: '+DI > −DI = pembeli dominan; −DI > +DI = penjual dominan. ADX naik = tren menguat.',
    thresholds: 'ADX <20 tren lemah · 20–25 moderat · ≥25 tren kuat.',
    caution: 'ADX tinggi pada tren turun berarti tren TURUN kuat.',
    aliases: ['dmi', 'di', 'plus_di', 'minus_di'],
  }),
  E({
    key: 'market_structure',
    term: 'Struktur Swing',
    category: 'Arah Tren',
    what: 'Pola puncak (swing high) dan lembah (swing low) terakhir.',
    read: 'Higher High & Higher Low = struktur naik. Lower High & Lower Low = struktur turun.',
    aliases: ['swing', 'higher high', 'lower low', 'hh', 'hl'],
  }),
  E({
    key: 'break_of_structure',
    term: 'Break of Structure (BOS)',
    category: 'Arah Tren',
    what: 'Harga menembus swing high terakhir (BOS bullish) atau jebol swing low terakhir (BOS bearish).',
    read: 'BOS bullish = tanda awal kekuatan/pembalikan naik. BOS bearish = tanda kelemahan.',
    caution: 'Tembusan bisa palsu (false break); lebih kuat bila disertai volume tinggi.',
    aliases: ['bos', 'bullish_bos', 'bearish_bos'],
  }),
  E({
    key: 'weekly_trend',
    term: 'Tren Mingguan',
    category: 'Arah Tren',
    what: 'Arah tren di grafik mingguan (EMA10 vs EMA20 mingguan dan kemiringannya).',
    read: 'Uptrend mingguan memberi "angin dari belakang" bagi sinyal harian; downtrend mingguan sebaliknya.',
    aliases: ['mingguan', 'weekly'],
  }),
  E({
    key: 'relative_strength',
    term: 'Kekuatan Relatif vs Indeks',
    category: 'Arah Tren',
    what: 'Selisih kinerja saham dibanding indeks (IHSG / S&P 500) dalam 20 dan 60 hari.',
    read: 'Positif = saham lebih kuat dari pasar; negatif = tertinggal.',
    thresholds: '±2% kecil · >+8% jauh lebih kuat dari indeks.',
    aliases: ['rs', 'relative strength'],
  }),
  E({
    key: 'linear_regression',
    term: 'Regresi Linear',
    category: 'Arah Tren',
    what: 'Kemiringan garis lurus terbaik yang melewati harga beberapa minggu terakhir.',
    read: 'Positif = kemiringan naik; makin konsisten harga di sekitar garis, makin kuat.',
    aliases: ['regression'],
  }),
  E({
    key: 'market_regime',
    term: 'Kondisi Indeks',
    category: 'Arah Tren',
    what: 'Skor arah tren yang sama, dihitung untuk indeks acuan (IHSG atau S&P 500).',
    read: 'Saat indeks turun (≤ −30), skor bullish saham diredam karena mayoritas saham ikut tertekan.',
    aliases: ['ihsg', 'indeks', 'market'],
  }),
  E({
    key: 'pullback',
    term: 'Status Pullback',
    category: 'Arah Tren',
    what: 'Posisi harga terhadap tren naik jangka panjangnya.',
    read: 'Pullback ideal = terkoreksi wajar, struktur utuh · Pullback dalam = koreksi besar, struktur rawan · Uptrend berjalan = naik normal · Uptrend terlalu jauh = jauh di atas EMA20, tunggu koreksi · Tren patah / tidak ada uptrend = bukan setup pullback.',
    thresholds: 'Jarak ke EMA20 diukur dalam ATR: ≥ ~2,5 ATR dianggap terlalu jauh.',
    caution: '"Diskon" bukan berarti murah secara fundamental; harga bisa terus turun. Tunggu pemicu (mis. MACD berbalik naik).',
    aliases: ['pullback_ideal', 'pullback_deep', 'uptrend_extended', 'trend_broken', 'diskon', 'koreksi', 'support'],
  }),
  E({
    key: 'long_momentum',
    term: 'Momentum 6 Bulan',
    category: 'Arah Tren',
    what: 'Imbal hasil harga ~6 bulan terakhir, tidak menghitung 1 bulan terakhir.',
    read: 'Positif besar = tren naik jangka menengah kuat. Bulan terakhir dilewati agar koreksi jangka pendek tidak mengaburkan tren.',
    thresholds: '≥ +10% kuat · ≤ −10% lemah.',
    caution: 'Momentum masa lalu bisa berbalik, terutama saat pasar krisis.',
    aliases: ['long momentum', 'momentum panjang', 'long_momentum_pct', '6 bulan'],
  }),
  E({
    key: 'relative_momentum',
    term: 'Momentum Relatif vs Indeks',
    category: 'Arah Tren',
    what: 'Momentum 6 bulan saham dikurangi momentum 6 bulan indeks.',
    read: 'Positif = saham lebih kuat dari pasar secara umum.',
    caution: 'Saham yang "lebih kuat" tetap bisa turun bila seluruh pasar jatuh.',
    aliases: ['relative momentum', 'relative_momentum_pct'],
  }),
  E({
    key: 'squeeze',
    term: 'Squeeze (Volatilitas Menyempit)',
    category: 'Arah Tren',
    what: 'Lebar Bollinger Band berada di 20% tersempit dalam ~120 hari.',
    read: 'Harga "diam" dan sering diikuti pergerakan besar.',
    caution: 'Squeeze TIDAK memberi tahu arah ledakan — bisa naik atau turun.',
    aliases: ['bollinger', 'volatilitas'],
  }),

  // ── Momentum ────────────────────────────────────────────────────────────
  E({
    key: 'rsi',
    term: 'RSI (14)',
    category: 'Momentum',
    what: 'Relative Strength Index: kecepatan kenaikan vs penurunan harga 14 hari terakhir.',
    read: 'Skala 0–100. Area 45–65 = momentum sehat untuk tren naik.',
    thresholds: '>70 jenuh beli (overbought) · <30 jenuh jual (oversold).',
    caution: 'Dalam tren kuat RSI bisa bertahan di atas 70 cukup lama; oversold tidak otomatis berarti akan naik.',
    aliases: ['relative strength index', 'overbought', 'oversold'],
  }),
  E({
    key: 'rsi_divergence',
    term: 'Divergensi RSI',
    category: 'Momentum',
    what: 'Harga dan RSI bergerak berlawanan arah di dua swing terakhir.',
    read: 'Bullish: harga lower low tapi RSI higher low (tekanan jual melemah). Bearish: harga higher high tapi RSI lower high (dorongan naik melemah).',
    caution: 'Hanya peringatan dini; perlu konfirmasi (mis. BOS atau candle pembalikan).',
    aliases: ['divergence', 'divergensi'],
  }),
  E({
    key: 'macd',
    term: 'MACD Histogram',
    category: 'Momentum',
    what: 'Selisih garis MACD dan garis sinyalnya; mengukur percepatan momentum.',
    read: 'Positif & membesar = momentum naik menguat. Negatif = momentum turun.',
    caution: 'Indikator lagging (terlambat); sering berbalik setelah harga sudah bergerak.',
    aliases: ['macd_hist'],
  }),
  E({
    key: 'ema',
    term: 'EMA 20 / 50 / 200',
    category: 'Momentum',
    what: 'Rata-rata harga eksponensial 20, 50 dan 200 hari (jangka pendek, menengah, panjang).',
    read: 'Harga > EMA20 > EMA50 > EMA200 = struktur naik rapi. Harga di bawah EMA200 = tren jangka panjang lemah.',
    thresholds: 'Harga >8% di atas EMA20 = sudah "jauh dari rata-rata", rawan koreksi.',
    caution: 'EMA juga sering menjadi area support/resistance, bukan jaminan pantulan.',
    aliases: ['ema20', 'ema50', 'ema200', 'moving average', 'rata-rata'],
  }),
  E({
    key: 'breakout_20d',
    term: 'Breakout 20 Hari',
    category: 'Momentum',
    what: 'Harga penutupan menembus harga tertinggi 20 hari terakhir.',
    read: 'Tanda kekuatan jangka pendek bila disertai volume.',
    caution: 'Breakout tanpa volume lebih sering gagal (false breakout).',
    aliases: ['breakout'],
  }),
  E({
    key: 'candlestick',
    term: 'Pola Candlestick',
    category: 'Momentum',
    what: 'Pola 1–3 lilin terakhir (mis. hammer, engulfing) yang dikenali otomatis.',
    read: 'Reliabilitas HIGH lebih bisa dipercaya daripada LOW. Paling bermakna di area support/resistance.',
    caution: 'Pola tunggal punya akurasi terbatas; gunakan sebagai konfirmasi saja.',
    aliases: ['candle', 'lilin'],
  }),

  // ── Aliran Dana ─────────────────────────────────────────────────────────
  E({
    key: 'cmf',
    term: 'CMF (Chaikin Money Flow 20)',
    category: 'Aliran Dana',
    what: 'Mengukur apakah volume 20 hari terakhir lebih banyak terjadi saat harga ditutup dekat puncak (beli) atau dekat dasar (jual).',
    read: 'Positif = tekanan beli/akumulasi; negatif = tekanan jual/distribusi; 0 = netral.',
    thresholds: '≥ +0,04 akumulasi · ≥ +0,15 akumulasi kuat · ≤ −0,04 distribusi · ≤ −0,12 distribusi kuat.',
    caution: 'Perkiraan dari harga & volume, bukan data siapa yang membeli.',
    aliases: ['chaikin', 'cmf20', 'money flow'],
  }),
  E({
    key: 'obv_divergence',
    term: 'Divergensi OBV',
    category: 'Aliran Dana',
    what: 'On-Balance Volume (volume kumulatif naik/turun) dibandingkan dengan arah harga.',
    read: 'BULLISH_ACCUMULATION: OBV naik saat harga datar/turun (diam-diam dikumpulkan). BEARISH_DISTRIBUTION: OBV turun saat harga naik/datar. NONE: searah.',
    aliases: ['obv', 'on balance volume', 'BULLISH_ACCUMULATION', 'BEARISH_DISTRIBUTION'],
  }),
  E({
    key: 'money_flow_status',
    term: 'Status Aliran Dana',
    category: 'Aliran Dana',
    what: 'Kesimpulan gabungan CMF, OBV dan VSA: akumulasi masif, akumulasi, netral, distribusi, distribusi masif.',
    read: 'Akumulasi = indikasi uang masuk; distribusi = indikasi uang keluar.',
    caution: 'Indikasi statistik, bukan bukti bandar/institusi membeli.',
    aliases: ['inflow', 'outflow', 'akumulasi', 'distribusi'],
  }),
  E({
    key: 'mfs_STRONG_INFLOW',
    term: 'Akumulasi Masif (STRONG_INFLOW)',
    category: 'Aliran Dana',
    what: 'CMF ≥ 0,15, atau CMF ≥ 0,08 + divergensi OBV bullish, atau VSA Absorption/Markup.',
    read: 'Tekanan beli kuat dalam data harga-volume.',
    caution: 'Di puncak tren, volume besar juga bisa menandai distribusi; lihat konteks.',
  }),
  E({
    key: 'mfs_MILD_INFLOW',
    term: 'Akumulasi (MILD_INFLOW)',
    category: 'Aliran Dana',
    what: 'CMF ≥ 0,04, atau divergensi OBV bullish, atau VSA No Supply Test.',
    read: 'Ada tanda uang masuk ringan.',
  }),
  E({
    key: 'mfs_NEUTRAL',
    term: 'Netral (NEUTRAL)',
    category: 'Aliran Dana',
    what: 'Tidak ada dominasi beli atau jual yang jelas.',
    read: 'CMF di antara −0,04 dan +0,04 tanpa sinyal VSA/OBV kuat.',
  }),
  E({
    key: 'mfs_MILD_OUTFLOW',
    term: 'Distribusi (MILD_OUTFLOW)',
    category: 'Aliran Dana',
    what: 'CMF ≤ −0,04 atau divergensi OBV bearish.',
    read: 'Ada tanda uang keluar ringan.',
  }),
  E({
    key: 'mfs_STRONG_OUTFLOW',
    term: 'Distribusi Masif (STRONG_OUTFLOW)',
    category: 'Aliran Dana',
    what: 'CMF ≤ −0,12, atau CMF ≤ −0,05 + OBV bearish, atau VSA Buying Climax/Selling Pressure.',
    read: 'Tekanan jual kuat; kenaikan harga cenderung kurang didukung.',
  }),
  E({
    key: 'vol_ratio',
    term: 'Rasio Volume (Vol Ratio)',
    category: 'Aliran Dana',
    what: 'Volume hari ini dibagi rata-rata volume 20 hari.',
    read: '1,0x = normal. Di atas 1 = lebih ramai dari biasanya.',
    thresholds: '≥1,3x ekspansi volume · ≥1,5x lonjakan · ≤0,75x volume kering.',
    caution: 'Lonjakan volume bisa terjadi saat beli maupun jual besar.',
    aliases: ['volume', 'volume spike'],
  }),

  // ── VSA ─────────────────────────────────────────────────────────────────
  E({
    key: 'vsa',
    term: 'VSA (Volume Spread Analysis)',
    category: 'Sinyal VSA',
    what: 'Membaca hubungan volume, rentang lilin (spread) dan posisi penutupan pada lilin terakhir.',
    read: 'Dipakai untuk menebak apakah pelaku besar sedang menyerap atau melepas saham.',
    caution: 'Hanya lilin terakhir yang dibaca; satu sinyal VSA saja tidak cukup untuk keputusan.',
    aliases: ['volume spread analysis', 'vsa_signal'],
  }),
  E({
    key: 'vsa_NORMAL',
    term: 'VSA: Normal',
    category: 'Sinyal VSA',
    what: 'Volume dan rentang harga seimbang.',
    read: 'Tidak ada pesan khusus dari volume hari ini.',
  }),
  E({
    key: 'vsa_NO_SUPPLY_TEST',
    term: 'VSA: No Supply Test',
    category: 'Sinyal VSA',
    what: 'Volume ≤0,75x rata-rata dan rentang lilin sempit.',
    read: 'Penjual tampak sepi; bisa menjadi dasar kenaikan bila tren mendukung.',
    caution: 'Di tren turun, volume kering juga bisa berarti pembeli tidak tertarik.',
  }),
  E({
    key: 'vsa_LOCKED',
    term: 'VSA: Harga Terkunci',
    category: 'Sinyal VSA',
    what: 'Seharian hanya satu harga (tertinggi = terendah), mis. saat ARA/ARB atau transaksi sangat sepi.',
    read: 'Volume dan rentang hari itu tidak dibaca sebagai sinyal beli maupun jual.',
  }),
  E({
    key: 'vsa_EFFORT_NO_RESULT',
    term: 'VSA: Effort vs No Result',
    category: 'Sinyal VSA',
    what: 'Volume ≥1,7x tetapi rentang lilin sempit.',
    read: 'Banyak transaksi tapi harga tidak bergerak — ada yang menahan; waspada pembalikan arah.',
  }),
  E({
    key: 'vsa_BUYING_CLIMAX',
    term: 'VSA: Buying Climax',
    category: 'Sinyal VSA',
    what: 'Lilin naik dengan volume ≥1,9x tapi ditutup di bawah tengah lilin.',
    read: 'Euforia beli namun harga gagal bertahan di atas — indikasi distribusi di pucuk.',
  }),
  E({
    key: 'vsa_SELLING_CLIMAX',
    term: 'VSA: Selling Climax',
    category: 'Sinyal VSA',
    what: 'Lilin turun dengan volume ≥1,8x tetapi ditutup di atas tengah lilin.',
    read: 'Aksi jual panik diserap pembeli; kadang menandai dasar sementara.',
    caution: 'Butuh konfirmasi beberapa hari; dasar bisa diuji ulang.',
  }),
  E({
    key: 'vsa_ABSORPTION',
    term: 'VSA: Absorption',
    category: 'Sinyal VSA',
    what: 'Volume ≥1,35x, rentang normal, ditutup di atas tengah lilin.',
    read: 'Antrian jual diserap — tanda permintaan kuat.',
  }),
  E({
    key: 'vsa_MARKUP',
    term: 'VSA: Markup',
    category: 'Sinyal VSA',
    what: 'Volume ≥1,3x, rentang lebar, ditutup dekat puncak.',
    read: 'Harga didorong naik dengan dukungan volume.',
    caution: 'Setelah markup besar, harga sering butuh istirahat (pullback).',
  }),
  E({
    key: 'vsa_SELLING_PRESSURE',
    term: 'VSA: Selling Pressure',
    category: 'Sinyal VSA',
    what: 'Volume ≥1,3x dan ditutup dekat dasar lilin.',
    read: 'Penjual mendominasi hari ini.',
  }),

  // ── Rencana Trading ─────────────────────────────────────────────────────
  E({
    key: 'atr',
    term: 'ATR (14)',
    category: 'Rencana Trading',
    what: 'Average True Range: rata-rata rentang gerak harga harian 14 hari.',
    read: 'Ukuran "kebisingan" normal saham. Dipakai untuk menentukan jarak stop loss dan target.',
    caution: 'Stop loss yang lebih sempit dari ~1 ATR mudah tersentuh oleh gerak acak biasa.',
    aliases: ['average true range', 'volatilitas'],
  }),
  E({
    key: 'entry_zone',
    term: 'Zona Entry',
    category: 'Rencana Trading',
    what: 'Rentang harga yang dihitung engine sebagai area masuk yang relatif wajar (berbasis EMA/ATR/support).',
    read: 'Harga di dalam zona = posisi risiko lebih terukur; jauh di atas zona = mengejar harga.',
    caution: 'Perhitungan mekanis; bukan saran untuk membeli.',
    aliases: ['entry', 'rekomendasi entry', 'area beli'],
  }),
  E({
    key: 'action_status',
    term: 'Status LAYAK / TUNGGU / HINDARI',
    category: 'Rencana Trading',
    what: 'Keputusan eksekusi: LAYAK bila semua syarat lolos (vonis beli, risiko ≤ 6%, likuid ≥ Rp2 M/hari, tidak terlalu volatil, pasar tidak krisis, tanpa ARB/suspensi baru).',
    read: 'LAYAK = boleh pasang order beli limit sesuai rencana. TUNGGU = pantau dulu, ada syarat yang belum lolos. HINDARI = jangan beli.',
    caution: 'Dari uji historis 2024–2026: LAYAK rata-rata sedikit lebih baik dari TUNGGU dan HINDARI, tetapi setelah biaya transaksi kira-kira impas. Bukan jaminan untung.',
    aliases: ['layak', 'tunggu', 'hindari', 'status'],
  }),
  E({
    key: 'buy_limit',
    term: 'Harga Beli (Limit)',
    category: 'Rencana Trading',
    what: 'Harga yang dipasang sebagai order beli limit di aplikasi broker — di tengah zona beli, di dekat support.',
    read: 'Order hanya terisi bila harga turun ke angka ini. Tidak terisi = tidak ada transaksi, dan itu tidak apa-apa.',
    caution: 'Jangan membeli di harga pasar bila harga sedang jauh di atas angka ini (mengejar). Uji historis aplikasi ini juga mengasumsikan order limit di harga ini.',
    aliases: ['harga saran', 'limit', 'recommended entry', 'harga beli'],
  }),
  E({
    key: 'stop_loss',
    term: 'Stop Loss / Cut Loss',
    category: 'Rencana Trading',
    what: 'Batas harga untuk keluar bila analisis ternyata salah.',
    read: 'Jarak entry ke stop loss = risiko per lembar yang Anda tanggung.',
    caution: 'Harga bisa gap melewati stop loss; kerugian bisa lebih besar dari rencana.',
    aliases: ['cut loss', 'sl', 'cl'],
  }),
  E({
    key: 'take_profit',
    term: 'Take Profit (TP1 / TP2)',
    category: 'Rencana Trading',
    what: 'Target harga hasil perhitungan: TP1 = resistance terdekat di atas harga beli, TP2 = resistance berikutnya.',
    read: 'Aturan aplikasi: di TP1 jual separuh dan naikkan cut loss ke harga beli; sisanya incar TP2.',
    caution: 'Target adalah skenario, bukan perkiraan pasti; harga mungkin tidak pernah mencapainya.',
    aliases: ['tp', 'tp1', 'tp2', 'target'],
  }),
  E({
    key: 'risk_reward',
    term: 'Rugi : Untung (R:R)',
    category: 'Rencana Trading',
    what: 'Perbandingan potensi rugi (harga beli ke cut loss) terhadap potensi untung (harga beli ke TP1).',
    read: '1 : 2 artinya potensi untung 2x lebih besar dari potensi rugi. 1 : 0,5 artinya untungnya hanya separuh risikonya.',
    thresholds: '< 1 : 1,2 ruang naik sempit · ≥ 1 : 2 baik.',
    caution: 'R:R tinggi tidak ada artinya bila peluang mencapai target kecil.',
    aliases: ['rr', 'risk reward', 'imbal hasil'],
  }),
  E({
    key: 'confluence',
    term: 'Gerbang Konfluensi (x/6)',
    category: 'Gerbang Konfluensi',
    what: 'Daftar 6 syarat yang dicek bersamaan: smart money, volume, searah tren, breakout, R:R, kesehatan finansial.',
    read: 'Makin banyak yang lolos, makin banyak faktor yang searah. "Confirmed breakout" butuh ≥4 lolos DAN searah tren.',
    caution: 'Lolos semua gerbang tetap bukan jaminan; gerbang dihitung dari data hari ini saja.',
    aliases: ['konfluensi', 'gate', 'confirmed breakout'],
  }),
  E({
    key: 'gate_smart_money',
    term: 'Gerbang: Smart Money',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila CMF ≥ 0,04 dan status aliran dana akumulasi.',
    read: 'Memastikan ada indikasi uang masuk.',
  }),
  E({
    key: 'gate_volume_expansion',
    term: 'Gerbang: Ekspansi Volume',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila volume hari ini ≥1,3x rata-rata 20 hari.',
    read: 'Pergerakan didukung partisipasi pasar.',
  }),
  E({
    key: 'gate_trend_alignment',
    term: 'Gerbang: Searah Tren',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila skor arah tren ≥ +20 dan harga di atas EMA20.',
    read: 'Wajib lolos agar setup bisa disebut "terkonfirmasi" — melawan tren lebih berisiko.',
  }),
  E({
    key: 'gate_resistance_breakout',
    term: 'Gerbang: Breakout / Penyerapan',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila breakout 20 hari, atau VSA Absorption / Markup / No Supply Test.',
    read: 'Ada pemicu harga, bukan hanya kondisi diam.',
  }),
  E({
    key: 'gate_risk_reward',
    term: 'Gerbang: Risk/Reward',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila rasio R:R ≥ 1 : 1,4.',
    read: 'Potensi untung sepadan dengan risikonya.',
  }),
  E({
    key: 'gate_financial_health',
    term: 'Gerbang: Kesehatan Finansial',
    category: 'Gerbang Konfluensi',
    what: 'Lolos bila emiten tidak tertekan dan tidak spekulatif.',
    read: 'Menyaring saham rugi/utang tinggi.',
  }),

  // ── Fundamental ─────────────────────────────────────────────────────────
  E({
    key: 'health_grade',
    term: 'Grade Kesehatan Finansial',
    category: 'Fundamental',
    what: 'Penilaian ringkas laporan keuangan: HEALTHY (sehat), MODERATE (stabil), DISTRESSED (tertekan).',
    read: 'Skor 0–100 dari ROE, margin laba, dan rasio utang (DER).',
    caution: 'Tidak menilai valuasi murah/mahal dan bisa tertinggal dari laporan terbaru.',
    aliases: ['healthy', 'moderate', 'distressed', 'kesehatan', 'roe', 'der'],
  }),
  E({
    key: 'speculative',
    term: 'Saham Spekulatif',
    category: 'Fundamental',
    what: 'Emiten merugi dan/atau berutang sangat tinggi ("gorengan").',
    read: 'Skor komposit dibatasi maksimal 60; pergerakan harga sering didorong spekulasi, bukan kinerja.',
    caution: 'Risiko tinggi: volatil, rawan turun tajam, likuiditas bisa hilang mendadak.',
    aliases: ['gorengan', 'spekulatif', 'is_speculative'],
  }),
];

export const GLOSSARY: Record<string, GlossaryEntry> = Object.fromEntries(ENTRIES.map((e) => [e.key, e]));

export const GLOSSARY_CATEGORIES: GlossaryCategory[] = [
  'Skor',
  'Arah Tren',
  'Momentum',
  'Aliran Dana',
  'Sinyal VSA',
  'Rencana Trading',
  'Gerbang Konfluensi',
  'Fundamental',
];

export const getTerm = (key: string): GlossaryEntry | undefined => GLOSSARY[key];

/** Key pilar skor → key glosarium. */
export const pillarTermKey = (pillar: string) => `pillar_${pillar}`;

/** Komponen arah tren → key glosarium. */
export const DIRECTION_COMPONENT_TERM: Record<string, string> = {
  ema_structure: 'ema',
  adx_dmi: 'adx',
  regression: 'linear_regression',
  market_structure: 'market_structure',
  momentum: 'pillar_momentum',
  weekly: 'weekly_trend',
  relative_strength: 'relative_strength',
};

/** Label Indonesia untuk setiap gerbang konfluensi. */
export const GATE_LABELS: Record<string, string> = {
  gate_smart_money: 'Smart Money',
  gate_volume_expansion: 'Ekspansi Volume',
  gate_trend_alignment: 'Searah Tren',
  gate_resistance_breakout: 'Breakout / Penyerapan',
  gate_risk_reward: 'Risk/Reward ≥ 1,4',
  gate_financial_health: 'Kesehatan Finansial',
};

/** Pencarian sederhana (tanpa beda huruf besar/kecil) di judul, isi dan alias. */
export function searchGlossary(query: string): GlossaryEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return ENTRIES;
  return ENTRIES.filter((e) =>
    [e.key, e.term, e.what, e.read, e.thresholds ?? '', e.caution ?? '', ...(e.aliases ?? [])]
      .join(' ')
      .toLowerCase()
      .includes(q)
  );
}
