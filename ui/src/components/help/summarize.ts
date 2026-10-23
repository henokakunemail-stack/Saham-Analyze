/**
 * Ringkasan bahasa awam dari payload analisis saham.
 *
 * Fungsi murni & deterministik (tanpa React / DOM) agar mudah diuji:
 * lihat summarize.check.ts. Bahasa sengaja hati-hati — ini membaca KONDISI,
 * bukan meramal harga (uji balik belum menunjukkan keunggulan prediktif skor).
 */
import type { StockAnalysis } from '../../types/stock';
import { fmtNum, fmtPct, fmtPrice, fmtSigned, fmtSignedInt } from './format';

export type SummaryTone = 'positive' | 'neutral' | 'cautious' | 'negative';

export interface PlainSummary {
  tone: SummaryTone;
  /** Judul singkat (3–6 kata). */
  headline: string;
  /** 1–2 kalimat kesimpulan. */
  conclusion: string;
  /** Yang mendukung (maks. 3). */
  supports: string[];
  /** Yang perlu diwaspadai (maks. 3). */
  risks: string[];
  /** Yang perlu ditunggu (maks. 3). */
  waitFor: string[];
}

/** Subset payload yang dibaca — semua opsional agar tahan payload lama/parsial. */
export type SummaryInput = {
  technical?: Partial<StockAnalysis['technical']>;
  money_flow?: Partial<StockAnalysis['money_flow']>;
  composite?: Partial<StockAnalysis['composite']>;
  direction?: Partial<NonNullable<StockAnalysis['direction']>> | null;
  market_regime?: Partial<NonNullable<StockAnalysis['market_regime']>> | null;
  financials?: Partial<NonNullable<StockAnalysis['financials']>> | null;
  sentiment?: Partial<StockAnalysis['sentiment']>;
};

/** Harga dianggap "terlalu jauh" dari EMA20 di atas ambang ini. */
export const STRETCH_PCT = 8;
export const STRETCH_ATR = 2.5;

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);

const MAX_ITEMS = 3;

