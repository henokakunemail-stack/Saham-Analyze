/** Signal Trust API calls. */
import { API_BASE } from './base';
import { requestJson, TIMEOUT } from './feedback';
import type { BacktestHorizon, BacktestResponse, ReliabilityResponse } from '../types/signals';
import type { PredictionHistoryResponse } from '../types/stock';

export const signalsApi = {
  base: API_BASE,

  /** Non-blocking: returns status "running" until the background computation finishes; poll again.
   * Throws ApiError with an Indonesian message (the panel shows it inline). */
  async getBacktest(market: 'IDX' | 'US', horizon: BacktestHorizon, refresh = false): Promise<BacktestResponse> {
    const params = new URLSearchParams({ market, horizon: String(horizon) });
    if (refresh) params.set('refresh', 'true');
    return requestJson<BacktestResponse>(`${API_BASE}/backtest?${params}`, { timeout: TIMEOUT.slow });
  },

  /** Track record per pullback state / market mode / score bucket. Never blocks; null on failure. */
  async getReliability(market: 'IDX' | 'US', horizon = 10): Promise<ReliabilityResponse | null> {
    try {
      const params = new URLSearchParams({ market, horizon: String(horizon) });
      return await requestJson<ReliabilityResponse>(`${API_BASE}/backtest/reliability?${params}`, { timeout: TIMEOUT.normal });
    } catch {
      return null;
    }
  },

  /** Throws ApiError (Indonesian message) on failure so the view can tell "error" from "no data". */
  async getPredictionHistory(
    market: 'IDX' | 'US',
    snapshotDate?: string,
    horizon?: number
  ): Promise<PredictionHistoryResponse> {
    const params = new URLSearchParams({ market });
    if (snapshotDate) params.set('snapshot_date', snapshotDate);
    if (horizon) params.set('horizon', String(horizon));
    return requestJson<PredictionHistoryResponse>(`${API_BASE}/predictions/history?${params}`, { timeout: TIMEOUT.slow });
  },
};
