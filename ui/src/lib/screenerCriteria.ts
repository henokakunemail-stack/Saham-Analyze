/** Multi-indicator screening criteria (pure logic, no React). */
import type { ScreenerItem } from '../types/stock';

export type RangeKey =
  | 'score'
  | 'direction_score'
  | 'adx'
  | 'rsi14'
  | 'cmf20'
  | 'vol_ratio'
  | 'liq_bn'
  | 'ret_1m'
  | 'ret_3m'
  | 'ret_6m'
  | 'rs_60d'
  | 'dist_52w_high_pct'
  | 'dist_ema200_pct'
  | 'stretch_atr'
  | 'pe'
  | 'pbv'
  | 'roe';

export interface Range {
  min?: number;
  max?: number;
}

export interface Criteria {
  ranges: Partial<Record<RangeKey, Range>>;
  pullbackStates: string[];
  flowStatuses: string[];
  healthGrades: string[];
  hideSpeculative: boolean;
  hideIlliquid: boolean;
  /** Fase 4: Indonesian sector labels (row.sector). */
  sectors?: string[];
  /** Fase 1: LAYAK / TUNGGU / HINDARI (row.action.status). */
  actionStatuses?: string[];
}

export const EMPTY_CRITERIA: Criteria = {
  ranges: {},
  pullbackStates: [],
  flowStatuses: [],
  healthGrades: [],
  hideSpeculative: false,
  hideIlliquid: false,
  sectors: [],
  actionStatuses: [],
};

type Getter = (i: ScreenerItem) => number | null | undefined;

export interface RangeDef {
  key: RangeKey;
  label: string;
  unit?: string;
  step: number;
  group: 'Teknikal' | 'Momentum & Posisi' | 'Likuiditas' | 'Fundamental';
  get: Getter;
}

export const RANGE_DEFS: RangeDef[] = [
  { key: 'score', label: 'Skor komposit', step: 1, group: 'Teknikal', get: (i) => i.score },
  { key: 'direction_score', label: 'Arah tren', step: 5, group: 'Teknikal', get: (i) => i.direction_score },
  { key: 'adx', label: 'ADX (kekuatan tren)', step: 1, group: 'Teknikal', get: (i) => i.adx },
  { key: 'rsi14', label: 'RSI 14', step: 1, group: 'Teknikal', get: (i) => i.rsi14 },
  { key: 'cmf20', label: 'CMF 20', step: 0.01, group: 'Teknikal', get: (i) => i.cmf20 },
  { key: 'vol_ratio', label: 'Rasio volume', unit: '×', step: 0.1, group: 'Teknikal', get: (i) => i.vol_ratio },
  { key: 'ret_1m', label: 'Return 1 bulan', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.ret_1m },
  { key: 'ret_3m', label: 'Return 3 bulan', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.ret_3m },
  { key: 'ret_6m', label: 'Return 6 bulan', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.ret_6m },
  { key: 'rs_60d', label: 'Kekuatan vs indeks 60h', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.rs_60d },
  { key: 'dist_52w_high_pct', label: 'Jarak dari high 52 mgg', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.dist_52w_high_pct },
  { key: 'dist_ema200_pct', label: 'Jarak dari EMA200', unit: '%', step: 1, group: 'Momentum & Posisi', get: (i) => i.screen?.dist_ema200_pct },
  { key: 'stretch_atr', label: 'Jarak dari EMA20', unit: '×ATR', step: 0.1, group: 'Momentum & Posisi', get: (i) => i.screen?.stretch_atr },
  { key: 'liq_bn', label: 'Nilai transaksi/hari', unit: 'miliar', step: 1, group: 'Likuiditas',
    get: (i) => (i.screen?.avg_value_20d !== undefined && i.screen?.avg_value_20d !== null ? i.screen.avg_value_20d / 1e9 : null) },
  { key: 'pe', label: 'PER', unit: '×', step: 1, group: 'Fundamental', get: (i) => (i.pe ? i.pe : null) },
  { key: 'pbv', label: 'PBV', unit: '×', step: 0.1, group: 'Fundamental', get: (i) => (i.pbv ? i.pbv : null) },
  { key: 'roe', label: 'ROE', unit: '%', step: 1, group: 'Fundamental', get: (i) => (i.roe ? i.roe : null) },
];

