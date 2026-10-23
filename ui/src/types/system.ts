/** Technical Quality types: OHLCV data-quality report (GET /api/system/data-quality). */

export type DataQualityIssueCode =
  | 'INVALID_PRICE'      // rows with NaN/zero prices dropped
  | 'DUPLICATE_DATE'     // duplicate dates collapsed
  | 'HIGH_LOW_REPAIRED'  // high/low widened to contain open/close
  | 'ZERO_VOLUME'        // holiday/suspension bars excluded from indicators
  | 'BAD_TICK'           // one-bar spike that reverted, dropped
  | 'PRICE_JUMP'         // >35% move that did not revert (likely unadjusted split/rights issue)
  | 'DATE_GAP'           // missing stretch of daily bars
  | 'SHORT_HISTORY';     // fewer than 200 bars

export interface DataQualityIssue {
  code: DataQualityIssueCode;
  severity: 'info' | 'warning' | 'error';
  count: number;
  /** Indonesian, ready to display */
  message: string;
  /** Up to 10 affected dates (YYYY-MM-DD) */
  dates: string[];
}

export type DataQualityGrade = 'GOOD' | 'FAIR' | 'POOR';

export interface DataQualityReport {
  ticker: string;
  interval: string;
  /** When the report was computed (ISO, local time) */
  generated_at: string;
  /** network = fresh download, cache = from SQLite, cache_fallback = network failed, old cache served */
  source: 'network' | 'cache' | 'cache_fallback';
  rows_raw: number;
  rows_clean: number;
  first_date: string | null;
  last_bar_date: string | null;
  /** Most recent completed session date for this ticker's exchange */
  expected_last_date: string | null;
  /** Weekdays between last bar and expected date (holidays not excluded); null if unknown */
  staleness_trading_days: number | null;
  /** staleness >= 2 trading days */
  is_stale: boolean;
  /** Score without the staleness penalty */
  base_score: number;
  /** 0–100, includes staleness penalty */
  score: number;
  grade: DataQualityGrade;
  issues: DataQualityIssue[];
}

export interface DataQualitySummary {
  tickers: number;
  avg_score: number | null;
  stale_count: number;
  poor_count: number;
  /** issue code -> number of tickers having it */
  issue_counts: Partial<Record<DataQualityIssueCode, number>>;
}

export interface DataQualityOverview {
  summary: DataQualitySummary;
  /** Sorted worst score first */
  reports: DataQualityReport[];
}
