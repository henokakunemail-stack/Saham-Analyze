import type { DataQualityReport } from './system';

export type MoneyFlowStatus =
  | 'STRONG_INFLOW'    // 🟢 Akumulasi Masif
  | 'MILD_INFLOW'      // 🟢 Akumulasi Normal
  | 'NEUTRAL'          // ⚪ Netral
  | 'MILD_OUTFLOW'     // 🟡 Distribusi Halus
  | 'STRONG_OUTFLOW';   // 🔴 Distribusi Masif (Uang Keluar)

export interface FinancialHealth {
  ticker?: string;
  market?: string;
  pe?: number;
  pbv?: number;
  roe?: number;
  debt_to_equity?: number;
  net_margin?: number;
  market_cap?: number;
  health_grade: 'HEALTHY' | 'MODERATE' | 'DISTRESSED';
  health_score: number;
  is_speculative: boolean;
  reasons?: string[];
  updated_at?: string;
}

export interface CandlestickData {
  pattern: string;
  label: string;
  signal: string;
  reliability?: 'HIGH' | 'MEDIUM' | 'LOW';
  description?: string;
}

export type TrendDirection = 'NAIK_KUAT' | 'NAIK' | 'NETRAL' | 'TURUN' | 'TURUN_KUAT';
export type TrendRegime = 'TRENDING_UP' | 'TRENDING_DOWN' | 'RANGING' | 'SQUEEZE' | 'UNKNOWN';

export type PullbackState =
  | 'PULLBACK_IDEAL'
  | 'PULLBACK_DEEP'
  | 'UPTREND_RUNNING'
  | 'UPTREND_EXTENDED'
  | 'TREND_BROKEN'
  | 'NO_UPTREND'
  | 'INSUFFICIENT_DATA';

export type MarketMode = 'NORMAL' | 'CAUTIOUS' | 'BEARISH' | 'CRASH';

export interface PullbackSetup {
  state: PullbackState;
  label: string;
  score: number;
  trend_quality?: number;
  discount?: number;
  long_momentum_pct: number | null;
  relative_momentum_pct?: number | null;
  stretch_atr?: number;
  drawdown_60d_pct?: number;
  structure_intact?: boolean;
  ema50_rising?: boolean;
  above_long_ema?: boolean;
  support_level?: number | null;
  notes: string[];
}

export interface NewsHeadline {
  title: string;
  link?: string;
  source?: string;
  published?: string;
  age_hours?: number | null;
  sentiment?: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  catalysts?: string[];
}

export interface StockReadingPlan {
  stance: 'LAYAK_DIPERTIMBANGKAN' | 'TUNGGU_PEMICU' | 'PANTAU' | 'TUNGGU_PULLBACK' | 'TAHAN' | 'HINDARI' | 'NETRAL'
    | 'LEWAT' | 'BATAL' | 'JANGAN_KEJAR';
  /** The reading before today's live position overrode it (session only). */
  base_stance?: string;
  headline: string;
  triggers: { label: string; met: boolean }[];
  triggers_met: number;
  invalidation?: string | null;
  invalidation_level?: number | null;
  target?: string | null;
  news_note?: string | null;
}

export interface TradeLevels {
  price: number;
  tick: number;
  entry_low: number;
  entry_high: number;
  recommended_entry: number;
  stop_loss: number;
  target_tp1: number;
  target_tp2: number;
  risk_reward_ratio: number;
  risk_pct: number;
  reward_pct: number;
  risk_per_lot?: number | null;
  entry_basis: string;
  stop_basis: string;
  tp1_basis: string;
  tp2_basis: string;
  flags: string[];
  atr14?: number;
  /** Date of the daily close the levels stand on (YYYY-MM-DD). */
  as_of?: string | null;
  /** False when that session was still trading when the levels were computed. */
  bar_final?: boolean | null;
  computed_at?: string | null;
  market?: 'IDX' | 'US';
  /** True while today's session trades: the plan stays the one made from the last final close. */
  frozen?: boolean;
  live?: PlanPosition | null;
  /** Nearest support/resistance on each side (max 3, nearest first), for the chart. */
  ladder?: { supports: LadderLevel[]; resistances: LadderLevel[] };
}

