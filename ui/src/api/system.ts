/** Technical Quality API calls. */
import { API_BASE } from './base';
import type { DataQualityOverview, DataQualityReport } from '../types/system';

export const systemApi = {
  base: API_BASE,

  /** All stored data-quality reports, worst first. */
  async getDataQuality(): Promise<DataQualityOverview> {
    const res = await fetch(`${API_BASE}/system/data-quality`);
    if (!res.ok) throw new Error(`Gagal memuat kualitas data (${res.status})`);
    return res.json();
  },

  /** Report for one ticker; null if it was never loaded. refresh=true re-downloads from yfinance first. */
  async getTickerDataQuality(ticker: string, market: 'IDX' | 'US' = 'IDX', refresh = false): Promise<DataQualityReport | null> {
    const q = new URLSearchParams({ ticker, market, refresh: String(refresh) });
    const res = await fetch(`${API_BASE}/system/data-quality?${q}`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Gagal memuat kualitas data ${ticker} (${res.status})`);
    return res.json();
  },
};
