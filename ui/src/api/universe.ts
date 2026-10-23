/** Coverage & Control API calls (scan universe, market session, auto-scan, alerts). */
import { API_BASE } from './base';
import type {
  AlertList,
  AlertPrefs,
  AutoScanMode,
  Market,
  MarketSession,
  UniverseInfo,
  UniverseMutationResult,
} from '../types/universe';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function req<T>(path: string, init: RequestInit = {}, timeoutMs = 8000): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const universeApi = {
  base: API_BASE,

  getUniverse: (market: Market) => req<UniverseInfo>(`/universe?market=${market}`),

  /** Validates the ticker against Yahoo Finance before adding (can take a few seconds). */
  addTicker: (market: Market, ticker: string) =>
    req<UniverseMutationResult>(
      `/universe/${market}/tickers`,
      { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ ticker }) },
      15000
    ),

  removeTicker: (market: Market, ticker: string) =>
    req<UniverseMutationResult>(`/universe/${market}/tickers/${encodeURIComponent(ticker)}`, { method: 'DELETE' }),

  resetUniverse: (market: Market) => req<UniverseInfo>(`/universe/${market}/reset`, { method: 'POST' }),

  getSessions: () => req<Record<Market, MarketSession>>('/universe/session', {}, 4000),

  getAutoScan: () => req<{ mode: AutoScanMode; modes: AutoScanMode[] }>('/universe/autoscan'),

  setAutoScan: (mode: AutoScanMode) =>
    req<{ mode: AutoScanMode; modes: AutoScanMode[] }>('/universe/autoscan', {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify({ mode }),
    }),

  listAlerts: (opts: { limit?: number; sinceId?: number; unreadOnly?: boolean } = {}) =>
    req<AlertList>(
      `/alerts?limit=${opts.limit ?? 50}&since_id=${opts.sinceId ?? 0}&unread_only=${opts.unreadOnly ? 'true' : 'false'}`,
      {},
      5000
    ),

  markRead: (ids: number[] | 'all') =>
    req<{ updated: number; unread_count: number }>('/alerts/read', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(ids === 'all' ? { all: true } : { ids }),
    }),

  clearAlerts: () => req<{ deleted: number }>('/alerts', { method: 'DELETE' }),

  getAlertPrefs: () => req<AlertPrefs>('/alerts/prefs'),

  setAlertPrefs: (patch: { kinds?: Partial<AlertPrefs['kinds']>; os_toast?: boolean }) =>
    req<AlertPrefs>('/alerts/prefs', { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(patch) }),
};
