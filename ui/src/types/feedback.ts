/** Speed & Feedback types. */
import { ScreenerItem } from './stock';

/** GET /api/screener/progress — live state of the running (or last) scan. */
export interface ScanProgress {
  active: boolean;
  market: string | null;
  total: number;
  done: number;
  failed: number;
  percent: number;
  current_ticker: string | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_sec: number;
  /** Seconds left (estimate); null until the first ticker finished. */
  eta_sec: number | null;
  /** Fatal scan error (scan aborted). */
  error: string | null;
  /** Most recent problem, e.g. a ticker without data. */
  last_error: string | null;
  /** Current step: prepare | download | analysis | news | finalize | done. */
  phase?: string | null;
  phase_label?: string | null;
  failed_tickers: string[];
  result_count: number;
  /** Finished tickers sorted by score (only when include_results=true). */
  results?: ScreenerItem[];
}

export type ApiErrorKind = 'network' | 'timeout' | 'http';

/** Emitted by api/client.ts whenever a call fails. */
export interface ApiErrorEvent {
  /** Stable id of the call, e.g. 'screener', 'watchlist.add'. Used for de-duplication & retry. */
  op: string;
  /** Short human title in Indonesian, e.g. "Gagal memuat screener". */
  title: string;
  /** Human explanation of the cause. */
  message: string;
  kind: ApiErrorKind;
  status?: number;
}

export type EngineConnection = 'online' | 'reconnecting' | 'offline';