export function summarizeAnalysis(a: SummaryInput): PlainSummary {
  const t = a.technical ?? {};
  const mf = a.money_flow ?? {};
  const c = a.composite ?? {};
  const d = a.direction ?? null;
  const fin = a.financials ?? null;

  const price = num(t.price);
  const ema20 = num(t.ema20);
  const ema50 = num(t.ema50);
  const ema200 = num(t.ema200);
  const atr = num(t.atr14);
  const rsi = num(t.rsi14);
  const macd = num(t.macd_hist);
  const volRatio = num(t.vol_ratio);
  const cmf = num(mf.cmf20);
  const flow = mf.money_flow_status ?? 'NEUTRAL';
  const vsa = mf.vsa_signal ?? 'NORMAL';
  const obv = mf.obv_divergence ?? 'NONE';
  const rr = num(c.risk_reward_ratio);
  const confluence = num(c.confluence_score);
  const gates = c.confluence_gates ?? {};
  const marketScore = num(a.market_regime?.direction_score);
  const marketLabel = a.market_regime?.direction_label;

  // Arah tren: pakai mesin arah; fallback ke pilar trend; fallback lagi ke tumpukan EMA.
  let dir = num(d?.direction_score);
  if (dir === undefined && num(c.pillars?.trend) !== undefined) dir = Math.round((c.pillars!.trend as number) * 100);
  if (dir === undefined && price !== undefined && ema20 !== undefined && ema50 !== undefined) {
    dir = price > ema20 && ema20 > ema50 ? 30 : price < ema20 && ema20 < ema50 ? -30 : 0;
  }
  const direction = dir ?? 0;
  const up = direction >= 20;
  const down = direction <= -20;
  const regime = d?.regime;
  const squeeze = Boolean(d?.squeeze) || regime === 'SQUEEZE';
  const confidence = num(d?.confidence);

  const inflow = flow === 'STRONG_INFLOW' || flow === 'MILD_INFLOW';
  const outflow = flow === 'STRONG_OUTFLOW' || flow === 'MILD_OUTFLOW';

  const isSpec = Boolean(c.is_speculative || fin?.is_speculative);
  const distressed = fin?.health_grade === 'DISTRESSED';
  const healthy = fin?.health_grade === 'HEALTHY' && !isSpec;

  const stretchPct = price !== undefined && ema20 ? ((price - ema20) / ema20) * 100 : undefined;
  const stretchAtr = price !== undefined && ema20 !== undefined && atr ? (price - ema20) / atr : undefined;
  // Setup pullback (scoring v4) — opsional, payload lama tidak punya.
  const pb = d?.pullback ?? null;
  const pbState: string | undefined = pb?.state ?? c.pullback_state;
  const pbIdeal = pbState === 'PULLBACK_IDEAL';
  const pbDeep = pbState === 'PULLBACK_DEEP';
  const pbExtended = pbState === 'UPTREND_EXTENDED';
  const pbNotSetup = pbState === 'TREND_BROKEN' || pbState === 'NO_UPTREND';
  const longMom = num(pb?.long_momentum_pct ?? undefined);
  const relMom = num(pb?.relative_momentum_pct ?? undefined);
  const support = num(pb?.support_level ?? undefined);
  const pbStretchAtr = num(pb?.stretch_atr);

  const stretched =
    pbExtended ||
    (stretchPct !== undefined && stretchPct >= STRETCH_PCT) ||
    ((pbStretchAtr ?? stretchAtr) !== undefined && (pbStretchAtr ?? stretchAtr)! >= STRETCH_ATR);
  const overbought = rsi !== undefined && rsi >= 75;
  // Mode pasar dari engine ('CRASH' sedang ditambahkan; dibaca sebagai string agar tahan perubahan tipe).
  const marketMode = (c.market_mode as string | undefined) ?? 'NORMAL';
  const marketCrash = marketMode === 'CRASH';
  const marketBearish = marketMode === 'BEARISH' || marketCrash;
  const marketCautious = marketMode === 'CAUTIOUS';
  const weakMarket = marketBearish || marketCautious || (marketScore !== undefined && marketScore <= -30);

  const swingHigh = num(d?.last_swing_high ?? undefined);
  const swingLow = num(d?.last_swing_low ?? undefined);
  const entryLow = num(t.entry_low) ?? num(c.entry_low);
  const entryHigh = num(t.entry_high) ?? num(c.entry_high);
  const stop = num(c.stop_loss);

  // ── Yang mendukung (urut berdasarkan bobot) ─────────────────────────────
  const supports: string[] = [];
  if (pbIdeal)
    supports.push(
      `Tren naik jangka panjang masih utuh; harga sedang terkoreksi wajar${support !== undefined ? ` dekat support ${fmtPrice(support)}` : ''}.`
    );
  if (longMom !== undefined && longMom >= 10) supports.push(`Momentum 6 bulan positif (${fmtPct(longMom, 1)}).`);
  if (relMom !== undefined && relMom >= 5) supports.push(`Lebih kuat dari indeks dalam 6 bulan (${fmtPct(relMom, 1)}).`);
  if (up) supports.push(`Tren cenderung naik (skor arah ${fmtSignedInt(direction)}).`);
  if (flow === 'STRONG_INFLOW') supports.push(`Indikasi akumulasi kuat (CMF ${fmtSigned(cmf)}).`);
  else if (inflow) supports.push(`Ada indikasi uang masuk (CMF ${fmtSigned(cmf)}).`);
  if (d?.break_of_structure === 'BULLISH_BOS') supports.push('Harga menembus swing high terakhir (break of structure naik).');
  if (d?.rsi_divergence === 'BULLISH') supports.push('Divergensi RSI bullish: tekanan jual mulai melemah.');
  if (vsa === 'ABSORPTION' || vsa === 'MARKUP') supports.push('Pola volume (VSA) menunjukkan permintaan kuat hari ini.');
  else if (vsa === 'NO_SUPPLY_TEST' && !down) supports.push('Volume jual mengering (VSA No Supply Test).');
  else if (vsa === 'SELLING_CLIMAX') supports.push('Aksi jual panik terserap (VSA Selling Climax) — kemungkinan dasar sementara.');
  if (obv === 'BULLISH_ACCUMULATION' && !inflow) supports.push('OBV naik walau harga belum naik (akumulasi diam-diam).');
  if (d?.weekly_trend?.startsWith('UPTREND')) supports.push('Tren mingguan juga naik.');
  if (num(d?.rs_20d_pct) !== undefined && (d!.rs_20d_pct as number) >= 2)
    supports.push(`Lebih kuat dari indeks (${fmtPct(d!.rs_20d_pct, 1)} dalam 20 hari).`);
  if (price !== undefined && ema200 !== undefined && price > ema200 && !up) supports.push('Harga masih di atas EMA200 (tren jangka panjang terjaga).');
  if (confluence !== undefined && confluence >= 4) supports.push(`${confluence} dari 6 gerbang konfluensi lolos.`);
  if (healthy) supports.push('Kondisi keuangan emiten sehat.');
  if (rr !== undefined && rr >= 2) supports.push(`Rasio risiko/imbal hasil menarik (1 : ${fmtNum(rr, 1)}).`);
  if (macd !== undefined && macd > 0 && up) supports.push('Momentum MACD positif.');

  // ── Yang perlu diwaspadai ───────────────────────────────────────────────
  const risks: string[] = [];
  if (marketBearish)
    risks.push(
      marketCrash
        ? 'Pasar dalam kondisi krisis (indeks turun ≥20% dalam 60 hari): mayoritas saham ikut tertekan.'
        : 'Pasar sedang bearish: mayoritas saham ikut tertekan, sinyal beli lebih sering gagal.'
    );
  if (pbState === 'TREND_BROKEN') risks.push('Tren naik sebelumnya sudah patah — bukan setup pullback.');
  if (pbDeep) risks.push('Koreksi sudah dalam; struktur tren naik mulai rawan.');
  if (longMom !== undefined && longMom <= -10) risks.push(`Momentum 6 bulan negatif (${fmtPct(longMom, 1)}).`);
  if (isSpec) risks.push('Saham spekulatif (rugi / utang tinggi): pergerakan sering tidak didukung kinerja.');
  else if (distressed) risks.push('Kinerja keuangan tertekan.');
  if (down) risks.push(`Tren sedang turun (skor arah ${fmtSignedInt(direction)}).`);
  if (flow === 'STRONG_OUTFLOW') risks.push(`Indikasi distribusi kuat / uang keluar (CMF ${fmtSigned(cmf)}).`);
  else if (outflow) risks.push(`Ada indikasi uang keluar (CMF ${fmtSigned(cmf)}).`);
  if (stretched && stretchPct !== undefined)
    risks.push(`Harga sudah ${fmtPct(stretchPct, 1)} di atas EMA20 — rawan koreksi.`);
  if (overbought) risks.push(`RSI ${fmtNum(rsi, 0)} (jenuh beli).`);
  if (d?.rsi_divergence === 'BEARISH') risks.push('Divergensi RSI bearish: dorongan naik melemah.');
  if (d?.break_of_structure === 'BEARISH_BOS') risks.push('Harga jebol swing low terakhir (break of structure turun).');
  if (vsa === 'BUYING_CLIMAX') risks.push('VSA Buying Climax: volume euforia tapi harga gagal bertahan di atas.');
  else if (vsa === 'EFFORT_NO_RESULT') risks.push('VSA Effort vs No Result: volume besar tanpa kemajuan harga.');
  else if (vsa === 'SELLING_PRESSURE') risks.push('VSA Selling Pressure: penjual mendominasi hari ini.');
  if (weakMarket && !marketBearish) risks.push(`Indeks sedang lemah${marketLabel ? ` (${marketLabel})` : ''}.`);
  if (rr !== undefined && rr < 1.4) risks.push(`Rasio risiko/imbal hasil kurang menarik (1 : ${fmtNum(rr, 1)}).`);
  if (price !== undefined && ema200 !== undefined && price < ema200 && !down) risks.push('Harga di bawah EMA200 (tren jangka panjang lemah).');
  if (d?.weekly_trend?.startsWith('DOWNTREND') && !down) risks.push('Tren mingguan masih turun.');
  if (confidence !== undefined && confidence < 40) risks.push(`Sinyal arah saling bertentangan (keyakinan ${confidence}%).`);

  // ── Yang perlu ditunggu ─────────────────────────────────────────────────
  const waitFor: string[] = [];
  if (marketBearish) waitFor.push('Indeks stabil terlebih dahulu (berhenti membuat titik terendah baru).');
  if (pbIdeal)
    waitFor.push('Pemicu pembalikan naik: MACD histogram berbalik naik atau candle pembalikan di dekat support.');
  if (pbDeep) waitFor.push(`Harga bertahan di atas support${support !== undefined ? ` ${fmtPrice(support)}` : ''} dan mulai berbalik naik.`);
  const zone =
    entryLow !== undefined && entryHigh !== undefined ? `${fmtPrice(entryLow)}–${fmtPrice(entryHigh)}` : undefined;
  if (down && outflow) {
    waitFor.push(`Tanda pembalikan: harga kembali di atas EMA20${ema20 !== undefined ? ` (~${fmtPrice(ema20)})` : ''} dan aliran dana berubah positif.`);
  } else if (down) {
    waitFor.push(
      swingHigh !== undefined
        ? `Harga menembus swing high terakhir (${fmtPrice(swingHigh)}) sebagai tanda awal pembalikan.`
        : 'Struktur harga berbalik (higher low lalu higher high).'
    );
  }
  if (up && stretched) {
    waitFor.push(`Pullback mendekati EMA20${ema20 !== undefined ? ` (~${fmtPrice(ema20)})` : ''}${zone ? ` atau zona entry ${zone}` : ''}.`);
  }
  if (up && !inflow) waitFor.push('Konfirmasi aliran dana (CMF positif) dan volume di atas rata-rata.');
  if (squeeze) waitFor.push('Arah keluar dari squeeze, idealnya disertai volume ≥ 1,3x.');
  if (!up && !down && !squeeze) {
    waitFor.push(
      swingHigh !== undefined
        ? `Arah yang jelas: breakout di atas ${fmtPrice(swingHigh)} dengan volume, atau tetap di luar.`
        : 'Arah yang jelas (breakout dengan volume) sebelum mengambil keputusan.'
    );
  }
  if (overbought && !stretched) waitFor.push('RSI turun kembali di bawah 70 (momentum mendingin).');
  if (weakMarket && !marketBearish) waitFor.push('Indeks pulih atau stabil terlebih dahulu.');
  if (rr !== undefined && rr < 1.4 && !stretched) waitFor.push('Harga lebih dekat ke zona entry agar rasio risiko/imbal hasil ≥ 1 : 1,4.');
  if (confluence !== undefined && confluence < 4 && up) {
    const failed = Object.entries(gates).filter(([, v]) => !v).length;
    waitFor.push(`Lebih banyak gerbang konfluensi lolos (saat ini ${confluence}/6${failed ? `, ${failed} belum` : ''}).`);
  }
  if (gates.gate_volume_expansion === false && up && volRatio !== undefined && volRatio < 1)
    waitFor.push('Volume meningkat (saat ini di bawah rata-rata).');
  if (waitFor.length === 0) {
    waitFor.push(
      stop !== undefined
        ? `Konfirmasi candle berikutnya; tetap disiplin pada batas risiko (stop loss ${fmtPrice(stop)}).`
        : 'Konfirmasi candle berikutnya dan tentukan batas risiko sebelum bertindak.'
    );
  }

  // ── Skenario utama → tone, judul, kesimpulan ────────────────────────────
  let tone: SummaryTone;
  let headline: string;
  let conclusion: string;

  if (pbIdeal && !isSpec && !distressed) {
    tone = 'cautious';
    headline = 'Diskon dalam tren naik';
    conclusion =
      'Harga sedang terkoreksi (diskon) di dalam tren naik yang masih utuh. Ini baru kondisi, belum pemicu — pantau pemicu seperti MACD berbalik naik sebelum mempertimbangkan.';
    if (outflow) conclusion += ' Aliran dana masih keluar, jadi tetap waspada.';
  } else if (pbDeep && !isSpec && !distressed) {
    tone = 'cautious';
    headline = 'Koreksi dalam di tren naik';
    conclusion = 'Tren naik masih ada, tetapi koreksinya sudah dalam dan strukturnya rawan patah. Tunggu harga stabil di atas support.';
  } else if (isSpec || distressed) {
    tone = 'negative';
    headline = 'Risiko fundamental tinggi';
    conclusion = `Emiten ${isSpec ? 'tergolong spekulatif (rugi / utang tinggi)' : 'sedang tertekan secara keuangan'}, sehingga sinyal teknikal kurang bisa diandalkan. Jika tetap dipantau, batasi ukuran posisi dan risiko.`;
  } else if (down && outflow) {
    tone = 'negative';
    headline = 'Tren turun, uang keluar';
    conclusion = 'Harga sedang dalam tren turun dan data volume menunjukkan uang keluar. Belum ada tanda pembalikan — tunggu tanda pembalikan sebelum mempertimbangkan.';
  } else if (down && (inflow || d?.rsi_divergence === 'BULLISH' || d?.break_of_structure === 'BULLISH_BOS')) {
    tone = 'cautious';
    headline = 'Tren turun, ada tanda awal';
    conclusion = 'Tren masih turun, tetapi muncul tanda awal akumulasi atau pelemahan tekanan jual. Ini belum konfirmasi pembalikan; tunggu struktur harga berbalik.';
  } else if (down) {
    tone = 'negative';
    headline = 'Tren turun';
    conclusion = 'Kondisi teknikal belum mendukung karena tren sedang turun. Tunggu tanda pembalikan sebelum mempertimbangkan.';
  } else if (up && (stretched || overbought)) {
    tone = 'cautious';
    headline = 'Tren naik, tapi rawan koreksi';
    conclusion = stretched
      ? `Tren naik, tetapi harga sudah jauh di atas EMA20 (${fmtPct(stretchPct, 1)}) — rawan koreksi, tunggu pullback daripada mengejar harga.`
      : `Tren naik, tetapi RSI sudah jenuh beli (${fmtNum(rsi, 0)}) — rawan koreksi, tunggu momentum mendingin.`;
  } else if (up && outflow) {
    tone = 'cautious';
    headline = 'Naik tanpa dukungan dana';
    conclusion = 'Harga cenderung naik, tetapi data volume menunjukkan uang keluar. Kenaikan kurang didukung; waspada distribusi.';
  } else if (up && inflow && (confluence ?? 0) >= 4) {
    tone = 'positive';
    headline = 'Kondisi teknikal mendukung';
    conclusion = 'Tren naik dengan indikasi uang masuk dan sebagian besar gerbang konfluensi lolos. Ini sinyal kondisi, bukan kepastian — tetap tentukan batas risiko.';
  } else if (up) {
    tone = 'positive';
    headline = 'Cenderung naik, konfirmasi belum lengkap';
    conclusion = `Tren cenderung naik, namun konfirmasi belum lengkap${confluence !== undefined ? ` (${confluence}/6 gerbang lolos)` : ''}. Sinyal masih awal.`;
  } else if (squeeze) {
    tone = 'neutral';
    headline = 'Volatilitas menyempit';
    conclusion = 'Harga bergerak sangat sempit (squeeze). Kondisi ini sering mendahului pergerakan besar, tetapi arahnya belum diketahui.';
  } else {
    tone = 'neutral';
    headline = 'Belum ada arah jelas';
    conclusion = 'Harga bergerak sideways tanpa arah dominan. Lebih aman menunggu arah yang jelas.';
  }

  if (pbNotSetup && !down) conclusion += ' Bukan setup pullback (tidak ada tren naik yang utuh).';

  if (marketBearish) {
    // Kondisi pasar mendahului apa pun kondisi sahamnya.
    const lead = marketCrash
      ? 'Pasar sedang krisis (IHSG turun tajam) — prioritas jaga modal.'
      : 'Pasar sedang bearish (indeks turun tajam) — prioritas jaga modal.';
    conclusion = `${lead} ${conclusion}`;
    headline = `${marketCrash ? 'Pasar krisis' : 'Pasar bearish'}: ${headline.charAt(0).toLowerCase()}${headline.slice(1)}`;
    if (tone === 'positive' || tone === 'neutral') tone = 'cautious';
  } else if (weakMarket && tone !== 'negative') {
    conclusion += ' Kondisi indeks sedang lemah, menambah risiko.';
    if (tone === 'positive') {
      tone = 'cautious';
      headline = `${headline}, tapi indeks lemah`;
    }
  }

  return {
    tone,
    headline,
    conclusion,
    supports: supports.slice(0, MAX_ITEMS),
    risks: risks.slice(0, MAX_ITEMS),
    waitFor: waitFor.slice(0, MAX_ITEMS),
  };
}