export interface LadderLevel {
  price: number;
  label: string;
}

export type ActionStatus = 'LAYAK' | 'TUNGGU' | 'HINDARI';

/** Is the plan executable now? (engine/screener/actionability.py) */
export interface ActionInfo {
  status: ActionStatus;
  reasons: string[];
  gates: Record<string, boolean>;
}

/** Abnormal trading day (ARA/ARB lock, suspension, corporate action) — engine/collectors/abnormal_days.py */
export interface AbnormalDay {
  date: string;
  kind: string;
  label: string;
}

export type PlanStatus = 'BELOW_STOP' | 'AT_TP2' | 'AT_TP1' | 'IN_ZONE' | 'TESTING_SUPPORT' | 'ABOVE_ZONE';

/** Where today's live price stands against the frozen plan. */
export interface PlanPosition {
  price: number;
  status: PlanStatus;
  label: string;
  touched_stop: boolean;
  touched_tp1: boolean;
  day_high?: number | null;
  day_low?: number | null;
  date?: string;
  /** Distance above the zone in ATR (0 when not above it). */
  dist_atr?: number;
  /** More than 1 ATR above the zone: a limit order in the zone is unlikely to fill today. */
  far_above?: boolean;
  /** False once the target was reached or the cut loss broken today. */
  buyable_today?: boolean;
}

export interface FlowSummary {
  available: boolean;
  disclaimer: string;
  cmf20: number;
  money_flow_status: string;
  obv_trend: number;
  vsa_label?: string;
  up_down_volume_ratio: number | null;
  pressure: 'BELI' | 'JUAL' | 'SEIMBANG';
  pressure_label: string;
  up_days: number;
  down_days: number;
  biggest_volume_day: { date: string; direction: 'NAIK' | 'TURUN' | 'DATAR'; volume_x_avg: number };
}

export interface ScreenMetrics {
  avg_value_20d?: number | null;
  illiquid?: boolean;
  ret_1m?: number | null;
  ret_3m?: number | null;
  ret_6m?: number | null;
  rs_20d?: number | null;
  rs_60d?: number | null;
  dist_52w_high_pct?: number | null;
  dist_ema200_pct?: number | null;
  stretch_atr?: number | null;
  long_momentum_pct?: number | null;
  atr_pct?: number | null;
  market_cap?: number | null;
}

export interface ScorePillars {
  pullback?: number;
  trend?: number;
  money_flow?: number;
  momentum?: number;
  setup?: number;
  fundamental?: number;
  sentiment?: number;
}

export interface TrendDirectionData {
  direction_score: number;
  direction: TrendDirection;
  direction_label: string;
  regime: TrendRegime;
  confidence: number;
  adx: number;
  plus_di?: number;
  minus_di?: number;
  adx_rising?: boolean;
  components: Record<string, number>;
  market_structure?: string;
  break_of_structure?: 'BULLISH_BOS' | 'BEARISH_BOS' | 'NONE';
  last_swing_high?: number | null;
  last_swing_low?: number | null;
  weekly_trend?: string;
  rsi_divergence?: 'BULLISH' | 'BEARISH' | 'NONE';
  squeeze?: boolean;
  rs_20d_pct?: number;
  rs_60d_pct?: number;
  pullback?: PullbackSetup;
  notes: string[];
}

