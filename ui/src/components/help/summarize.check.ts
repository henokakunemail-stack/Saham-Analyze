/**
 * Self-check untuk summarizeAnalysis (tanpa dependency test tambahan).
 *
 * Jalankan dari folder ui/:
 *   npx esbuild src/components/help/summarize.check.ts --bundle --platform=node --outfile=<tmp>/check.mjs --format=esm
 *   node <tmp>/check.mjs
 * Gagal → melempar Error (exit code ≠ 0).
 */
import { summarizeAnalysis, SummaryInput, SummaryTone } from './summarize';

interface Case {
  name: string;
  input: SummaryInput;
  tone: SummaryTone;
  /** Potongan teks yang wajib muncul di kesimpulan. */
  conclusionHas?: string[];
  /** Potongan teks yang wajib muncul di salah satu item "perlu ditunggu". */
  waitHas?: string[];
  riskHas?: string[];
  supportHas?: string[];
}

const base = (over: Partial<SummaryInput> = {}): SummaryInput => ({
  technical: { price: 1000, ema20: 990, ema50: 970, ema200: 900, rsi14: 55, macd_hist: 1, vol_ratio: 1.1, atr14: 25, entry_low: 980, entry_high: 1000 },
  money_flow: { cmf20: 0, money_flow_status: 'NEUTRAL', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
  composite: { score: 55, risk_reward_ratio: 1.8, confluence_score: 3, stop_loss: 940 },
  direction: { direction_score: 0, regime: 'RANGING', confidence: 55, last_swing_high: 1050, last_swing_low: 950 },
  market_regime: { direction_score: 10, direction_label: 'Sideways' },
  financials: { health_grade: 'MODERATE', health_score: 55, is_speculative: false },
  ...over,
});

const CASES: Case[] = [
  {
    name: 'Downtrend + outflow → tunggu tanda pembalikan',
    input: base({
      technical: { price: 800, ema20: 850, ema50: 900, ema200: 950, rsi14: 35, macd_hist: -3, vol_ratio: 1.2, atr14: 20 },
      money_flow: { cmf20: -0.14, money_flow_status: 'STRONG_OUTFLOW', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
      direction: { direction_score: -62, regime: 'TRENDING_DOWN', confidence: 70, last_swing_high: 880 },
    }),
    tone: 'negative',
    conclusionHas: ['Tunggu tanda pembalikan'.toLowerCase()],
    waitHas: ['Tanda pembalikan', 'EMA20'],
    riskHas: ['Tren sedang turun', 'uang keluar'],
  },
  {
    name: 'Uptrend tapi harga jauh di atas EMA20 → rawan koreksi, tunggu pullback',
    input: base({
      technical: { price: 1200, ema20: 1050, ema50: 980, ema200: 900, rsi14: 68, macd_hist: 5, vol_ratio: 1.5, atr14: 30, entry_low: 1060, entry_high: 1090 },
      money_flow: { cmf20: 0.12, money_flow_status: 'MILD_INFLOW', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
      direction: { direction_score: 58, regime: 'TRENDING_UP', confidence: 80 },
      composite: { confluence_score: 4, risk_reward_ratio: 1.2 },
    }),
    tone: 'cautious',
    conclusionHas: ['rawan koreksi', 'tunggu pullback'],
    waitHas: ['Pullback mendekati EMA20'],
    riskHas: ['di atas EMA20'],
  },
  {
    name: 'Uptrend + inflow + konfluensi ≥4 → positif tapi tetap hati-hati',
    input: base({
      technical: { price: 1020, ema20: 1000, ema50: 960, ema200: 880, rsi14: 60, macd_hist: 2, vol_ratio: 1.6, atr14: 25 },
      money_flow: { cmf20: 0.18, money_flow_status: 'STRONG_INFLOW', vsa_signal: 'MARKUP', obv_divergence: 'NONE' },
      direction: { direction_score: 45, regime: 'TRENDING_UP', confidence: 75, break_of_structure: 'BULLISH_BOS' },
      composite: { confluence_score: 5, risk_reward_ratio: 2.1, stop_loss: 960 },
      financials: { health_grade: 'HEALTHY', health_score: 80, is_speculative: false },
    }),
    tone: 'positive',
    conclusionHas: ['bukan kepastian'],
    supportHas: ['Tren cenderung naik', 'akumulasi kuat'],
  },
  {
    name: 'Uptrend + indeks lemah → turun jadi cautious',
    input: base({
      technical: { price: 1020, ema20: 1000, ema50: 960, ema200: 880, rsi14: 60, macd_hist: 2, vol_ratio: 1.6, atr14: 25 },
      money_flow: { cmf20: 0.18, money_flow_status: 'STRONG_INFLOW', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
      direction: { direction_score: 45, regime: 'TRENDING_UP', confidence: 75 },
      composite: { confluence_score: 5, risk_reward_ratio: 2.1 },
      market_regime: { direction_score: -45, direction_label: 'Cenderung Turun' },
    }),
    tone: 'cautious',
    conclusionHas: ['indeks sedang lemah'],
    riskHas: ['Indeks sedang lemah'],
  },
  {
    name: 'Uptrend + outflow → waspada distribusi',
    input: base({
      money_flow: { cmf20: -0.07, money_flow_status: 'MILD_OUTFLOW', vsa_signal: 'NORMAL', obv_divergence: 'BEARISH_DISTRIBUTION' },
      direction: { direction_score: 30, regime: 'TRENDING_UP', confidence: 60 },
    }),
    tone: 'cautious',
    conclusionHas: ['waspada distribusi'],
    waitHas: ['Konfirmasi aliran dana'],
  },
  {
    name: 'Spekulatif → risiko fundamental mendominasi',
    input: base({
      money_flow: { cmf20: 0.2, money_flow_status: 'STRONG_INFLOW', vsa_signal: 'MARKUP', obv_divergence: 'NONE' },
      direction: { direction_score: 55, regime: 'TRENDING_UP', confidence: 70 },
      composite: { is_speculative: true, confluence_score: 4 },
      financials: { health_grade: 'DISTRESSED', health_score: 20, is_speculative: true },
    }),
    tone: 'negative',
    riskHas: ['spekulatif'],
  },
  {
    name: 'Sideways → tunggu arah jelas',
    input: base(),
    tone: 'neutral',
    conclusionHas: ['sideways'],
    waitHas: ['breakout di atas'],
  },
  {
    name: 'Squeeze → arah belum diketahui',
    input: base({ direction: { direction_score: 5, regime: 'SQUEEZE', squeeze: true, confidence: 50 } }),
    tone: 'neutral',
    conclusionHas: ['arahnya belum diketahui'],
    waitHas: ['squeeze'],
  },
  {
    name: 'Downtrend + divergensi bullish → cautious, belum konfirmasi',
    input: base({
      technical: { price: 800, ema20: 840, ema50: 880, ema200: 950, rsi14: 38, macd_hist: -1, vol_ratio: 1, atr14: 20 },
      direction: { direction_score: -35, regime: 'TRENDING_DOWN', confidence: 55, rsi_divergence: 'BULLISH', last_swing_high: 870 },
    }),
    tone: 'cautious',
    conclusionHas: ['belum konfirmasi'],
    waitHas: ['swing high terakhir'],
  },
  {
    name: 'PULLBACK_IDEAL → diskon dalam tren naik, pantau pemicu MACD',
    input: base({
      technical: { price: 980, ema20: 1000, ema50: 950, ema200: 850, rsi14: 45, macd_hist: -1, vol_ratio: 0.8, atr14: 25 },
      direction: {
        direction_score: 12, regime: 'RANGING', confidence: 50,
        pullback: { state: 'PULLBACK_IDEAL', label: 'Pullback Ideal', score: 0.6, long_momentum_pct: 24, relative_momentum_pct: 12, support_level: 950, notes: [] },
      },
    }),
    tone: 'cautious',
    conclusionHas: ['diskon', 'MACD berbalik naik'],
    waitHas: ['MACD histogram berbalik naik'],
    supportHas: ['Momentum 6 bulan positif'],
  },
  {
    name: 'UPTREND_EXTENDED → tunggu pullback',
    input: base({
      technical: { price: 1030, ema20: 1000, ema50: 950, ema200: 850, rsi14: 66, macd_hist: 2, vol_ratio: 1.2, atr14: 25 },
      money_flow: { cmf20: 0.1, money_flow_status: 'MILD_INFLOW', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
      direction: {
        direction_score: 55, regime: 'TRENDING_UP', confidence: 75,
        pullback: { state: 'UPTREND_EXTENDED', label: 'Uptrend Terlalu Jauh', score: -0.2, long_momentum_pct: 40, stretch_atr: 3.1, notes: [] },
      },
    }),
    tone: 'cautious',
    conclusionHas: ['tunggu pullback'],
    waitHas: ['Pullback mendekati EMA20'],
  },
  {
    name: 'TREND_BROKEN → bukan setup pullback',
    input: base({
      direction: { direction_score: 5, regime: 'RANGING', confidence: 40, pullback: { state: 'TREND_BROKEN', label: 'Tren Patah', score: -0.6, long_momentum_pct: -5, notes: [] } },
    }),
    tone: 'neutral',
    conclusionHas: ['Bukan setup pullback'],
    riskHas: ['bukan setup pullback'],
  },
  {
    name: 'market_mode BEARISH mendahului saham yang bagus',
    input: base({
      technical: { price: 1020, ema20: 1000, ema50: 960, ema200: 880, rsi14: 60, macd_hist: 2, vol_ratio: 1.6, atr14: 25 },
      money_flow: { cmf20: 0.18, money_flow_status: 'STRONG_INFLOW', vsa_signal: 'NORMAL', obv_divergence: 'NONE' },
      direction: { direction_score: 45, regime: 'TRENDING_UP', confidence: 75 },
      composite: { confluence_score: 5, risk_reward_ratio: 2.1, market_mode: 'BEARISH' },
    }),
    tone: 'cautious',
    conclusionHas: ['Pasar sedang bearish', 'prioritas jaga modal'],
    riskHas: ['Pasar sedang bearish'],
    waitHas: ['Indeks stabil'],
  },
  {
    name: 'market_mode CRASH (tipe belum ada) → krisis, jaga modal',
    input: base({ composite: { market_mode: 'CRASH' as never } }),
    tone: 'cautious',
    conclusionHas: ['krisis', 'prioritas jaga modal'],
    riskHas: ['krisis'],
  },
  {
    name: 'Payload minimal (tanpa direction) tidak crash',
    input: { technical: { price: 100 } },
    tone: 'neutral',
  },
];

const BANNED = ['pasti naik', 'dijamin', 'pasti untung', 'beli sekarang'];

let failures = 0;
for (const c of CASES) {
  const s = summarizeAnalysis(c.input);
  const errs: string[] = [];
  const lc = (x: string) => x.toLowerCase();
  if (s.tone !== c.tone) errs.push(`tone=${s.tone}, harap ${c.tone}`);
  for (const needle of c.conclusionHas ?? [])
    if (!lc(s.conclusion).includes(lc(needle))) errs.push(`kesimpulan tidak memuat "${needle}"`);
  const check = (list: string[], needles: string[] | undefined, label: string) => {
    for (const n of needles ?? []) if (!list.some((x) => lc(x).includes(lc(n)))) errs.push(`${label} tidak memuat "${n}"`);
  };
  check(s.waitFor, c.waitHas, 'perlu ditunggu');
  check(s.risks, c.riskHas, 'diwaspadai');
  check(s.supports, c.supportHas, 'mendukung');
  if (s.waitFor.length === 0) errs.push('perlu ditunggu kosong');
  if ([s.supports, s.risks, s.waitFor].some((l) => l.length > 3)) errs.push('lebih dari 3 item');
  const all = lc([s.headline, s.conclusion, ...s.supports, ...s.risks, ...s.waitFor].join(' '));
  for (const b of BANNED) if (all.includes(b)) errs.push(`memuat frasa terlarang "${b}"`);

  if (errs.length) {
    failures++;
    console.log(`✗ ${c.name}\n    ${errs.join('\n    ')}\n    → ${JSON.stringify(s, null, 2)}`);
  } else {
    console.log(`✓ ${c.name}\n    [${s.tone}] ${s.headline} — ${s.conclusion}`);
  }
}

if (failures) throw new Error(`${failures} kasus gagal`);
console.log(`\nSemua ${CASES.length} kasus lolos.`);
