import {
  ScreenerItem,
  ChartData,
  StockAnalysis,
  MarketIndex,
  WatchlistItem,
  AISettings,
  AIValidationResult,
  PredictionHistoryResponse,
  ScanStatus,
  BrokerSummaryData,
  AiModelsResponse,
  ClosingReview
} from '../types/stock';
import { API_BASE } from './base';
import { requestJson, TIMEOUT, ApiError } from './feedback';

// Failures are reported through onApiError() (api/feedback.ts) with a human message;
// every function below keeps its original return shape so callers need no changes.
export { onApiError } from './feedback';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

/** Message for calls that report errors inline ({ ok: false, message }) instead of via events. */
const inlineError = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export const api = {
  async getHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2500) });
      return res.ok;
    } catch {
      return false;
    }
  },

  async getMarketSummary(): Promise<Record<string, MarketIndex>> {
    try {
      return await requestJson(`${API_BASE}/market/summary`, {
        op: 'market', title: 'Gagal memuat ringkasan pasar', timeout: TIMEOUT.slow,
      });
    } catch {
      return {};
    }
  },

  /** cachedOnly: return the cached rows without ever starting a scan (quiet background reloads). */
  async getScreener(market: 'IDX' | 'US' = 'IDX', forceRefresh: boolean = false, cachedOnly: boolean = false): Promise<ScreenerItem[]> {
    try {
      // Without force_refresh (and without cached_only) the engine may still run a full scan when its cache is thin
      const data = await requestJson<{ results?: ScreenerItem[] }>(
        `${API_BASE}/screener?market=${market}&force_refresh=${forceRefresh}&limit=250${cachedOnly ? '&cached_only=true' : ''}`,
        { op: 'screener', title: forceRefresh ? 'Scan pasar gagal' : 'Gagal memuat screener', timeout: TIMEOUT.scan }
      );
      return data.results || [];
    } catch {
      return [];
    }
  },

  async getStockChart(
    ticker: string,
    market: 'IDX' | 'US' = 'IDX',
    interval: string = '1d',
    forceRefresh: boolean = false,
    silent: boolean = false
  ): Promise<ChartData | null> {
    try {
      // silent: background polls fail quietly (no toast)
      return await requestJson<ChartData>(
        `${API_BASE}/stock/${encodeURIComponent(ticker)}/chart?market=${market}&interval=${interval}&force_refresh=${forceRefresh}`,
        silent
          ? { timeout: TIMEOUT.slow }
          : { op: `chart:${ticker}`, title: `Gagal memuat grafik ${ticker}`, timeout: TIMEOUT.slow }
      );
    } catch {
      return null;
    }
  },

  /** Analisa Penutupan: last session vs its plan + next plan with an honest assessment (silent, null on failure). */
  async getClosingReview(market: 'IDX' | 'US'): Promise<ClosingReview | null> {
    try {
      return await requestJson<ClosingReview>(`${API_BASE}/plan/closing-review?market=${market}`, { timeout: TIMEOUT.slow });
    } catch {
      return null;
    }
  },

  /** Exchange that has data for a code typed/clicked without its suffix (null when none has). */
  async resolveTicker(ticker: string, market: 'IDX' | 'US'): Promise<{ ticker: string; market: 'IDX' | 'US' } | null> {
    try {
      return await requestJson(
        `${API_BASE}/stock/${encodeURIComponent(ticker)}/resolve?market=${market}`,
        { op: `resolve:${ticker}`, title: `Saham ${ticker} tidak ditemukan`, timeout: TIMEOUT.slow }
      );
    } catch {
      return null;
    }
  },

  async getStockAnalysis(ticker: string, market: 'IDX' | 'US' = 'IDX', forceRefresh: boolean = false): Promise<StockAnalysis | null> {
    try {
      return await requestJson<StockAnalysis>(
        `${API_BASE}/stock/${encodeURIComponent(ticker)}/analysis?market=${market}&force_refresh=${forceRefresh}`,
        { op: `analysis:${ticker}`, title: `Gagal memuat analisis ${ticker}`, timeout: TIMEOUT.slow }
      );
    } catch {
      return null;
    }
  },

  async getWatchlist(): Promise<WatchlistItem[]> {
    try {
      return await requestJson<WatchlistItem[]>(`${API_BASE}/watchlist`, {
        op: 'watchlist', title: 'Gagal memuat watchlist',
      });
    } catch {
      return [];
    }
  },

  async addToWatchlist(item: WatchlistItem): Promise<boolean> {
    try {
      await requestJson(`${API_BASE}/watchlist`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(item),
        op: 'watchlist.add', title: `Gagal menambahkan ${item.ticker} ke watchlist`,
      });
      return true;
    } catch {
      return false;
    }
  },

  async removeFromWatchlist(ticker: string): Promise<boolean> {
    try {
      await requestJson(`${API_BASE}/watchlist/${encodeURIComponent(ticker)}`, {
        method: 'DELETE', op: 'watchlist.remove', title: `Gagal menghapus ${ticker} dari watchlist`,
      });
      return true;
    } catch {
      return false;
    }
  },

  async getSettings(): Promise<AISettings | null> {
    try {
      return await requestJson<AISettings>(`${API_BASE}/settings`, {
        op: 'settings', title: 'Gagal memuat pengaturan',
      });
    } catch {
      return null;
    }
  },

  async updateSettings(data: {
    provider?: string;
    base_url?: string;
    api_key?: string;
    model?: string;
    sectors_api_key?: string;
    anthropic_api_key?: string;
    anthropic_model?: string;
    anthropic_auth_mode?: 'api_key' | 'login';
  }): Promise<boolean> {
    try {
      await requestJson(`${API_BASE}/settings`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data),
        op: 'settings.save', title: 'Gagal menyimpan pengaturan',
      });
      return true;
    } catch {
      return false;
    }
  },

  async getBrokerSummary(ticker: string, market: 'IDX' | 'US' = 'IDX', refresh: boolean = false): Promise<BrokerSummaryData | null> {
    try {
      return await requestJson<BrokerSummaryData>(
        `${API_BASE}/stock/${encodeURIComponent(ticker)}/broker-summary?market=${market}&refresh=${refresh}`,
        { op: `broker:${ticker}`, title: `Gagal memuat broker summary ${ticker}`, timeout: TIMEOUT.slow }
      );
    } catch {
      return null;
    }
  },

  // The calls below already show their result inline ({ ok, message }), so they don't emit toasts.
  async testBrokerApiKey(provider: string, apiKey: string): Promise<{ ok: boolean; message: string }> {
    try {
      return await requestJson(`${API_BASE}/broker/test-connection`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ provider, api_key: apiKey }),
        timeout: TIMEOUT.slow,
      });
    } catch (e) {
      return { ok: false, message: inlineError(e, 'Gagal menghubungi server broker') };
    }
  },

  async testAiConnection(data: { provider?: string; base_url?: string; api_key?: string; model?: string; auth_mode?: string }): Promise<{ ok: boolean; message: string; latency_ms?: number; model?: string }> {
    try {
      return await requestJson(`${API_BASE}/ai/test-connection`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data), timeout: TIMEOUT.slow,
      });
    } catch (e) {
      return { ok: false, message: inlineError(e, 'Koneksi gagal') };
    }
  },

  /** Models/combos the provider really offers (no invented fallback list on failure). */
  async fetchAiModels(data: { provider?: string; base_url?: string; api_key?: string; auth_mode?: string; refresh?: boolean }): Promise<AiModelsResponse> {
    try {
      return await requestJson<AiModelsResponse>(`${API_BASE}/ai/models`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(data), timeout: TIMEOUT.slow,
      });
    } catch (e) {
      return { ok: false, models: [], combos: [], groups: [], message: inlineError(e, 'Gagal mendeteksi model') };
    }
  },

  async validateSignal(ticker: string, market: 'IDX' | 'US' = 'IDX'): Promise<AIValidationResult> {
    try {
      return await requestJson<AIValidationResult>(`${API_BASE}/ai/validate-signal`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ ticker, market }), timeout: TIMEOUT.ai,
      });
    } catch (e) {
      return { ok: false, error: inlineError(e, 'Gagal memvalidasi sinyal') };
    }
  },

  /** Polled every few seconds: silent, the health check reports connection loss. */
  async getScanStatus(): Promise<ScanStatus | null> {
    try {
      return await requestJson<ScanStatus>(`${API_BASE}/screener/status`, { timeout: TIMEOUT.short });
    } catch {
      return null;
    }
  },

  async getPredictionDates(market: 'IDX' | 'US' = 'IDX'): Promise<string[]> {
    try {
      const data = await requestJson<{ dates?: string[] }>(`${API_BASE}/predictions/dates?market=${market}`, {
        op: 'predictions.dates', title: 'Gagal memuat tanggal prediksi',
      });
      return data.dates || [];
    } catch {
      return [];
    }
  },

  async getPredictionHistory(
    market: 'IDX' | 'US' = 'IDX',
    snapshotDate?: string
  ): Promise<PredictionHistoryResponse | null> {
    try {
      const url = snapshotDate
        ? `${API_BASE}/predictions/history?market=${market}&snapshot_date=${encodeURIComponent(snapshotDate)}`
        : `${API_BASE}/predictions/history?market=${market}`;
      return await requestJson<PredictionHistoryResponse>(url, {
        op: 'predictions.history', title: 'Gagal memuat riwayat prediksi', timeout: TIMEOUT.slow,
      });
    } catch {
      return null;
    }
  },

  async triggerBackfill(
    market: 'IDX' | 'US' = 'IDX',
    daysAgo: number = 7
  ): Promise<{ ok: boolean; snapshot_date?: string; message?: string }> {
    try {
      return await requestJson(`${API_BASE}/predictions/backfill`, {
        method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ market, days_ago: daysAgo }),
        timeout: TIMEOUT.scan,
      });
    } catch (e) {
      return { ok: false, message: inlineError(e, 'Gagal trigger backfill') };
    }
  },
};