export interface ScreenerItem {
  ticker: string;
  market: 'IDX' | 'US';
  price: number;
  change_pct: number;
  ema20: number;
  ema50: number;
  ema200: number;
  rsi14: number;
  macd_hist: number;
  cmf20: number;
  vol_ratio: number;
  money_flow_status: MoneyFlowStatus;
  vsa_signal?: string;
  vsa_label?: string;
  vsa_desc?: string;
  spread_ratio?: number;
  sentiment_score: number;
  catalyst: string;
  score: number;
  verdict: string;
  badge_text: string;
  reasons: string[];
  is_confirmed_breakout?: boolean;
  confluence_score?: number;
  confluence_gates?: Record<string, boolean>;
  risk_reward_ratio?: number;
  target_tp?: number;
  target_tp1?: number;
  target_tp2?: number;
  stop_loss?: number;
  entry_low?: number;
  entry_high?: number;
  recommended_entry?: number;
  atr14?: number;
  candlestick?: CandlestickData;
  health_grade?: 'HEALTHY' | 'MODERATE' | 'DISTRESSED';
  health_score?: number;
  is_speculative?: boolean;
  roe?: number;
  net_margin?: number;
  debt_to_equity?: number;
  pe?: number;
  pbv?: number;
  direction_score?: number;
  direction?: TrendDirection;
  direction_label?: string;
  trend_regime?: TrendRegime;
  trend_confidence?: number;
  adx?: number;
  direction_notes?: string[];
  pillars?: ScorePillars;
  market_mode?: MarketMode;
  pullback_state?: PullbackState;
  pullback_label?: string;
  reading?: StockReadingPlan | null;
  news_headlines?: NewsHeadline[];
  sentiment_label?: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  news_checked_at?: string | null;
  levels?: TradeLevels | null;
  screen?: ScreenMetrics | null;
  /** Fase 1–4 */
  action?: ActionInfo | null;
  rank?: number;
  raw_score?: number;
  pillar_values?: Record<string, number>;
  abnormal_recent?: AbnormalDay[];
  sector?: string | null;
  sector_rank?: number | null;
}