const DEF_BY_KEY = Object.fromEntries(RANGE_DEFS.map((d) => [d.key, d])) as Record<RangeKey, RangeDef>;

export const PULLBACK_STATE_LABELS: Record<string, string> = {
  PULLBACK_IDEAL: 'Pullback sehat',
  PULLBACK_DEEP: 'Koreksi dalam',
  UPTREND_RUNNING: 'Uptrend berjalan',
  UPTREND_EXTENDED: 'Terlalu panas',
  TREND_BROKEN: 'Tren rusak',
  NO_UPTREND: 'Bukan uptrend',
};
export const FLOW_LABELS: Record<string, string> = {
  STRONG_INFLOW: 'Akumulasi kuat',
  MILD_INFLOW: 'Akumulasi',
  NEUTRAL: 'Netral',
  MILD_OUTFLOW: 'Distribusi',
  STRONG_OUTFLOW: 'Distribusi kuat',
};
export const HEALTH_LABELS: Record<string, string> = { HEALTHY: 'Sehat', MODERATE: 'Stabil', DISTRESSED: 'Tertekan' };

const isSet = (r?: Range) => r !== undefined && (r.min !== undefined || r.max !== undefined);

/** A stock passes when it meets every active condition. A missing value never passes an active range. */
export function matches(item: ScreenerItem, c: Criteria): boolean {
  for (const [key, range] of Object.entries(c.ranges) as [RangeKey, Range][]) {
    if (!isSet(range)) continue;
    const v = DEF_BY_KEY[key]?.get(item);
    if (v === undefined || v === null || Number.isNaN(v)) return false;
    if (range.min !== undefined && v < range.min) return false;
    if (range.max !== undefined && v > range.max) return false;
  }
  if (c.pullbackStates.length && !c.pullbackStates.includes(item.pullback_state ?? '')) return false;
  if (c.flowStatuses.length && !c.flowStatuses.includes(item.money_flow_status)) return false;
  if (c.healthGrades.length && !c.healthGrades.includes(item.health_grade ?? '')) return false;
  if (c.hideSpeculative && item.is_speculative) return false;
  if (c.hideIlliquid && item.screen?.illiquid) return false;
  if (c.sectors?.length && !c.sectors.includes(item.sector ?? '')) return false;
  if (c.actionStatuses?.length && !c.actionStatuses.includes(item.action?.status ?? '')) return false;
  return true;
}

export function isEmpty(c: Criteria): boolean {
  return (
    !Object.values(c.ranges).some(isSet) &&
    !c.pullbackStates.length &&
    !c.flowStatuses.length &&
    !c.healthGrades.length &&
    !c.hideSpeculative &&
    !c.hideIlliquid &&
    !c.sectors?.length &&
    !c.actionStatuses?.length
  );
}

export interface Chip {
  id: string;
  label: string;
  clear: (c: Criteria) => Criteria;
}

const num = (v: number) => v.toLocaleString('id-ID', { maximumFractionDigits: 2 });

export function activeChips(c: Criteria): Chip[] {
  const chips: Chip[] = [];
  for (const [key, r] of Object.entries(c.ranges) as [RangeKey, Range][]) {
    if (!isSet(r)) continue;
    const d = DEF_BY_KEY[key];
    const u = d.unit ? ` ${d.unit}` : '';
    const text =
      r.min !== undefined && r.max !== undefined
        ? `${num(r.min)}–${num(r.max)}${u}`
        : r.min !== undefined
        ? `≥ ${num(r.min)}${u}`
        : `≤ ${num(r.max as number)}${u}`;
    chips.push({
      id: `r-${key}`,
      label: `${d.label} ${text}`,
      clear: (x) => {
        const ranges = { ...x.ranges };
        delete ranges[key];
        return { ...x, ranges };
      },
    });
  }
  for (const s of c.pullbackStates)
    chips.push({ id: `p-${s}`, label: PULLBACK_STATE_LABELS[s] ?? s, clear: (x) => ({ ...x, pullbackStates: x.pullbackStates.filter((y) => y !== s) }) });
  for (const s of c.flowStatuses)
    chips.push({ id: `f-${s}`, label: FLOW_LABELS[s] ?? s, clear: (x) => ({ ...x, flowStatuses: x.flowStatuses.filter((y) => y !== s) }) });
  for (const s of c.healthGrades)
    chips.push({ id: `h-${s}`, label: `Fundamental ${HEALTH_LABELS[s] ?? s}`, clear: (x) => ({ ...x, healthGrades: x.healthGrades.filter((y) => y !== s) }) });
  for (const s of c.sectors ?? [])
    chips.push({ id: `s-${s}`, label: `Sektor ${s}`, clear: (x) => ({ ...x, sectors: (x.sectors ?? []).filter((y) => y !== s) }) });
  for (const s of c.actionStatuses ?? [])
    chips.push({ id: `a-${s}`, label: `Status ${s}`, clear: (x) => ({ ...x, actionStatuses: (x.actionStatuses ?? []).filter((y) => y !== s) }) });
  if (c.hideSpeculative) chips.push({ id: 'spec', label: 'Tanpa saham spekulatif', clear: (x) => ({ ...x, hideSpeculative: false }) });
  if (c.hideIlliquid) chips.push({ id: 'liq', label: 'Hanya saham likuid', clear: (x) => ({ ...x, hideIlliquid: false }) });
  return chips;
}

