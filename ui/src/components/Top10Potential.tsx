import React, { useState } from 'react';
import { ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
import { ReadingPlan, LatestNews } from './StockReading';
import { LevelBasis } from './FlowSummaryCard';
import { PlanCheckpoint } from './PlanCheckpoint';
import { AbnormalDaysChip } from './AbnormalDaysChip';
import { ActionStatusBadge } from './ActionStatusBadge';
import { fmtNum, fmtPct, fmtPrice, fmtSigned } from './help/format';
import {
  TrendingUp,
  Target,
  ShieldAlert,
  ArrowUpRight,
  Star,
  BarChart2,
  Compass,
  CheckCircle2,
} from 'lucide-react';

interface Props {
  /** Exchange of the list; enables the live 'price vs plan' checkpoint. */
  market?: 'IDX' | 'US';
  items: ScreenerItem[];
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
  onToggleWatchlist: (ticker: string) => void;
  watchlistSet: Set<string>;
  /** First load / scan running with no rows yet. */
  isLoading?: boolean;
  /** Start a scan from the empty state (omitted while the engine is offline). */
  onScan?: () => void;
}

const FILTER_EMPTY_TEXT: Record<'LAYAK' | 'CONFIRMED' | 'STRONG_INFLOW', string> = {
  LAYAK: 'Belum ada saham yang LAYAK dieksekusi hari ini — semua masih perlu ditunggu (lihat alasan di tiap kartu).',
  CONFIRMED: 'Belum ada saham di Top 10 yang lolos konfluensi (minimal 4 dari 6 gerbang, searah tren). Saat pasar krisis, konfluensi dinonaktifkan.',
  STRONG_INFLOW: 'Belum ada saham di Top 10 dengan aliran uang masuk kuat (CMF tinggi) saat ini.',
};

export const Top10Potential: React.FC<Props> = ({
  market,
  items,
  onSelectTicker,
  onToggleWatchlist,
  watchlistSet,
  isLoading = false,
  onScan,
}) => {
  const [filterMode, setFilterMode] = useState<'ALL' | 'LAYAK' | 'CONFIRMED' | 'STRONG_INFLOW'>('ALL');

  // The engine's own order (rank: LAYAK first, then the score before the market brake);
  // older scans without a rank fall back to the score
  const ranked = items.some((s) => s.rank);
  const top10All = [...items]
    .sort((a, b) => (ranked ? (a.rank ?? 1e6) - (b.rank ?? 1e6) : (b.score ?? 0) - (a.score ?? 0)))
    .slice(0, 10);
  const countOf = (st: string) => top10All.filter((s) => s.action?.status === st).length;
  const hasStatus = top10All.some((s) => s.action);

  // Fase 4: several picks from one sector move together — say so
  const crowded = Object.entries(
    top10All.reduce<Record<string, string[]>>((acc, s) => {
      if (s.sector && s.sector !== 'Lainnya') (acc[s.sector] ??= []).push(s.ticker.replace('.JK', ''));
      return acc;
    }, {})
  ).filter(([, t]) => t.length >= 3);

  const displayedItems = top10All.filter((item) => {
    if (filterMode === 'LAYAK') return item.action?.status === 'LAYAK';
    if (filterMode === 'CONFIRMED') return Boolean(item.is_confirmed_breakout);
    if (filterMode === 'STRONG_INFLOW') return item.money_flow_status === 'STRONG_INFLOW';
    return true;
  });


  return (
    <div className="space-y-6">
      {market && <PlanCheckpoint market={market} onSelectTicker={onSelectTicker} />}
      {/* Page Title & Summary Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-surface to-surface border border-emerald-500/20 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400">
              <TrendingUp className="w-5 h-5" />
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
              Top 10 Skor Tertinggi
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Quantitative Radar
              </span>
            </h1>
          </div>
          {top10All.some((s) => s.market_mode === 'CRASH' || s.market_mode === 'BEARISH') && (
            <p className="mb-2 text-xs font-semibold text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg px-2.5 py-1.5 max-w-2xl">
              ⛔ Pasar sedang {top10All.some((s) => s.market_mode === 'CRASH') ? 'krisis' : 'bearish'}: daftar ini hanya peringkat
              relatif. Level harga di bawah adalah perhitungan teknis, bukan ajakan masuk sekarang.
            </p>
          )}
          {hasStatus && (
            <p className="mb-2 text-xs text-gray-300 flex flex-wrap items-center gap-2">
              <span className="font-semibold text-emerald-300">{countOf('LAYAK')} LAYAK</span>·
              <span className="font-semibold text-amber-300">{countOf('TUNGGU')} TUNGGU</span>·
              <span className="font-semibold text-rose-300">{countOf('HINDARI')} HINDARI</span>
              {countOf('LAYAK') === 0 && (
                <span className="text-gray-400">— belum ada setup yang layak dieksekusi; ini saham terbaik untuk ditunggu.</span>
              )}
            </p>
          )}
          {crowded.map(([sector, tickers]) => (
            <p key={sector} className="mb-2 text-xs font-semibold text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-2.5 py-1.5 max-w-2xl">
              ⚠️ {tickers.length} saham dari sektor {sector} ({tickers.join(', ')}) — cenderung bergerak bersama; risiko
              terkonsentrasi bila semuanya dibeli.
            </p>
          ))}
          <p className="text-xs text-gray-400 max-w-2xl leading-relaxed">
            Peringkat skor tertinggi (bukan jaminan naik). Dianalisis secara multi-dimensi menggabungkan konfluensi <strong>Indikator Teknikal</strong> (EMA, RSI, MACD),
            <strong> Aliran Uang CMF</strong> (indikasi dari harga &amp; volume), <strong>Pola Candlestick</strong>,
            dan <strong>Sentimen Berita Pasar</strong> beserta kalkulasi otomatis harga <strong>Entry, Take Profit, dan Cutloss</strong>.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 bg-[#090D16] p-1.5 rounded-xl border border-borderMuted self-start md:self-auto">
          <button
            onClick={() => setFilterMode('ALL')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              filterMode === 'ALL'
                ? 'bg-emerald-500 text-black shadow font-bold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Semua Top 10
          </button>
          {hasStatus && (
            <button
              onClick={() => setFilterMode('LAYAK')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                filterMode === 'LAYAK' ? 'bg-emerald-400 text-black shadow font-bold' : 'text-gray-400 hover:text-white'
              }`}
            >
              ✅ Layak ({countOf('LAYAK')})
            </button>
          )}
          <button
            onClick={() => setFilterMode('CONFIRMED')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              filterMode === 'CONFIRMED'
                ? 'bg-amber-500 text-black shadow font-bold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            ✅ Konfluensi Lolos
          </button>
          <button
            onClick={() => setFilterMode('STRONG_INFLOW')}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              filterMode === 'STRONG_INFLOW'
                ? 'bg-emerald-600 text-white shadow font-bold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            🔥 Strong Inflow
          </button>
        </div>
      </div>

      {/* Grid of Top 10 Cards */}
      {top10All.length === 0 && isLoading ? (
        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="p-5 rounded-2xl bg-surface border border-borderMuted animate-pulse space-y-4" aria-hidden="true">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded-lg bg-slate-800" />
                  <div className="h-4 w-24 rounded bg-slate-700/60" />
                </div>
                <div className="h-6 w-16 rounded-full bg-slate-800" />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {[0, 1, 2, 3].map((j) => <div key={j} className="h-12 rounded-lg bg-slate-800/80" />)}
              </div>
              <div className="space-y-1.5">
                <div className="h-2.5 w-full rounded bg-slate-800" />
                <div className="h-2.5 w-2/3 rounded bg-slate-800" />
              </div>
            </div>
          ))}
        </div>
      ) : top10All.length === 0 ? (
        <div className="p-12 text-center rounded-2xl border border-dashed border-borderMuted bg-surface/30">
          <h3 className="text-sm font-bold text-gray-300">Belum ada hasil scan</h3>
          <p className="text-xs text-gray-400 mt-1 max-w-md mx-auto">
            Peringkat Top 10 dibuat dari hasil scan pasar. Jalankan scan terlebih dahulu
            {onScan ? '.' : ' — data akan muncul otomatis setelah engine terhubung.'}
          </p>
          {onScan && (
            <button
              onClick={onScan}
              className="mt-4 px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 text-xs font-semibold"
            >
              Scan sekarang
            </button>
          )}
        </div>
      ) : displayedItems.length === 0 ? (
        <div className="p-12 text-center rounded-2xl border border-borderMuted bg-surface text-sm">
          <p className="text-gray-400">{filterMode !== 'ALL' ? FILTER_EMPTY_TEXT[filterMode] : 'Tidak ada saham yang memenuhi kriteria.'}</p>
          <button
            onClick={() => setFilterMode('ALL')}
            className="mt-3 text-xs font-semibold text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
          >
            Tampilkan semua Top 10
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
          {displayedItems.map((stock) => {
            const rank = top10All.findIndex((s) => s.ticker === stock.ticker) + 1;
            const isPos = (stock.change_pct ?? 0) >= 0;
            const isPinned = watchlistSet.has(stock.ticker);

            const price = stock.price ?? 0;
            const entryPrice = stock.recommended_entry && stock.recommended_entry > 0 ? stock.recommended_entry : price;
            // Levels come from the engine only; missing values are shown as "-" rather than invented
            const pos = (v?: number) => (v !== undefined && v !== null && v > 0 ? v : undefined);
            const tp1 = pos(stock.target_tp1) ?? pos(stock.target_tp);
            const tp2 = pos(stock.target_tp2);
            const cl = pos(stock.stop_loss);

            // Same base as the engine's R:R: the recommended entry, not the last price
            const upsidePct = entryPrice > 0 && tp1 ? Math.round(((tp1 - entryPrice) / entryPrice) * 1000) / 10 : null;
            const downsidePct = entryPrice > 0 && cl ? Math.round(((entryPrice - cl) / entryPrice) * 1000) / 10 : null;
            const rrRatio =
              stock.risk_reward_ratio ||
              (upsidePct !== null && downsidePct ? Math.round((upsidePct / downsidePct) * 100) / 100 : null);

            const candle = stock.candlestick;
            const open = () => onSelectTicker(stock.ticker, stock.market);
            const hasRsi = typeof stock.rsi14 === 'number' && Number.isFinite(stock.rsi14);
            const hasEma200 = typeof stock.ema200 === 'number' && stock.ema200 > 0 && price > 0;
            // Plan heading follows the executability status; the verdict is only a fallback
            const planTitle = stock.action
              ? stock.action.status === 'LAYAK'
                ? 'Rencana Trading — Layak Dieksekusi'
                : 'Rencana Trading (Jika Masuk) — belum layak'
              : (stock.verdict === 'STRONG_BULLISH' || stock.verdict === 'MILD_BULLISH') && stock.market_mode !== 'CRASH'
                ? 'Rencana Trading (Jika Masuk)'
                : 'Level Teknis — Belum Sinyal Masuk';

            return (
              <div
                key={stock.ticker}
                role="button"
                tabIndex={0}
                aria-label={`Buka detail ${stock.ticker}`}
                onClick={open}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    open();
                  }
                }}
                className="p-5 min-w-0 rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 bg-surface border border-borderMuted hover:border-emerald-500/40 hover:bg-surfaceHover/90 transition-all cursor-pointer group flex flex-col justify-between relative shadow-lg"
              >
                {/* Top Header: Rank, Ticker, Watchlist, Score */}
                <div>
                  <div className="flex items-center justify-between gap-3 mb-3 min-w-0">
                    <div className="flex items-center gap-3 min-w-0">
                      {/* Rank Badge */}
                      <div className={`w-8 h-8 shrink-0 rounded-xl flex items-center justify-center font-mono font-extrabold text-sm ${
                        rank === 1
                          ? 'bg-amber-400 text-black shadow-[0_0_12px_rgba(251,191,36,0.5)]'
                          : rank === 2
                          ? 'bg-slate-300 text-black'
                          : rank === 3
                          ? 'bg-amber-700/80 text-white'
                          : 'bg-[#090D16] border border-borderMuted text-gray-300'
                      }`}>
                        #{rank}
                      </div>

                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-lg font-mono font-extrabold text-white group-hover:text-emerald-400 transition-colors">
                            {stock.ticker}
                          </span>
                          {stock.is_confirmed_breakout && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                              ✅ KONFLUENSI
                            </span>
                          )}
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surfaceHover text-gray-400 font-mono">
                            {stock.market}
                          </span>
                          {stock.action && <ActionStatusBadge status={stock.action.status} compact />}
                          {stock.sector && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20">
                              {stock.sector}
                            </span>
                          )}
                          <AbnormalDaysChip items={stock.abnormal_recent} compact />
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-sm font-bold font-mono text-gray-100">
                            {fmtPrice(price)}
                          </span>
                          <span className={`text-xs font-mono font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {fmtPct(stock.change_pct)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Right side: Score & Pin */}
                    <div className="flex items-center gap-2.5 shrink-0">
                      <div className="text-right">
                        <div className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">Skor Potensi</div>
                        <div className="text-base font-mono font-extrabold text-emerald-400">
                          {stock.score ?? '-'}<span className="text-xs text-gray-400 font-normal">/100</span>
                        </div>
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleWatchlist(stock.ticker);
                        }}
                        className="p-2 rounded-xl bg-[#090D16] hover:bg-surfaceHover border border-borderMuted transition-colors text-gray-400 hover:text-amber-400"
                        title={isPinned ? 'Hapus dari Watchlist' : 'Simpan ke Watchlist'}
                        aria-label={isPinned ? `Hapus ${stock.ticker} dari watchlist` : `Simpan ${stock.ticker} ke watchlist`}
                        aria-pressed={isPinned}
                      >
                        <Star className={`w-4 h-4 ${isPinned ? 'fill-amber-400 text-amber-400' : ''}`} />
                      </button>
                    </div>
                  </div>

                  {/* Badges / Flow & Verdict */}
                  <div className="flex flex-wrap items-center gap-2 mb-4">
                    <InflowBadge status={stock.money_flow_status} cmf={stock.cmf20} />
                    <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#090D16] border border-borderMuted text-gray-300 flex items-center gap-1.5">
                      <span>{stock.badge_text || '⚪ KONSOLIDASI'}</span>
                    </span>

                    {/* Financial Health Badge */}
                    {stock.is_speculative ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-rose-500/15 text-rose-300 border-rose-500/40">
                        ⚠️ Spekulatif (Rugi/Utang)
                      </span>
                    ) : stock.health_grade === 'HEALTHY' ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-emerald-500/15 text-emerald-300 border-emerald-500/40">
                        🛡️ Finansial Sehat {stock.roe ? `(ROE ${fmtNum(stock.roe, 1)}%)` : ''}
                      </span>
                    ) : stock.health_grade === 'DISTRESSED' ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-rose-500/15 text-rose-300 border-rose-500/40">
                        ⚠️ Utang/Rugi {stock.debt_to_equity ? `(DER ${fmtNum(stock.debt_to_equity, 1)}%)` : ''}
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-slate-800 text-slate-300 border-slate-700">
                        ⚖️ Finansial Stabil
                      </span>
                    )}

                    {/* VSA Signal Badge */}
                    {stock.vsa_signal && stock.vsa_signal !== 'NORMAL' && (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-purple-500/15 text-purple-300 border-purple-500/30">
                        📊 {stock.vsa_label || stock.vsa_signal}
                      </span>
                    )}

                    {/* Candlestick Pattern with Reliability */}
                    {candle && typeof candle.pattern === 'string' && candle.pattern.length > 0 && (
                      <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                        candle.signal === 'BULLISH' || candle.signal === 'STRONG_BULLISH'
                          ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                          : candle.signal === 'BEARISH'
                          ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                          : 'bg-slate-800 text-slate-300 border-slate-700'
                      }`}>
                        🕯️ {candle.label || candle.pattern.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>

                  {/* Algorithm's explicit plan: stance, triggers, invalidation, target */}
                  <ReadingPlan reading={stock.reading} />

                  {/* 🎯 TRADING SETUP: ENTRY, TP, CUTLOSS BOX */}
                  <div className="p-3.5 rounded-xl bg-[#090D16] border border-borderMuted space-y-3 mb-4">
                    <div className="flex items-center justify-between gap-2 text-[11px] font-bold uppercase tracking-wider text-gray-400 border-b border-borderMuted/60 pb-1.5">
                      <div className="flex items-center gap-1.5 text-cyan-400">
                        <Target className="w-3.5 h-3.5" />
                        <span>{planTitle}</span>
                      </div>
                      <div className="font-mono text-gray-400 shrink-0">
                        R:R <span className="text-white font-bold">{rrRatio ? `1 : ${fmtNum(rrRatio, 2, 2)}` : '-'}</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      {/* Entry Price & Zone */}
                      <div className="p-2 rounded-lg bg-surface border border-borderMuted">
                        <div className="text-[10px] text-gray-400 uppercase font-semibold flex items-center justify-center gap-1">
                          <Compass className="w-3 h-3 text-cyan-400" />
                          <span>Zona beli</span>
                        </div>
                        <div className="text-sm font-mono font-bold text-cyan-300 mt-0.5">
                          {stock.entry_low && stock.entry_high
                            ? `${fmtPrice(stock.entry_low)} – ${fmtPrice(stock.entry_high)}`
                            : fmtPrice(entryPrice)}
                        </div>
                        <div
                          className="text-[9px] text-cyan-300/80 font-mono truncate"
                          title="Uji historis mengasumsikan order beli limit di harga saran, bukan di batas atas zona"
                        >
                          Harga saran (limit) {fmtPrice(entryPrice)}
                        </div>
                      </div>

                      {/* Take Profit (TP1 & TP2) */}
                      <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                        <div className="text-[10px] text-emerald-400 uppercase font-semibold flex items-center justify-center gap-1">
                          <ArrowUpRight className="w-3 h-3 text-emerald-400" />
                          <span>TP1</span>
                        </div>
                        <div className="text-sm font-mono font-bold text-emerald-300 mt-0.5">
                          {fmtPrice(tp1)}
                        </div>
                        <div className="text-[9px] text-emerald-400 font-mono font-semibold">
                          {upsidePct !== null ? `${fmtPct(upsidePct, 1)} dari entry` : '-'} (TP2: {fmtPrice(tp2)})
                        </div>
                      </div>

                      {/* Cut Loss / Stop Loss */}
                      <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
                        <div className="text-[10px] text-rose-400 uppercase font-semibold flex items-center justify-center gap-1">
                          <ShieldAlert className="w-3 h-3 text-rose-400" />
                          <span>Cut loss</span>
                        </div>
                        <div className="text-sm font-mono font-bold text-rose-300 mt-0.5">
                          {fmtPrice(cl)}
                        </div>
                        <div className="text-[9px] text-rose-400 font-mono font-semibold">
                          {downsidePct !== null ? `${fmtPct(-downsidePct, 1)} dari entry` : '-'} (bawah support)
                        </div>
                      </div>
                    </div>
                    <LevelBasis levels={stock.levels} compact />
                  </div>

                  {/* Multi-Dimensional Analytics Grid (Indicators, Money Flow, Candlestick, News) */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
                    {/* RSI */}
                    <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                      <div className="text-[10px] text-gray-400">RSI (14)</div>
                      <div className="font-mono font-semibold text-white mt-0.5 flex items-center gap-1">
                        <span>{hasRsi ? fmtNum(stock.rsi14, 1) : '-'}</span>
                        {hasRsi && stock.rsi14 > 70 && <span className="text-[9px] text-rose-400 font-bold">Panas</span>}
                        {hasRsi && stock.rsi14 < 30 && <span className="text-[9px] text-amber-400 font-bold">Jenuh Jual</span>}
                      </div>
                    </div>

                    {/* Money Flow / CMF */}
                    <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                      <div className="text-[10px] text-gray-400">Chaikin MF (20)</div>
                      <div className="font-mono font-semibold mt-0.5">
                        <span className={(stock.cmf20 ?? 0) >= 0.05 ? 'text-emerald-400' : 'text-gray-300'}>
                          {fmtSigned(stock.cmf20, 2)}
                        </span>
                      </div>
                    </div>

                    {/* Volume Ratio */}
                    <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                      <div className="text-[10px] text-gray-400">Vol Spike</div>
                      <div className="font-mono font-semibold mt-0.5">
                        <span className={(stock.vol_ratio ?? 1) >= 1.5 ? 'text-amber-400 font-bold' : 'text-gray-300'}>
                          {typeof stock.vol_ratio === 'number' ? `${fmtNum(stock.vol_ratio, 2)}x` : '-'}
                        </span>
                      </div>
                    </div>

                    {/* EMA Structure */}
                    <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                      <div className="text-[10px] text-gray-400">EMA Trend</div>
                      <div className="font-mono font-semibold text-white mt-0.5 text-[11px] truncate">
                        {!hasEma200 ? (
                          <span className="text-gray-400">-</span>
                        ) : price > stock.ema200 ? (
                          <span className="text-emerald-400">Di atas EMA200</span>
                        ) : (
                          <span className="text-rose-300">Di bawah EMA200</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Sinyal Konfluensi & Katalis Berita */}
                  <div className="space-y-1.5 text-xs text-gray-300">
                    {/* Alasan / Signal Points */}
                    {Array.isArray(stock.reasons) && stock.reasons.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {stock.reasons.slice(0, 3).map((reason, i) => (
                          <div
                            key={i}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#090D16] border border-borderMuted text-[11px] text-gray-300"
                          >
                            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                            <span>{reason}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Berita terbaru per saham */}
                    <div className="px-2.5 py-2 rounded-lg bg-surface/80 border border-borderMuted space-y-1.5">
                      {stock.catalyst && stock.catalyst !== 'Nol Berita Baru' && (
                        <div className="text-[11px] text-gray-300 font-medium truncate">Katalis utama: {stock.catalyst}</div>
                      )}
                      <LatestNews headlines={stock.news_headlines} checkedAt={stock.news_checked_at} />
                    </div>
                  </div>
                </div>

                {/* Bottom Card Action */}
                <div className="mt-4 pt-3 border-t border-borderMuted flex items-center justify-between text-xs text-emerald-400 font-semibold group-hover:text-emerald-300">
                  <div className="flex items-center gap-1">
                    <BarChart2 className="w-4 h-4" />
                    <span>Buka Grafik & Analisis Detail</span>
                  </div>
                  <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

