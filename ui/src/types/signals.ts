/** Signal Trust types. */
import type { BrokerSummaryData } from './stock';

export type BacktestHorizon = 5 | 10 | 20;

export interface BacktestBucket {
  bucket: string;
  count: number;
  avg_fwd_ret_pct: number;
  avg_excess_ret_pct: number | null;
  hit_rate_pct: number;
}

export interface BacktestScoreSummary {
  samples: number;
  dates?: number;
  ic: number | null;
  ic_t_stat?: number | null;
  baseline_hit_rate_pct?: number;
  baseline_avg_fwd_ret_pct?: number;
  buckets: BacktestBucket[];
}

export interface BacktestVerdict {
  code: 'NO_EDGE' | 'POSITIVE' | 'NEGATIVE' | 'NO_DATA';
  text: string;
}

/** Trade plans simulated on the bars that followed them (engine/screener/plan_sim.py). */
export interface PlanSimStats {
  plans: number;
  decided: number;
  filled: number;
  fill_rate_pct: number | null;
  not_filled: number;
  cancelled: number;
  closed: number;
  hit_tp1: number;
  hit_tp2: number;
  stopped_out: number;
  expired: number;
  win_rate_pct: number | null;
  avg_r: number | null;
  profit_factor: number | null;
  avg_return_pct: number | null;
  avg_bars_held: number | null;
}

export interface PlanSimSummary {
  rules?: { fill_days: number; fees: string };
  overall: PlanSimStats;
  periods?: {
    in_sample?: PlanSimStats & { until: string };
    out_of_sample?: PlanSimStats & { from: string };
  };
  by_score_bucket?: Record<string, PlanSimStats>;
  by_verdict?: Record<string, PlanSimStats>;
  by_pullback_state?: Record<string, PlanSimStats>;
  by_market_mode?: Record<string, PlanSimStats>;
  by_rr_bucket?: Record<string, PlanSimStats>;
  by_atr_bucket?: Record<string, PlanSimStats>;
  by_tight_room?: Record<string, PlanSimStats>;
  by_wide_stop?: Record<string, PlanSimStats>;
}

export interface BacktestResult {
  ok: boolean;
  market: 'IDX' | 'US';
  horizon_days: number;
  message?: string;
  tickers?: number;
  benchmark_symbol?: string;
  score?: BacktestScoreSummary;
  direction_ic?: number | null;
  verdict?: BacktestVerdict;
  /** Unix seconds. */
  computed_at?: number;
  period_start?: string | null;
  period_end?: string | null;
  plans?: PlanSimSummary;
}

export type BacktestResponse =
  | (BacktestResult & { status: 'ready'; age_sec: number })
  | { status: 'running'; market: string; horizon_days: number; started_at: number; elapsed_sec: number; previous: BacktestResult | null }
  | { status: 'error'; market: string; horizon_days: number; message: string; previous: BacktestResult | null };

/** Historical track record of one category (pullback state / market mode). */
export interface TrackRecordStat {
  count: number;
  hit_rate_pct: number;
  avg_fwd_ret_pct?: number;
  avg_excess_ret_pct?: number | null;
  beat_index_pct?: number | null;
}

export type ReliabilityResponse =
  | { status: 'ready' | 'running' | 'error'; available: false; market: string; horizon_days: number }
  | {
      status: 'ready' | 'running' | 'error';
      available: true;
      market: string;
      horizon_days: number;
      age_sec: number | null;
      period_start: string | null;
      period_end: string | null;
      tickers?: number;
      benchmark_symbol?: string;
      baseline_hit_rate_pct?: number;
      by_pullback_state: Record<string, TrackRecordStat>;
      by_market_mode: Record<string, TrackRecordStat>;
      by_score_bucket: BacktestBucket[];
      verdict?: BacktestVerdict;
    };

/** Broker summary fields added by the Signal Trust backend (NO_DATA instead of simulated rows). */
export interface BrokerSummaryTrust extends BrokerSummaryData {
  data_available?: boolean;
  no_data_reason?: 'NO_KEY' | 'FETCH_FAILED' | 'NOT_IDX';
  no_data_message?: string;
}
