/** Market breadth & sector strength API (Fase 4, display only). Types live here until the integrator moves them. */
import { API_BASE } from './base';
import { requestJson, TIMEOUT } from './feedback';

export type Market = 'IDX' | 'US';

export interface BreadthMetrics {
  /** Tickers with a bar on that date */
  n: number;
  pct_above_ema20: number | null;
  pct_above_ema50: number | null;
  pct_above_ema200: number | null;
  advancers: number;
  decliners: number;
  unchanged: number;
  new_high_20d: number;
  new_low_20d: number;
  /** % of tickers with CMF20 > 0 */
  pct_cmf_pos: number | null;
}

export interface BreadthPoint extends BreadthMetrics {
  date: string;
  /** Cumulative (advancers − decliners) from the first returned date */
  ad_line: number;
}

export interface BreadthLatest extends BreadthMetrics {
  date: string;
  updated_at?: string | null;
}

export type BreadthLabelCode = 'STRONG' | 'HEALTHY' | 'NEUTRAL' | 'WEAK' | 'VERY_WEAK' | 'NO_DATA';

export interface BreadthResponse {
  market: Market;
  latest: BreadthLatest | null;
  /** e.g. "Lemah (28% di atas EMA50)" */
  label: string;
  label_code: BreadthLabelCode;
  /** Oldest → newest */
  history: BreadthPoint[];
}

export interface SectorStrength {
  sector: string;
  count: number;
  median_ret_1m: number | null;
  median_ret_3m: number | null;
  pct_above_ema50: number | null;
  median_score: number | null;
  /** Rows with action.status === "LAYAK" */
  layak: number;
  /** Members, best score first */
  tickers: string[];
  /** 1..N; null for "Lainnya" */
  rank: number | null;
}

export interface SectorsResponse {
  market: Market;
  sectors: SectorStrength[];
  updated_at: string | null;
  /** Tickers whose sector is still being fetched from Yahoo */
  missing: number;
  refreshing: boolean;
}

export const marketApi = {
  /** First call per market builds 120 days of history from cached candles (a few seconds). */
  getBreadth(market: Market, days: number = 120): Promise<BreadthResponse> {
    return requestJson<BreadthResponse>(`${API_BASE}/market/breadth?market=${market}&days=${days}`, {
      timeout: TIMEOUT.slow,
    });
  },

  getSectors(market: Market): Promise<SectorsResponse> {
    return requestJson<SectorsResponse>(`${API_BASE}/market/sectors?market=${market}`, { timeout: TIMEOUT.normal });
  },
};