export interface CandlePoint {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface VolumePoint {
  time: string | number;
  value: number;
  color: string;
}

export interface CmfPoint {
  time: string | number;
  value: number;
}

export interface ChartData {
  ticker: string;
  interval?: string;
  candles: CandlePoint[];
  volume: VolumePoint[];
  cmf: CmfPoint[];
  /** Abnormal trading days (ARA/ARB, suspension, corporate action) as chart markers. */
  markers?: { time: string; kind: string; label: string }[];
}

export interface NewsItem {
  title: string;
  link: string;
  published: string;
  source: string;
  summary?: string;
}

export interface StockAnalysis {
  ticker: string;
  technical: {
    price: number;
    change_pct: number;
    ema20: number;
    ema50: number;
    ema200: number;
    rsi14: number;
    macd_line: number;
    macd_signal: number;
    macd_hist: number;
    vol_ratio: number;
    is_breakout: boolean;
    atr14?: number;
    entry_low?: number;
    entry_high?: number;
    recommended_entry?: number;
    candlestick?: CandlestickData;
  };
  money_flow: {
    cmf20: number;
    obv: number;
    obv_divergence: string;
    vsa_signal: string;
    vsa_label?: string;
    vsa_desc?: string;
    spread_ratio?: number;
    money_flow_status: MoneyFlowStatus;
  };
  sentiment: {
    sentiment_score: number;
    sentiment_label: string;
    catalyst: string;
    article_count: number;
  };
  composite: {
    score: number;
    verdict: string;
    badge_text: string;
    reasons: string[];
    is_confirmed_breakout?: boolean;
    confluence_score?: number;
    confluence_gates?: Record<string, boolean>;
    risk_reward_ratio?: number;
    target_tp?: number;
    target_tp1?: number;
    target_tp2?: number;
    stop_loss?: number;
    entry_low?: number;
    entry_high?: number;
    recommended_entry?: number;
    is_speculative?: boolean;
    pillars?: ScorePillars;
    market_mode?: MarketMode;
    pullback_state?: PullbackState;
    pullback_label?: string;
    levels?: TradeLevels | null;
    raw_score?: number;
    pillar_values?: Record<string, number>;
    pillar_weights?: Record<string, number>;
    action?: ActionInfo | null;
  };
  abnormal_recent?: AbnormalDay[];
  sector?: string | null;
  direction?: TrendDirectionData;
  flow_summary?: FlowSummary | null;
  market_regime?: TrendDirectionData | null;
  financials?: FinancialHealth;
  broker_summary?: BrokerSummaryData;
  news: NewsItem[];
  data_quality?: DataQualityReport | null;
}

export interface BrokerItem {
  broker: string;
  name: string;
  type: 'FOREIGN' | 'DOMESTIC_INSTITUTION' | 'RETAIL';
  bval?: number;
  bvol?: number;
  sval?: number;
  svol?: number;
  avg_price?: number;
}

export interface BrokerSummaryData {
  ticker: string;
  trade_date: string;
  source: string;
  top_buyers: BrokerItem[];
  top_sellers: BrokerItem[];
  net_foreign_val: number;
  bandar_status: string;
  bandar_status_label: string;
  bandar_avg_price: number;
  top3_ratio: number;
  summary_notes: string[];
  is_simulated?: boolean;
}

export interface MarketIndex {
  price: number;
  change_pct: number;
  symbol: string;
}

export interface WatchlistItem {
  ticker: string;
  name?: string;
  market?: string;
  added_at?: string;
  notes?: string;
}

export interface AISettings {
  provider: string;
  base_url: string;
  model: string;
  is_api_key_set: boolean;
  masked_api_key: string;
  api_key?: string;
  is_sectors_key_set?: boolean;
  masked_sectors_key?: string;
  sectors_api_key?: string;
  anthropic_model?: string;
  is_anthropic_key_set?: boolean;
  masked_anthropic_key?: string;
  anthropic_auth_mode?: 'api_key' | 'login';
}

export interface AiModelInfo {
  id: string;
  label?: string;
  context_length?: number | null;
  max_output?: number | null;
  reasoning?: boolean | null;
  vision?: boolean | null;
  tools?: boolean | null;
}

export interface AiModelsResponse {
  ok: boolean;
  models: string[];
  combos: AiModelInfo[];
  groups: { provider: string; label: string; models: AiModelInfo[] }[];
  message: string;
  alias_count?: number;
}

export interface AIValidationResult {
  ok: boolean;
  error?: string;
  confidence_score?: number;
  verdict?: string;
  bullish_thesis?: string;
  bull_trap_risk?: 'LOW' | 'MEDIUM' | 'HIGH';
  bull_trap_analysis?: string;
  entry_zone?: string;
  stop_loss?: string;
  target_tp1?: string;
  target_tp2?: string;
  key_catalyst?: string;
  model_used?: string;
  /** Time the model took to answer (ms). */
  elapsed_ms?: number;
}

export type PredictionStatus =
  | 'HIT_TP2'
  | 'HIT_TP1'
  | 'STOPPED_OUT'
  | 'EXPIRED'
  | 'IN_PROGRESS'
  /** Executable plans: the buy limit was never reached / the price opened under the stop first / still waiting. */
  | 'NOT_FILLED'
  | 'CANCELLED'
  | 'WAITING_ENTRY';

export interface PredictionItem {
  id?: number;
  snapshot_date: string;
  market: 'IDX' | 'US';
  ticker: string;
  rank: number;
  score: number;
  verdict: string;
  badge_text: string;
  price_at_prediction: number;
  recommended_entry: number;
  entry_low?: number;
  entry_high?: number;
  target_tp1: number;
  target_tp2: number;
  stop_loss: number;
  risk_reward_ratio: number;
  money_flow_status: MoneyFlowStatus;
  reasons: string[];
  confluence_score: number;
  current_price: number;
  max_price: number;
  min_price: number;
  /** Realised return for closed predictions (exit at TP/SL/horizon close), mark-to-market for IN_PROGRESS. */
  return_pct: number;
  /** Latest close vs prediction price, regardless of status. */
  current_return_pct?: number;
  max_return_pct: number;
  status: PredictionStatus;
  is_closed?: boolean;
  exit_price?: number | null;
  exit_date?: string | null;
  hit_date?: string | null;
  days_elapsed: number;
  eval_days?: number;
  horizon_days?: number;
  benchmark_return_pct?: number | null;
  excess_return_pct?: number | null;
  /** True when evaluated as an executable plan (buy limit first); false for old snapshots. */
  plan_checked?: boolean;
  filled?: boolean;
  fill_price?: number | null;
  fill_date?: string | null;
  touched_zone?: boolean;
  r_multiple?: number | null;
}

export interface PredictionSummary {
  total_predictions: number;
  horizon_days?: number;
  closed_count?: number;
  win_count: number;
  hit_tp1_count: number;
  hit_tp2_count: number;
  stopped_out_count: number;
  expired_count?: number;
  expired_positive_count?: number;
  in_progress_count: number;
  /** TP hits / closed predictions; null when nothing is closed yet. */
  win_rate_pct: number | null;
  /** Average return of closed predictions; null when nothing is closed yet. */
  avg_return_pct: number | null;
  avg_open_return_pct?: number | null;
  benchmark_symbol?: string;
  benchmark_avg_return_pct?: number | null;
  avg_excess_return_pct?: number | null;
  beat_benchmark_count?: number;
  benchmark_compared_count?: number;
  not_filled_count?: number;
  cancelled_count?: number;
  waiting_entry_count?: number;
  /** Plans bought in the entry zone / plans decided; null when every plan was filled or none is decided. */
  fill_rate_pct?: number | null;
  avg_r?: number | null;
}

export interface PredictionHistoryResponse {
  snapshot_date: string;
  market: 'IDX' | 'US';
  horizon_days?: number;
  summary: PredictionSummary;
  items: PredictionItem[];
  available_dates: string[];
}

export interface ScanStatus {
  is_scanning: boolean;
  last_scan_time: string | null;
  last_scan_market: string | null;
  next_scan_in_sec: number;
  scan_count: number;
}

export interface PlanCheckpointRow extends PlanPosition {
  ticker: string;
  source: 'Top 10' | 'Watchlist';
  as_of?: string | null;
  entry_low: number;
  entry_high: number;
  /** Buy-limit price the plan/backtest assumes (sent by newer engines). */
  recommended_entry?: number | null;
  stop_loss: number;
  target_tp1: number;
  target_tp2: number;
}

export type RecapOutcome = 'STOP' | 'TP2' | 'TP1' | 'FILLED' | 'ZONE' | 'ABOVE';

/** One stock: the last session's bar read against the plan it traded on. */
export interface SessionRecapRow {
  ticker: string;
  source: 'Top 10' | 'Watchlist';
  outcome: RecapOutcome;
  text: string;
  /** The buy limit (recommended entry) was reached during the session. */
  filled: boolean;
  session_date: string;
  plan_as_of?: string | null;
  open: number;
  high: number;
  low: number;
  close: number;
  change_pct?: number | null;
  entry_low: number;
  entry_high: number;
  recommended_entry?: number | null;
  stop_loss: number;
  target_tp1: number;
  target_tp2: number;
}

export interface SessionRecap {
  session_date: string | null;
  /** Whether the session's daily bar is final (BEI: ±16:45 WIB). */
  final?: boolean | null;
  plan_as_of?: string | null;
  /** Date of the remembered Top 10 the recap covers (null: today's list was used). */
  list_from_plan?: string | null;
  rows: SessionRecapRow[];
  counts: Record<RecapOutcome, number>;
  filled: number;
}

export interface PlanCheckpoint {
  session: import('./universe').MarketSession;
  live: boolean;
  rows: PlanCheckpointRow[];
  message?: string | null;
  checked_at?: string;
  /** After the close: what the last session did to the plans it traded on. */
  recap?: SessionRecap | null;
}
