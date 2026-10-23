/** Coverage & Control types. */
export type Market = 'IDX' | 'US';
export type TickerSource = 'watchlist' | 'user' | 'default';

export interface UniverseItem {
  ticker: string;
  sources: TickerSource[];
  scanned: boolean;
}

export interface UniverseInfo {
  market: Market;
  tickers: string[];
  items: UniverseItem[];
  defaults: { ticker: string; removed: boolean }[];
  added: string[];
  removed_defaults: string[];
  watchlist: string[];
  count: number;
  total_requested: number;
  limit: number;
  truncated: boolean;
}

export interface UniverseMutationResult {
  ok: boolean;
  ticker: string;
  message: string;
  universe?: UniverseInfo;
}

export type AutoScanMode = 'market_hours' | 'always' | 'off';

export interface MarketSession {
  market: Market;
  exchange: string;
  is_open: boolean;
  phase: 'open' | 'closed' | 'weekend';
  label: string;
  auto_scan_label: string;
  auto_scan_mode: AutoScanMode;
  local_time: string;
  open_time: string;
  close_time: string;
  tz_label: string;
  next_open: string;
  tz_fallback: boolean;
  note: string | null;
  holidays_modelled: boolean;
  /** BEI: pre_open | session_1 | lunch_break | session_2 | pre_close | post_trading | closed; US: regular | closed */
  session?: string;
  session_name?: string;
  session_ends?: string | null;
  next_session?: string | null;
  trading_day_live?: boolean;
}

export type AlertKind = 'breakout' | 'strong_bullish' | 'stop_loss' | 'target_hit' | 'outflow' | 'entry_zone';

export interface AlertItem {
  id: number;
  created_at: string;
  market: Market;
  ticker: string;
  kind: AlertKind;
  title: string;
  message: string;
  read: boolean;
}

export interface AlertList {
  alerts: AlertItem[];
  unread_count: number;
  latest_id: number;
}

export interface AlertPrefs {
  kinds: Record<AlertKind, boolean>;
  os_toast: boolean;
  labels: Record<AlertKind, string>;
}