export interface Preset {
  id: string;
  label: string;
  description: string;
  criteria: Criteria;
}

const P = (partial: Partial<Criteria>): Criteria => ({ ...EMPTY_CRITERIA, ...partial, ranges: { ...(partial.ranges ?? {}) } });

export const PRESETS: Preset[] = [
  {
    id: 'layak',
    label: '✅ Layak Dieksekusi',
    description: 'Status LAYAK: vonis beli, risiko ≤ 6%, tidak terlalu volatil, likuid, tanpa ARB/suspensi baru, pasar tidak krisis (teruji di periode uji).',
    criteria: P({ actionStatuses: ['LAYAK'] }),
  },
  {
    id: 'pullback',
    label: '🎯 Pullback Sehat',
    description: 'Strategi utama: tren 6 bulan naik, sedang koreksi wajar ke support, tren cukup kuat (ADX ≥ 18), likuid.',
    criteria: P({ pullbackStates: ['PULLBACK_IDEAL'], ranges: { adx: { min: 18 } }, hideIlliquid: true }),
  },
  {
    id: 'leaders',
    label: '🏆 Pemimpin vs Indeks',
    description: 'Lebih kuat ≥ 5% dari indeks dalam 60 hari dan masih di atas EMA200 — kandidat pantauan saat pasar lemah.',
    criteria: P({ ranges: { rs_60d: { min: 5 }, dist_ema200_pct: { min: 0 } }, hideIlliquid: true }),
  },
  {
    id: 'accumulation',
    label: '💧 Akumulasi saat Koreksi',
    description: 'Aliran uang positif (CMF ≥ 0,05) sementara harga di bawah/sekitar EMA20.',
    criteria: P({ ranges: { cmf20: { min: 0.05 }, stretch_atr: { max: 0 } }, hideIlliquid: true }),
  },
  {
    id: 'strong_not_hot',
    label: '📈 Tren Kuat, Belum Panas',
    description: 'Arah tren ≥ 40, RSI ≤ 68, dan harga tidak lebih dari 2× ATR di atas EMA20.',
    criteria: P({ ranges: { direction_score: { min: 40 }, rsi14: { max: 68 }, stretch_atr: { max: 2 } }, hideIlliquid: true }),
  },
  {
    id: 'quality_discount',
    label: '🛡️ Fundamental Sehat + Diskon',
    description: 'Fundamental sehat, tidak spekulatif, dan harga ≥ 20% di bawah high 52 minggu.',
    criteria: P({ healthGrades: ['HEALTHY'], ranges: { dist_52w_high_pct: { max: -20 } }, hideSpeculative: true }),
  },
  {
    id: 'avoid',
    label: '⛔ Hindari',
    description: 'Tren rusak / bukan uptrend dan uang keluar — daftar untuk dihindari atau dievaluasi ulang.',
    criteria: P({ pullbackStates: ['TREND_BROKEN', 'NO_UPTREND'], flowStatuses: ['MILD_OUTFLOW', 'STRONG_OUTFLOW'] }),
  },
];
