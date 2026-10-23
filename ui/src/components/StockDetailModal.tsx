import React, { useEffect, useRef, useState } from 'react';
import { ChartData, StockAnalysis, AIValidationResult } from '../types/stock';
import { api } from '../api/client';
import { universeApi } from '../api/universe';
import { ChartView } from './ChartView';
import { CmfOscillatorChart } from './CmfOscillatorChart';
import { InflowBadge } from './InflowBadge';
import { BrokerSummarySection } from './BrokerSummarySection';
import { FlowSummaryCard, LevelBasis } from './FlowSummaryCard';
import { TrendDirectionPanel } from './TrendDirectionPanel';
import { InfoTip } from './help/InfoTip';
import { GlossaryButton } from './help/GlossaryDrawer';
import { PlainSummaryCard } from './help/PlainSummaryCard';
import { SignalTrackRecord } from './SignalTrackRecord';
import { AbnormalDaysChip } from './AbnormalDaysChip';
import { ActionStatusBadge } from './ActionStatusBadge';
import { DecisionStrip } from './DecisionStrip';
import { StatementsSection } from './StatementsSection';
import { PillarBars } from './PillarBars';
import { fmtNum, fmtPct, fmtPrice, fmtSigned } from './help/format';
import { GATE_LABELS, getTerm } from '../lib/glossary';
import {
  X,
  Star,
  ExternalLink,
  Activity,
  Flame,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  CheckCircle2,
  Bot,
  AlertTriangle,
  Target,
  Compass,
  RefreshCw,
  DollarSign,
  TrendingUp,
  Info
} from 'lucide-react';

interface Props {
  ticker: string;
  market: 'IDX' | 'US';
  onClose: () => void;
  isPinned: boolean;
  onToggleWatchlist: (ticker: string) => void;
  onOpenSettings?: () => void;
}

/** Background chart refresh: intraday every 20 s, daily every 60 s (and only while the exchange trades). */
const INTRADAY_POLL_MS = 20000;
const DAILY_POLL_MS = 60000;

const readFlag = (key: string, fallback: boolean): boolean => {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v === '1';
  } catch {
    return fallback;
  }
};

const writeFlag = (key: string, value: boolean): boolean => {
  try {
    localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* per-viewer convenience only */
  }
  return value;
};

