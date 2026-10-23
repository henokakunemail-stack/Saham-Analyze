import React, { useState } from 'react';
import { ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
import { ReadingPlan, LatestNews } from './StockReading';
import { LevelBasis, PlanNow } from './FlowSummaryCard';
import { ClosingReview } from './ClosingReview';
import { AbnormalDaysChip } from './AbnormalDaysChip';
import { ActionStatusBadge } from './ActionStatusBadge';
import { ReasonChip } from './ReasonChip';
import { InfoTip } from './help/InfoTip';
import { fmtNum, fmtPct, fmtPrice, fmtSigned } from './help/format';
import { TrendingUp, Target, ShieldAlert, ArrowUpRight, Star, BarChart2, Compass, ChevronDown } from 'lucide-react';

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
  CONFIRMED: 'Belum ada saham di Top 10 dengan sinyal kuat (minimal 4 dari 6 gerbang konfluensi, searah tren). Saat pasar krisis, konfluensi dinonaktifkan.',
  STRONG_INFLOW: 'Belum ada saham di Top 10 dengan akumulasi kuat (CMF tinggi) saat ini.',
};

// Older engines wrote "Nol Berita Baru"; both mean there is no catalyst to show
const NO_CATALYST = new Set(['Nol Berita Baru', 'Tidak ada berita baru', 'Tidak Ada Katalis Khusus', 'Tidak ada katalis khusus']);

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

  // The engine's own order (rank: LAYAK first, then executable from today's price, then the
  // score before the market brake); older scans without a rank fall back to the score
  const ranked = items.some((s) => s.rank);
  const top10All = [...items]
    .sort((a, b) => (ranked ? (a.rank ?? 1e6) - (b.rank ?? 1e6) : (b.score ?? 0) - (a.score ?? 0)))
    .slice(0, 10);
  const countOf = (st: string) => top10All.filter((s) => s.action?.status === st).length;
  const hasStatus = top10All.some((s) => s.action);
  const frozenDay = top10All.find((s) => s.levels?.frozen)?.levels?.as_of;

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

  const pill = (active: boolean, activeCls: string) =>
    `px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${active ? `${activeCls} shadow font-bold` : 'text-gray-300 hover:text-white'}`;

  return (
    <div className="space-y-4">
      {/* Page title: one row, then at most a few one-line notes */}
      <div className="px-5 py-4 rounded-2xl bg-gradient-to-r from-emerald-950/30 via-surface to-surface border border-emerald-500/20 space-y-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400">
              <TrendingUp className="w-5 h-5" />
            </div>
            <h1 className="text-lg font-bold text-white tracking-tight">Top 10 Saham</h1>
            <InfoTip label="Cara Top 10 diurutkan">
              <p className="text-xs leading-relaxed">
                Urutan: <b>status</b> (LAYAK di atas) → <b>masih layak dipasang order dari harga sekarang</b> (harga beli dekat,
                TP1 masih di atas harga; yang sudah di TP, jebol cut loss, atau lari jauh dari zona turun ke bawah) →{' '}
                <b>skor</b>. Skor menggabungkan tren, aliran uang, momentum, fundamental, dan berita.
              </p>
            </InfoTip>
          </div>
          {hasStatus && (
            <div className="flex items-center gap-1.5 text-[11px] font-semibold">
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                {countOf('LAYAK')} LAYAK
              </span>
              <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-200 border border-amber-500/25">
                {countOf('TUNGGU')} TUNGGU
              </span>
              <span className="px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-300 border border-rose-500/25">
                {countOf('HINDARI')} HINDARI
              </span>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-300 max-w-3xl leading-relaxed">
          10 saham terbaik dari scan terakhir, masing-masing dengan <b className="text-white">harga beli (limit)</b>,{' '}
          <b className="text-white">cut loss</b>, dan <b className="text-white">target</b>.
          {hasStatus && countOf('LAYAK') === 0 && ' Belum ada yang layak dieksekusi — ini saham terbaik untuk ditunggu.'}
          {' '}Skor bukan jaminan naik; selalu pasang cut loss.
        </p>
        {top10All.some((s) => s.market_mode === 'CRASH' || s.market_mode === 'BEARISH') && (
          <p className="text-xs text-rose-300 flex items-start gap-1.5">
            <span aria-hidden="true">⛔</span>
            <span>
              Pasar sedang {top10All.some((s) => s.market_mode === 'CRASH') ? 'krisis' : 'bearish'} — daftar ini peringkat relatif;
              utamakan saham LAYAK dan ukuran posisi kecil.
            </span>
          </p>
        )}
        {crowded.map(([sector, tickers]) => (
          <p key={sector} className="text-xs text-amber-300 flex items-start gap-1.5">
            <span aria-hidden="true">⚠️</span>
            <span>
              {tickers.length} saham sektor {sector} ({tickers.join(', ')}) cenderung bergerak bersama — risiko terkonsentrasi bila
              semuanya dibeli.
            </span>
          </p>
        ))}
        {frozenDay && (
          <p className="text-[11px] text-gray-400">
            Bursa sedang berjalan: rencana dikunci dari penutupan terakhir; yang bergerak hanya harga (tertunda ±15 menit).
          </p>
        )}
      </div>

      {market && <ClosingReview market={market} onSelectTicker={onSelectTicker} />}

      {/* Filters act on the cards below, so they sit right above them */}
      {top10All.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-gray-400">Tampilkan kartu:</span>
          <div className="flex flex-wrap items-center gap-1 bg-[#090D16] p-1 rounded-xl border border-borderMuted">
            <button onClick={() => setFilterMode('ALL')} className={pill(filterMode === 'ALL', 'bg-emerald-500 text-black')}>
              Semua ({top10All.length})
            </button>
            {hasStatus && (
              <button onClick={() => setFilterMode('LAYAK')} className={pill(filterMode === 'LAYAK', 'bg-emerald-400 text-black')}>
                Layak ({countOf('LAYAK')})
              </button>
            )}
            <button onClick={() => setFilterMode('CONFIRMED')} className={pill(filterMode === 'CONFIRMED', 'bg-sky-500 text-black')}>
              Sinyal kuat
            </button>
            <button onClick={() => setFilterMode('STRONG_INFLOW')} className={pill(filterMode === 'STRONG_INFLOW', 'bg-emerald-600 text-white')}>
              Akumulasi kuat
            </button>
          </div>
        </div>
      )}

      {/* Grid of Top 10 Cards */}
      {top10All.length === 0 && isLoading ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="p-5 rounded-2xl bg-surface border border-borderMuted animate-pulse space-y-4" aria-hidden="true">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded-lg bg-slate-800" />
                  <div className="h-4 w-24 rounded bg-slate-700/60" />
                </div>
                <div className="h-6 w-16 rounded-full bg-slate-800" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[0, 1, 2].map((j) => <div key={j} className="h-14 rounded-lg bg-slate-800/80" />)}
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
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
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

            // Same base as the engine's R:R: the buy limit, not the last price
            const upsidePct = entryPrice > 0 && tp1 ? Math.round(((tp1 - entryPrice) / entryPrice) * 1000) / 10 : null;
            const downsidePct = entryPrice > 0 && cl ? Math.round(((entryPrice - cl) / entryPrice) * 1000) / 10 : null;
            const rrRatio =
              stock.risk_reward_ratio ||
              (upsidePct !== null && downsidePct ? Math.round((upsidePct / downsidePct) * 100) / 100 : null);
            const rrCls = !rrRatio ? 'text-gray-300' : rrRatio >= 2 ? 'text-emerald-300' : rrRatio >= 1.2 ? 'text-gray-100' : 'text-amber-300';

            const candle = stock.candlestick;
            const open = () => onSelectTicker(stock.ticker, stock.market);
            const hasRsi = typeof stock.rsi14 === 'number' && Number.isFinite(stock.rsi14);
            const hasEma200 = typeof stock.ema200 === 'number' && stock.ema200 > 0 && price > 0;
            // Plan heading follows the executability status; the verdict is only a fallback
            const planTitle = stock.action
              ? stock.action.status === 'LAYAK'
                ? 'Rencana — layak dieksekusi'
                : 'Rencana jika masuk — belum layak'
              : (stock.verdict === 'STRONG_BULLISH' || stock.verdict === 'MILD_BULLISH') && stock.market_mode !== 'CRASH'
                ? 'Rencana jika masuk'
                : 'Level teknis — belum sinyal masuk';

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
                <div>
                  {/* Header: rank, ticker, price | status, score, pin */}
                  <div className="flex items-start justify-between gap-3 mb-3 min-w-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`w-8 h-8 shrink-0 rounded-xl flex items-center justify-center font-mono font-extrabold text-sm ${
                          rank <= 3 ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-[#090D16] border border-borderMuted text-gray-300'
                        }`}
                      >
                        #{rank}
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-lg font-mono font-extrabold text-white group-hover:text-emerald-400 transition-colors">
                            {stock.ticker.replace('.JK', '')}
                          </span>
                          {stock.sector && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-gray-300 border border-slate-700">
                              {stock.sector}
                            </span>
                          )}
                          {stock.is_confirmed_breakout && (
                            <span
                              className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30"
                              title="Sinyal kuat: minimal 4 dari 6 gerbang konfluensi lolos"
                            >
                              Sinyal kuat
                            </span>
                          )}
                          <AbnormalDaysChip items={stock.abnormal_recent} compact />
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-sm font-bold font-mono text-gray-100">{fmtPrice(price)}</span>
                          <span className={`text-xs font-mono font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {fmtPct(stock.change_pct)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0">
                      <div className="text-right space-y-1">
                        {stock.action ? (
                          <ActionStatusBadge status={stock.action.status} />
                        ) : (
                          <span className="text-[11px] text-gray-300">{stock.badge_text || '⚪ KONSOLIDASI'}</span>
                        )}
                        <div className="text-[11px] text-gray-400">
                          Skor <span className="font-mono font-bold text-gray-100">{stock.score ?? '-'}</span>/100
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

                  {/* What the algorithm says, in one sentence */}
                  <ReadingPlan reading={stock.reading} compact />

                  {/* The plan: buy limit, target, cut loss */}
                  <div className="p-3.5 rounded-xl bg-[#090D16] border border-borderMuted space-y-2.5 mb-3">
                    <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-gray-400 border-b border-borderMuted/60 pb-1.5">
                      <div className="flex items-center gap-1.5 text-cyan-300">
                        <Target className="w-3.5 h-3.5" />
                        <span>{planTitle}</span>
                      </div>
                      <div className="font-mono shrink-0 flex items-center gap-1">
                        Rugi : Untung <span className={`font-bold ${rrCls}`}>{rrRatio ? `1 : ${fmtNum(rrRatio, 2, 2)}` : '-'}</span>
                        <InfoTip term="risk_reward" />
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="p-2 rounded-lg bg-cyan-500/5 border border-cyan-500/25">
                        <div className="text-[11px] text-cyan-300 font-semibold flex items-center justify-center gap-1">
                          <Compass className="w-3 h-3" />
                          <span>Harga beli</span>
                          <InfoTip term="buy_limit" />
                        </div>
                        <div className="text-base font-mono font-bold text-cyan-200 mt-0.5">{fmtPrice(entryPrice)}</div>
                        <div className="text-[10px] text-gray-400 font-mono">
                          {stock.entry_low && stock.entry_high
                            ? `limit · zona ${fmtPrice(stock.entry_low)}–${fmtPrice(stock.entry_high)}`
                            : 'order limit'}
                        </div>
                      </div>

                      <div className="p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/25">
                        <div className="text-[11px] text-emerald-300 font-semibold flex items-center justify-center gap-1">
                          <ArrowUpRight className="w-3 h-3" />
                          <span>Target 1</span>
                          <InfoTip term="take_profit" />
                        </div>
                        <div className="text-base font-mono font-bold text-emerald-200 mt-0.5">{fmtPrice(tp1)}</div>
                        <div className="text-[10px] text-gray-400 font-mono">
                          {upsidePct !== null ? fmtPct(upsidePct, 1) : '-'} · T2 {fmtPrice(tp2)}
                        </div>
                      </div>

                      <div className="p-2 rounded-lg bg-rose-500/5 border border-rose-500/25">
                        <div className="text-[11px] text-rose-300 font-semibold flex items-center justify-center gap-1">
                          <ShieldAlert className="w-3 h-3" />
                          <span>Cut loss</span>
                          <InfoTip term="stop_loss" />
                        </div>
                        <div className="text-base font-mono font-bold text-rose-200 mt-0.5">{fmtPrice(cl)}</div>
                        <div className="text-[10px] text-gray-400 font-mono">
                          {downsidePct !== null ? fmtPct(-downsidePct, 1) : '-'}
                        </div>
                      </div>
                    </div>
                    <PlanNow levels={stock.levels} />
                  </div>

                  {/* Money flow & financial health: the two things the app is about, kept visible */}
                  <div className="flex flex-wrap items-center gap-2">
                    <InflowBadge status={stock.money_flow_status} cmf={stock.cmf20} />
                    {stock.is_speculative ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-rose-500/15 text-rose-300 border-rose-500/40">
                        ⚠️ Spekulatif (rugi/utang tinggi)
                      </span>
                    ) : stock.health_grade === 'HEALTHY' ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-emerald-500/10 text-emerald-300 border-emerald-500/30">
                        🛡️ Keuangan sehat {stock.roe ? `(ROE ${fmtNum(stock.roe, 1)}%)` : ''}
                      </span>
                    ) : stock.health_grade === 'DISTRESSED' ? (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-rose-500/15 text-rose-300 border-rose-500/40">
                        ⚠️ Keuangan tertekan {stock.debt_to_equity ? `(DER ${fmtNum(stock.debt_to_equity, 1)}%)` : ''}
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold border bg-slate-800 text-slate-300 border-slate-700">
                        ⚖️ Keuangan stabil
                      </span>
                    )}
                  </div>

                  {/* Everything else, one click away */}
                  <details className="group/d mt-3 rounded-lg border border-borderMuted/70 bg-[#090D16]/40" onClick={(e) => e.stopPropagation()}>
                    <summary className="list-none cursor-pointer select-none px-3 py-1.5 text-[11px] font-semibold text-gray-300 hover:text-white flex items-center gap-1">
                      <ChevronDown className="w-3.5 h-3.5 transition-transform group-open/d:rotate-180" />
                      Lihat alasan & detail
                    </summary>
                    <div className="px-3 pb-3 space-y-3">
                      {Array.isArray(stock.reasons) && stock.reasons.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {stock.reasons.slice(0, 4).map((reason, i) => (
                            <ReasonChip key={i} text={reason} sign={stock.reason_signs?.[i]} />
                          ))}
                        </div>
                      )}

                      <div className="flex flex-wrap gap-2">
                        {stock.vsa_signal && stock.vsa_signal !== 'NORMAL' && (
                          <span className="px-2 py-0.5 rounded text-[11px] border bg-slate-800 text-gray-200 border-slate-700 inline-flex items-center gap-1">
                            Volume: {stock.vsa_label || stock.vsa_signal}
                            <InfoTip term={`vsa_${stock.vsa_signal}`} />
                          </span>
                        )}
                        {candle && typeof candle.pattern === 'string' && candle.pattern.length > 0 && (
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] border ${
                              candle.signal === 'BULLISH' || candle.signal === 'STRONG_BULLISH'
                                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                                : candle.signal === 'BEARISH'
                                ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                                : 'bg-slate-800 text-slate-300 border-slate-700'
                            }`}
                          >
                            Candle: {candle.label || candle.pattern.replace(/_/g, ' ')}
                          </span>
                        )}
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                        <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                          <div className="text-[11px] text-gray-400 flex items-center gap-1">RSI (14) <InfoTip term="rsi" /></div>
                          <div className="font-mono font-semibold text-white mt-0.5 flex items-center gap-1">
                            <span>{hasRsi ? fmtNum(stock.rsi14, 1) : '-'}</span>
                            {hasRsi && stock.rsi14 > 70 && <span className="text-[10px] text-rose-400 font-bold">Panas</span>}
                            {hasRsi && stock.rsi14 < 30 && <span className="text-[10px] text-amber-400 font-bold">Jenuh jual</span>}
                          </div>
                        </div>
                        <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                          <div className="text-[11px] text-gray-400 flex items-center gap-1">Aliran uang (CMF) <InfoTip term="cmf" /></div>
                          <div className="font-mono font-semibold mt-0.5">
                            <span className={(stock.cmf20 ?? 0) >= 0.05 ? 'text-emerald-400' : 'text-gray-300'}>{fmtSigned(stock.cmf20, 2)}</span>
                          </div>
                        </div>
                        <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                          <div className="text-[11px] text-gray-400 flex items-center gap-1">Rasio volume <InfoTip term="vol_ratio" /></div>
                          <div className="font-mono font-semibold mt-0.5">
                            <span className={(stock.vol_ratio ?? 1) >= 1.5 ? 'text-amber-400 font-bold' : 'text-gray-300'}>
                              {typeof stock.vol_ratio === 'number' ? `${fmtNum(stock.vol_ratio, 2)}x` : '-'}
                            </span>
                          </div>
                        </div>
                        <div className="p-2 rounded-lg bg-surface/50 border border-borderMuted">
                          <div className="text-[11px] text-gray-400 flex items-center gap-1">Tren jangka panjang <InfoTip term="ema" /></div>
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

                      <LevelBasis levels={stock.levels} compact withNow={false} />

                      <div className="px-2.5 py-2 rounded-lg bg-surface/80 border border-borderMuted space-y-1.5">
                        {stock.catalyst && !NO_CATALYST.has(stock.catalyst) && (
                          <div className="text-[11px] text-gray-300 font-medium truncate">Katalis utama: {stock.catalyst}</div>
                        )}
                        <LatestNews headlines={stock.news_headlines} checkedAt={stock.news_checked_at} />
                      </div>
                    </div>
                  </details>
                </div>

                <div className="mt-4 pt-3 border-t border-borderMuted flex items-center justify-between text-xs text-emerald-400 font-semibold group-hover:text-emerald-300">
                  <div className="flex items-center gap-1">
                    <BarChart2 className="w-4 h-4" />
                    <span>Buka grafik & analisis lengkap</span>
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