export const StockDetailModal: React.FC<Props> = ({
  ticker,
  market,
  onClose,
  isPinned,
  onToggleWatchlist,
  onOpenSettings,
}) => {
  const [chartData, setChartData] = useState<ChartData | null>(null);
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [aiValidation, setAiValidation] = useState<AIValidationResult | null>(null);
  const [aiLoading, setAiLoading] = useState<boolean>(false);
  const [aiSeconds, setAiSeconds] = useState(0);
  const [timeframe, setTimeframe] = useState<'1d' | '1h' | '15m' | '5m'>('1d');
  const timeframeRef = useRef(timeframe);
  timeframeRef.current = timeframe;
  // Mousedown on the backdrop itself (a drag that starts inside the dialog must not close it)
  const backdropDownRef = useRef(false);
  // Chart overlays, remembered per viewer
  const [showPlan, setShowPlan] = useState<boolean>(() => readFlag('saham.chart.showPlan', true));
  const [showLadder, setShowLadder] = useState<boolean>(() => readFlag('saham.chart.showLadder', false));
  const togglePlan = () => setShowPlan((v) => writeFlag('saham.chart.showPlan', !v));
  const toggleLadder = () => setShowLadder((v) => writeFlag('saham.chart.showLadder', !v));
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Keyboard: Esc menutup; fokus masuk ke dialog saat dibuka dan kembali ke pemicu saat ditutup.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previouslyFocused?.focus?.();
    };
  }, []);

  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !dialogRef.current) return;
    const nodes = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, iframe, [tabindex]:not([tabindex="-1"])')
    ).filter((n) => !n.hasAttribute('disabled') && n.offsetParent !== null);
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    if (!dialogRef.current.contains(active)) return; // fokus di tooltip/glosarium (portal)
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  /** Returns false when the chart could not be loaded. silent: background poll, no error toast. */
  const loadChartData = async (tf = timeframe, force = false, silent = false): Promise<boolean> => {
    try {
      const chart = await api.getStockChart(ticker, market, tf, force, silent);
      // A slow reply for an interval the user already left must not replace the current chart
      if (chart && timeframeRef.current === tf) setChartData(chart);
      return Boolean(chart);
    } catch (e) {
      console.error(e);
      return false;
    }
  };

  const handleTimeframeChange = async (tf: typeof timeframe) => {
    if (tf === timeframe) return;
    const prev = timeframe;
    timeframeRef.current = tf;
    setTimeframe(tf);
    const ok = await loadChartData(tf, false);
    // Failed switch: go back to the interval whose data is still on screen
    if (!ok && timeframeRef.current === tf) {
      timeframeRef.current = prev;
      setTimeframe(prev);
    }
  };

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await Promise.all([
      loadChartData(timeframe, true),
      api.getStockAnalysis(ticker, market, true).then((ana) => ana && setAnalysis(ana)),
    ]);
    setRefreshing(false);
  };

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setAiValidation(null);

    Promise.all([
      api.getStockChart(ticker, market, timeframe, false),
      api.getStockAnalysis(ticker, market, false),
    ]).then(([chart, ana]) => {
      if (!isMounted) return;
      setChartData(chart);
      setAnalysis(ana);
      setLoading(false);
    });

    return () => {
      isMounted = false;
    };
  }, [ticker, market]);

  useEffect(() => {
    // Silent background refresh from the engine cache (force=false). The daily bar only changes
    // while the exchange trades, so the daily chart is not polled outside the trading day.
    const daily = timeframe === '1d';
    const intervalId = window.setInterval(async () => {
      if (document.hidden) return;
      if (daily) {
        try {
          const s = (await universeApi.getSessions())[market];
          if (s && !(s.trading_day_live ?? s.is_open)) return;
        } catch {
          /* session unknown: refresh anyway */
        }
      }
      loadChartData(timeframe, false, true);
    }, daily ? DAILY_POLL_MS : INTRADAY_POLL_MS);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, market, timeframe]);

  // Seconds counter while the model answers (usually 8-15 s through 9router)
  useEffect(() => {
    if (!aiLoading) return;
    setAiSeconds(0);
    const id = window.setInterval(() => setAiSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [aiLoading]);

  const handleRunAiValidation = async () => {
    setAiLoading(true);
    const res = await api.validateSignal(ticker, market);
    setAiValidation(res);
    setAiLoading(false);
  };

  const currentPrice = analysis?.technical?.price ?? 0;
  const changePct = analysis?.technical?.change_pct ?? 0;
  const isPos = changePct >= 0;
  const isConfirmed = analysis?.composite?.is_confirmed_breakout;
  const isSpeculative = Boolean(analysis?.composite?.is_speculative || analysis?.financials?.is_speculative);
  const financials = analysis?.financials;

  const formatCurrency = (val?: number) => fmtPrice(val);

  const MONEY_FLOW_LABELS: Record<string, string> = {
    STRONG_INFLOW: '▲▲ Akumulasi masif',
    MILD_INFLOW: '▲ Akumulasi',
    NEUTRAL: '■ Netral',
    MILD_OUTFLOW: '▼ Distribusi',
    STRONG_OUTFLOW: '▼▼ Distribusi masif',
  };
  const OBV_LABELS: Record<string, string> = {
    BULLISH_ACCUMULATION: '▲ Akumulasi tersembunyi',
    BEARISH_DISTRIBUTION: '▼ Distribusi tersembunyi',
    NONE: '■ Searah harga',
  };
  const rsiHint = (rsi?: number) =>
    rsi === undefined ? '' : rsi > 70 ? 'jenuh beli' : rsi < 30 ? 'jenuh jual' : rsi >= 45 && rsi <= 65 ? 'sehat' : 'netral';

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onMouseDown={(e) => {
        backdropDownRef.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (backdropDownRef.current && e.target === e.currentTarget) onClose();
        backdropDownRef.current = false;
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="stock-detail-title"
        onKeyDown={trapTab}
        className="w-full max-w-6xl max-h-[92vh] bg-surface border border-borderMuted rounded-2xl flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
      >
        {/* Header Bar */}
        <div className="p-4 border-b border-borderMuted flex items-center justify-between bg-[#090D16]">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 id="stock-detail-title" className="text-xl font-extrabold font-mono text-white">
              {ticker}
              <span className="sr-only"> — detail analisa</span>
            </h2>
            {analysis?.composite?.action && <ActionStatusBadge status={analysis.composite.action.status} />}
            {isConfirmed && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">
                Sinyal kuat (konfluensi)
                <InfoTip term="confluence" />
              </span>
            )}
            {analysis && (
              <>
                <span className="font-mono text-base font-bold text-gray-200">
                  {formatCurrency(currentPrice)}
                </span>
                <span
                  className={`font-mono text-xs font-bold ${
                    isPos ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  (<span aria-hidden="true">{isPos ? '▲' : '▼'} </span>{fmtPct(changePct)})
                </span>
                <InflowBadge status={analysis.money_flow.money_flow_status} cmf={analysis.money_flow.cmf20} info />

                {/* Financial Health Header Pill */}
                {isSpeculative ? (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                    ⚠️ Spekulatif (rugi/utang tinggi) <InfoTip term="speculative" className="ml-0.5" />
                  </span>
                ) : financials?.health_grade === 'HEALTHY' ? (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
                    🛡️ Keuangan sehat ({financials.health_score}/100)
                  </span>
                ) : financials?.health_grade === 'DISTRESSED' ? (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                    ⚠️ Keuangan tertekan
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                    ⚖️ Keuangan stabil
                  </span>
                )}

                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-slate-800 text-white border border-slate-700">
                  Skor: <span className="text-white">{analysis.composite.score ?? '-'}</span>/100
                  <InfoTip term="composite_score" />
                </span>
                {analysis.data_quality && analysis.data_quality.grade !== 'GOOD' && (
                  <span
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-200 border border-amber-500/40"
                    title={analysis.data_quality.issues.map((i) => i.message).join(' · ')}
                  >
                    <span aria-hidden="true">⚠</span>
                    DATA {analysis.data_quality.is_stale ? 'TERLAMBAT' : 'KURANG BERSIH'} ({analysis.data_quality.score}/100)
                  </span>
                )}
                <AbnormalDaysChip items={analysis.abnormal_recent} />
                {analysis.composite.market_mode && analysis.composite.market_mode !== 'NORMAL' && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/15 text-rose-200 border border-rose-500/40">
                    <span aria-hidden="true">▼</span>
                    {({ CAUTIOUS: 'PASAR WASPADA', BEARISH: 'PASAR BEARISH', CRASH: 'PASAR KRISIS' } as Record<string, string>)[
                      analysis.composite.market_mode as string
                    ] ?? `PASAR ${analysis.composite.market_mode}`}
                    <InfoTip term="market_mode" />
                  </span>
                )}
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            <GlossaryButton compact />
            <button
              onClick={handleRunAiValidation}
              disabled={aiLoading}
              className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-600/30 to-emerald-500/30 border border-purple-500/40 text-purple-200 hover:text-white hover:border-purple-400 text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm"
              title="Minta model AI (diatur di Pengaturan) menilai ulang sinyal ini"
            >
              {aiLoading ? (
                <>
                  <Activity className="w-3.5 h-3.5 animate-spin text-purple-300" />
                  <span>Menganalisa... {aiSeconds} dtk</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                  <span>Validasi AI</span>
                </>
              )}
            </button>
            <button
              onClick={() => onToggleWatchlist(ticker)}
              className={`p-2 rounded-lg border transition-all ${
                isPinned
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                  : 'bg-surface border-borderMuted text-gray-400 hover:text-white'
              }`}
              title="Pin ke Watchlist"
              aria-label={isPinned ? 'Hapus dari watchlist' : 'Tambah ke watchlist'}
              aria-pressed={isPinned}
            >
              <Star className={`w-4 h-4 ${isPinned ? 'fill-amber-400' : ''}`} />
            </button>
            <button
              ref={closeBtnRef}
              onClick={onClose}
              aria-label="Tutup detail (Esc)"
              title="Tutup (Esc)"
              className="p-2 rounded-lg bg-surface border border-borderMuted text-gray-400 hover:text-white hover:bg-slate-800 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/70"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading ? (
            <div className="h-96 flex flex-col items-center justify-center gap-3 text-gray-400">
              <Activity className="w-8 h-8 text-emerald-400 animate-spin" />
              <p className="text-xs font-mono">Memuat chart kuantitatif & analisa kesehatan saham...</p>
            </div>
          ) : (
            <>
              {/* Analysis failed to load: say so and offer a retry (the chart may still be shown) */}
              {!analysis && (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 flex items-center justify-between gap-3" role="alert">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                    <span>Gagal memuat analisis {ticker}.</span>
                  </div>
                  <button
                    onClick={handleManualRefresh}
                    disabled={refreshing}
                    className="px-3 py-1.5 rounded-lg bg-rose-500/20 border border-rose-500/40 text-rose-100 hover:bg-rose-500/30 font-semibold flex items-center gap-1.5 disabled:opacity-60"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                    Coba lagi
                  </button>
                </div>
              )}

              {/* What to do today: status, reason, the order to place */}
              {analysis && (
                <DecisionStrip
                  action={analysis.composite.action}
                  reading={analysis.composite.reading}
                  levels={analysis.composite.levels}
                  buy={analysis.composite.recommended_entry ?? analysis.technical.recommended_entry}
                  stop={analysis.composite.stop_loss}
                  tp1={analysis.composite.target_tp1}
                  tp2={analysis.composite.target_tp2}
                  rr={analysis.composite.risk_reward_ratio}
                />
              )}

              {/* Ringkasan bahasa awam */}
              {analysis && <PlainSummaryCard analysis={analysis} />}

              {/* Rekam jejak historis sinyal serupa */}
              {analysis && (
                <SignalTrackRecord
                  market={market}
                  score={analysis.composite.score}
                  pullbackState={analysis.composite.pullback_state ?? analysis.direction?.pullback?.state}
                  pullbackLabel={analysis.composite.pullback_label ?? analysis.direction?.pullback?.label}
                  marketMode={analysis.composite.market_mode}
                />
              )}

              {/* AI Validation Card */}
              {aiValidation && (
                <div className="p-4 rounded-xl bg-gradient-to-b from-[#141026] to-[#0A0D18] border border-purple-500/40 shadow-xl space-y-3">
                  <div className="flex items-center justify-between border-b border-purple-500/20 pb-2">
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-purple-400" />
                      <h3 className="text-xs font-extrabold uppercase tracking-wider text-purple-200">
                        Pendapat AI ({aiValidation.model_used || 'AI'}
                        {aiValidation.elapsed_ms ? ` · ${(aiValidation.elapsed_ms / 1000).toFixed(1)} dtk` : ''})
                      </h3>
                    </div>
                    {aiValidation.confidence_score && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">Keyakinan model AI:</span>
                        <span
                          className="px-2.5 py-0.5 rounded-full text-xs font-mono font-extrabold bg-slate-800 text-gray-100 border border-slate-600"
                          title="Penilaian subjektif model bahasa, bukan probabilitas yang terukur secara statistik."
                        >
                          {aiValidation.confidence_score}%
                        </span>
                      </div>
                    )}
                  </div>

                  {aiValidation.error ? (
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                      {aiValidation.error}
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                      {/* Left: Thesis & Bull-Trap */}
                      <div className="space-y-2.5">
                        <div>
                          <div className="text-[11px] font-bold text-gray-400 uppercase">Tesis Kenaikan:</div>
                          <p className="text-gray-200 mt-1 leading-relaxed bg-black/20 p-2.5 rounded-lg border border-slate-800">
                            {aiValidation.bullish_thesis}
                          </p>
                        </div>

                        {/* Bull Trap Alert */}
                        <div className={`p-2.5 rounded-lg border flex items-start gap-2 ${
                          aiValidation.bull_trap_risk === 'LOW'
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                            : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                        }`}>
                          <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                          <div>
                            <div className="font-bold">
                              Deteksi Bull-Trap: {aiValidation.bull_trap_risk === 'LOW' ? 'RISIKO RENDAH (Akumulasi Murni)' : 'RISIKO TINGGI (Waspada Pancingan)'}
                            </div>
                            <div className="text-[11px] mt-0.5 opacity-90">
                              {aiValidation.bull_trap_analysis}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Right: the AI's own levels — a second opinion, not the plan */}
                      <div className="space-y-2.5">
                        <div className="p-3 rounded-lg bg-black/30 border border-slate-800 space-y-2">
                          <div className="text-[11px] font-bold text-gray-400 flex items-center gap-1.5">
                            <Target className="w-3.5 h-3.5 text-purple-300" />
                            <span>Pendapat AI soal level (pembanding, bukan rencana resmi)</span>
                          </div>
                          <p className="font-mono text-[11px] text-gray-200 leading-relaxed">
                            Zona {aiValidation.entry_zone || '-'} · cut loss{' '}
                            <span className="text-rose-300">{aiValidation.stop_loss || '-'}</span> · target{' '}
                            <span className="text-emerald-300">{aiValidation.target_tp1 || '-'}</span>
                            {aiValidation.target_tp2 ? <> / {aiValidation.target_tp2}</> : null}
                          </p>
                          <p className="text-[11px] text-gray-400">
                            Rencana resmi (yang diuji historis) ada di kotak "Keputusan hari ini" di atas.
                          </p>
                          {aiValidation.key_catalyst && (
                            <div className="text-[11px] text-gray-300 pt-1">
                              <span className="text-gray-400">Katalis Utama:</span> {aiValidation.key_catalyst}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Chart header: interval + refresh (in-app chart, data from the SAHAM engine) */}
              <div className="flex items-center justify-between flex-wrap gap-2 pt-1 pb-1">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-300">
                  <span>📈 Grafik Harga & Aliran Uang (CMF)</span>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[11px] text-gray-400 font-mono hidden sm:inline">Interval:</span>
                  {(['1d', '1h', '15m', '5m'] as const).map((tf) => (
                    <button
                      key={tf}
                      onClick={() => handleTimeframeChange(tf)}
                      aria-pressed={timeframe === tf}
                      className={`px-2.5 py-1 rounded text-xs font-mono font-bold transition-all ${
                        timeframe === tf
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                          : 'bg-surface border border-borderMuted text-gray-400 hover:text-white'
                      }`}
                    >
                      {tf.toUpperCase()}
                    </button>
                  ))}

                  <span className="mx-1 h-4 w-px bg-borderMuted hidden sm:inline-block" />
                  {(
                    [
                      ['Rencana', showPlan, togglePlan, 'Garis zona beli, cut loss, TP1/TP2'],
                      ['Support/Resistance', showLadder, toggleLadder, 'Garis support & resistance terdekat'],
                    ] as const
                  ).map(([label, on, toggle, title]) => (
                    <button
                      key={label}
                      onClick={toggle}
                      title={title}
                      aria-pressed={on}
                      className={`px-2 py-1 rounded text-[11px] font-semibold border transition-all ${
                        on ? 'bg-sky-500/15 text-sky-300 border-sky-500/40' : 'bg-surface border-borderMuted text-gray-500 hover:text-white'
                      }`}
                    >
                      {label}
                    </button>
                  ))}

                  <button
                    onClick={handleManualRefresh}
                    disabled={refreshing}
                    className="p-1.5 rounded bg-surface border border-borderMuted text-gray-400 hover:text-white hover:bg-slate-800 transition-all ml-1 flex items-center gap-1 text-xs"
                    title="Muat ulang data grafik"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-emerald-400' : ''}`} />
                    <span className="hidden sm:inline">Refresh</span>
                  </button>
                </div>
              </div>

              {/* Price + volume chart and CMF oscillator */}
              <div className="space-y-2">
                {chartData ? (
                  <>
                    <ChartView
                      data={chartData}
                      height={360}
                      levels={analysis?.composite?.levels ?? null}
                      showPlan={showPlan}
                      showLadder={showLadder}
                      markers={chartData.markers ?? null}
                    />
                    {chartData.cmf && chartData.cmf.length > 0 && (
                      <CmfOscillatorChart cmfData={chartData.cmf} height={130} />
                    )}
                  </>
                ) : (
                  <div className="h-[360px] rounded-xl border border-dashed border-borderMuted flex items-center justify-center text-xs text-gray-500">
                    Data grafik belum tersedia untuk interval ini.
                  </div>
                )}
              </div>

              {/* 🎯 TRADING SETUP BOX: Realistic ATR Entry, TP, Cut Loss & Candlestick */}
              {analysis && (
                <div className="p-4 rounded-xl bg-gradient-to-r from-[#0E1526] via-[#090D16] to-[#0E1526] border border-emerald-500/30 shadow-lg space-y-3">
                  <div className="flex items-center justify-between border-b border-borderMuted pb-2 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <Compass className="w-4 h-4 text-emerald-400" />
                      <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                        Dasar rencana: dari mana angka-angka ini
                      </h3>
                    </div>
                    {analysis.technical.candlestick && (
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-gray-200 border border-slate-700">
                        🕯️ {analysis.technical.candlestick.label}
                      </span>
                    )}
                  </div>

                  {analysis.technical.candlestick?.description && (
                    <div className="text-xs space-y-0.5">
                      <p className="text-gray-300">{analysis.technical.candlestick.description}</p>
                      {analysis.technical.candlestick.evidence && (
                        <p
                          className={
                            analysis.technical.candlestick.evidence.verdict === 'terbukti' ? 'text-sky-300' : 'text-amber-300'
                          }
                        >
                          {analysis.technical.candlestick.evidence.text}
                        </p>
                      )}
                    </div>
                  )}

                  {/* The numbers themselves are in "Keputusan hari ini" at the top; here: where they come from */}
                  <LevelBasis levels={analysis.composite.levels} withNow={false} />
                  {analysis.technical.atr14 ? (
                    <p className="text-[11px] text-gray-400 flex items-center gap-1">
                      Gerak harian normal (ATR 14): {fmtNum(analysis.technical.atr14, 2)} <InfoTip term="atr" />
                    </p>
                  ) : null}

                  {/* Signal strength (confluence) is a different question from "may I buy": keep it folded */}
                  {analysis.composite.confluence_gates && Object.keys(analysis.composite.confluence_gates).length > 0 && (
                    <details className="rounded-lg border border-borderMuted/70 bg-[#090D16]/50 px-3 py-1.5">
                      <summary className="cursor-pointer select-none text-[11px] font-semibold text-gray-300 hover:text-white">
                        Kekuatan sinyal (konfluensi): {analysis.composite.confluence_score ?? 0}/6 gerbang lolos
                      </summary>
                      <div className="pt-2 space-y-1.5">
                        <p className="text-[11px] text-gray-400 flex items-center gap-1">
                          Mengukur seberapa banyak faktor yang searah — bukan izin membeli; itu ditentukan status di atas.
                          <InfoTip term="confluence" />
                        </p>
                        <ul className="flex flex-wrap gap-1.5">
                          {Object.entries(analysis.composite.confluence_gates).map(([key, ok]) => (
                            <li
                              key={key}
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-semibold ${
                                ok
                                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                                  : 'bg-slate-800 text-gray-300 border-slate-700'
                              }`}
                            >
                              <span aria-hidden="true">{ok ? '✓' : '✗'}</span>
                              <span className="sr-only">{ok ? 'Lolos:' : 'Belum lolos:'}</span>
                              {GATE_LABELS[key] ?? key}
                              <InfoTip term={key} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    </details>
                  )}
                  {analysis.composite.pillar_values && Object.keys(analysis.composite.pillar_values).length > 0 && (
                    <div className="space-y-1">
                      <div className="text-[11px] uppercase tracking-wider text-gray-400 font-bold flex items-center gap-1">
                        Komponen skor <InfoTip term="composite_score" />
                        {analysis.composite.raw_score !== undefined && analysis.composite.raw_score !== analysis.composite.score && (
                          <span className="normal-case font-normal text-gray-400">
                            {' '}· skor asli {analysis.composite.raw_score}, dipotong ke {analysis.composite.score} oleh rem pasar
                          </span>
                        )}
                      </div>
                      <PillarBars values={analysis.composite.pillar_values} weights={analysis.composite.pillar_weights} />
                    </div>
                  )}
                  <p className="text-[11px] text-gray-400">
                    Level dihitung dari support/resistance nyata dan dibulatkan ke fraksi harga bursa — hitungan mekanis,
                    bukan saran beli/jual.
                  </p>
                </div>
              )}

              {/* 🏛️ Broker Summary & Bandarmologi Section */}
              {/* Real broker data only; otherwise a price & volume flow summary (clearly labelled) */}
              {analysis && analysis.broker_summary && analysis.broker_summary.bandar_status !== 'NO_DATA' ? (
                <BrokerSummarySection
                  data={analysis.broker_summary}
                  currentPrice={currentPrice}
                  onOpenSettings={() => {
                    onClose();
                    onOpenSettings?.();
                  }}
                />
              ) : (
                analysis && <FlowSummaryCard data={analysis.flow_summary} />
              )}

              {/* Financial statements: information only (does not change score or status) */}
              {analysis && <StatementsSection ticker={ticker} market={market} />}

              {/* Trend Direction Engine */}
              {analysis?.direction && (
                <TrendDirectionPanel
                  direction={analysis.direction}
                  marketRegime={analysis.market_regime}
                  pillars={analysis.composite.pillars}
                />
              )}

              {/* 4-Pillar Detailed Analysis Grid */}
              {analysis && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Card 1: Smart Money & True VSA */}
                  <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
                      <Flame className="w-4 h-4" />
                      <span>Aliran Uang & VSA</span>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Status Aliran Dana: <InfoTip term="money_flow_status" />
                        </span>
                        <span className="font-bold text-white text-right">
                          {MONEY_FLOW_LABELS[analysis.money_flow.money_flow_status] ?? analysis.money_flow.money_flow_status}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Chaikin MF (CMF): <InfoTip term="cmf" />
                        </span>
                        <span className={`font-mono font-bold ${analysis.money_flow.cmf20 >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {fmtSigned(analysis.money_flow.cmf20, 3)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Divergensi OBV: <InfoTip term="obv_divergence" />
                        </span>
                        <span className="text-gray-200 text-right">
                          {OBV_LABELS[analysis.money_flow.obv_divergence] ?? analysis.money_flow.obv_divergence}
                        </span>
                      </div>
                      <div className="py-1 border-b border-slate-800">
                        <div className="flex justify-between gap-2">
                          <span className="text-gray-400 inline-flex items-center gap-1">
                            Sinyal VSA: <InfoTip term={getTerm(`vsa_${analysis.money_flow.vsa_signal}`) ? `vsa_${analysis.money_flow.vsa_signal}` : 'vsa'} />
                          </span>
                          <span className="font-bold text-purple-300 text-right">
                            {analysis.money_flow.vsa_label || analysis.money_flow.vsa_signal}
                          </span>
                        </div>
                        {analysis.money_flow.vsa_desc && (
                          <p className="text-[10px] text-gray-400 mt-0.5">{analysis.money_flow.vsa_desc}</p>
                        )}
                      </div>
                      <div className="flex justify-between gap-2 py-1">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Rasio Volume: <InfoTip term="vol_ratio" />
                        </span>
                        <span className={`font-mono font-bold ${analysis.technical.vol_ratio >= 1.3 ? 'text-amber-400' : 'text-gray-200'}`}>
                          {fmtNum(analysis.technical.vol_ratio, 2)}x
                          <span className="text-[10px] font-sans font-normal text-gray-400 ml-1">
                            {analysis.technical.vol_ratio >= 1.5 ? '(lonjakan)' : analysis.technical.vol_ratio <= 0.75 ? '(sepi)' : '(normal)'}
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 2: Technical Indicators */}
                  <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-400">
                      <Activity className="w-4 h-4" />
                      <span>Teknikal & Trend</span>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          RSI (14): <InfoTip term="rsi" />
                        </span>
                        <span className="font-mono font-bold text-white">
                          {fmtNum(analysis.technical.rsi14, 1)}
                          <span className="text-[10px] font-sans font-normal text-gray-400 ml-1">
                            ({rsiHint(analysis.technical.rsi14)})
                          </span>
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          EMA 20 / 50: <InfoTip term="ema" />
                        </span>
                        <span className="font-mono text-gray-200">
                          {formatCurrency(analysis.technical.ema20)} / {formatCurrency(analysis.technical.ema50)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400">EMA 200 (jangka panjang):</span>
                        <span className="font-mono text-gray-200">
                          {formatCurrency(analysis.technical.ema200)}
                          {analysis.technical.ema200 > 0 && (
                            <span className="text-[10px] font-sans text-gray-400 ml-1">
                              ({analysis.technical.price >= analysis.technical.ema200 ? '▲ harga di atas' : '▼ harga di bawah'})
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          MACD Hist: <InfoTip term="macd" />
                        </span>
                        <span className={`font-mono ${analysis.technical.macd_hist >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {fmtSigned(analysis.technical.macd_hist, 2)}
                        </span>
                      </div>
                      <div className="flex justify-between gap-2 py-1">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Breakout 20 Hari: <InfoTip term="breakout_20d" />
                        </span>
                        <span className="font-bold text-white">
                          {analysis.technical.is_breakout ? '🟢 Ya, breakout' : '⚪ Belum'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 3: Fundamental & Financial Health */}
                  <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
                      <ShieldCheck className="w-4 h-4" />
                      <span>Kesehatan Finansial</span>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800">
                        <span className="text-gray-400 inline-flex items-center gap-1">
                          Grade Kesehatan: <InfoTip term={isSpeculative ? 'speculative' : 'health_grade'} />
                        </span>
                        <span className={`font-bold ${
                          isSpeculative || financials?.health_grade === 'DISTRESSED'
                            ? 'text-rose-400'
                            : financials?.health_grade === 'HEALTHY'
                            ? 'text-emerald-400'
                            : 'text-gray-200'
                        }`}>
                          {financials?.health_grade || 'MODERATE'} ({financials?.health_score ?? '-'}/100)
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800">
                        <span className="text-gray-400">ROE (Profitabilitas):</span>
                        <span className={`font-mono font-bold ${(financials?.roe ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {financials?.roe !== undefined ? fmtPct(financials.roe, 1) : '-'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800">
                        <span className="text-gray-400">Net Profit Margin:</span>
                        <span className={`font-mono font-bold ${(financials?.net_margin ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {financials?.net_margin !== undefined ? fmtPct(financials.net_margin, 1) : '-'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800">
                        <span className="text-gray-400">DER (Beban Utang):</span>
                        <span className={`font-mono font-bold ${(financials?.debt_to_equity ?? 0) <= 150 ? 'text-white' : 'text-rose-400'}`}>
                          {financials?.debt_to_equity !== undefined ? `${fmtNum(financials.debt_to_equity, 1)}%` : '-'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-gray-400">Valuasi (PER / PBV):</span>
                        <span className="font-mono text-gray-200">
                          {financials?.pe ? `${fmtNum(financials.pe, 1)}x` : '-'} / {financials?.pbv ? `${fmtNum(financials.pbv, 2)}x` : '-'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card 4: Algorithmic Reasons & Verdict */}
                  <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
                      <Sparkles className="w-4 h-4" />
                      <span>Kesimpulan Algoritma</span>
                    </div>

                    <div className="space-y-2 text-xs">
                      <div className="p-2 rounded-lg bg-surface border border-borderMuted">
                        <div className="text-[10px] text-gray-400 flex items-center gap-1">
                          Verdict Akhir: <InfoTip term="verdict" />
                        </div>
                        <div className="text-xs font-bold text-white mt-0.5">{analysis.composite.badge_text}</div>
                        <p className="text-[10px] text-gray-500 mt-1 leading-snug">
                          Ringkasan kondisi, bukan prediksi. Uji historis belum membuktikan skor ini akurat memprediksi kenaikan.
                        </p>
                      </div>

                      <div className="space-y-1.5 pt-1">
                        <div className="text-[10px] text-gray-500 uppercase tracking-wider font-bold">Faktor penilaian:</div>
                        {analysis.composite.reasons.map((r, i) => (
                          <div key={i} className="flex items-start gap-1.5 text-gray-300">
                            <span aria-hidden="true" className="text-gray-500 shrink-0">•</span>
                            <span className="text-[11px] leading-tight">{r}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* News Radar Section */}
              {analysis && analysis.news && analysis.news.length > 0 && (
                <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-gray-300">
                      Berita Terkini & Katalis Terdeteksi
                    </h3>
                    <span className="text-[11px] text-gray-400 font-mono">
                      Sentimen Skor: {fmtSigned(analysis.sentiment.sentiment_score, 2)} ({analysis.sentiment.sentiment_label})
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {analysis.news.map((n, idx) => (
                      <a
                        key={idx}
                        href={n.link}
                        target="_blank"
                        rel="noreferrer"
                        className="p-3 rounded-lg bg-surface hover:bg-surfaceHover border border-borderMuted flex items-start justify-between gap-3 group transition-all"
                      >
                        <div>
                          <p className="text-xs font-medium text-gray-200 group-hover:text-emerald-400 transition-colors line-clamp-2">
                            {n.title}
                          </p>
                          <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-500">
                            <span className="font-semibold text-gray-400">{n.source}</span>
                            <span>•</span>
                            <span>{n.published}</span>
                          </div>
                        </div>
                        <ExternalLink className="w-3.5 h-3.5 text-gray-500 group-hover:text-emerald-400 shrink-0 mt-0.5" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
