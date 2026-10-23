import React from 'react';
import { ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
import { ActionStatusBadge } from './ActionStatusBadge';
import { reasonSign } from './ReasonChip';
import { fmtPct, fmtPrice } from './help/format';
import { clickableProps, FOCUS_RING } from '../lib/a11y';
import { ChevronRight, Zap } from 'lucide-react';

interface Props {
  items: ScreenerItem[];
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
  /** First load / scan in progress with no rows yet: show placeholder cards. */
  isLoading?: boolean;
}

const CardSkeleton: React.FC = () => (
  <div className="p-4 rounded-xl bg-surface border border-borderMuted animate-pulse space-y-3" aria-hidden="true">
    <div className="flex items-center justify-between">
      <div className="h-4 w-20 rounded bg-slate-700/60" />
      <div className="h-3 w-14 rounded bg-slate-800" />
    </div>
    <div className="flex gap-2">
      <div className="h-5 w-24 rounded-full bg-slate-800" />
      <div className="h-5 w-20 rounded-full bg-slate-800" />
    </div>
    <div className="space-y-1.5">
      <div className="h-2.5 w-full rounded bg-slate-800" />
      <div className="h-2.5 w-3/4 rounded bg-slate-800" />
    </div>
    <div className="pt-2.5 border-t border-borderMuted">
      <div className="h-2.5 w-28 rounded bg-slate-800" />
    </div>
  </div>
);

export const TopPicks: React.FC<Props> = ({ items, onSelectTicker, isLoading = false }) => {
  // Same order as the Top 10 page (engine rank: status first), so "#1" means the same everywhere
  const ranked = items.some((s) => s.rank);
  const topThree = [...items]
    .sort((a, b) => (ranked ? (a.rank ?? 1e6) - (b.rank ?? 1e6) : (b.score ?? 0) - (a.score ?? 0)))
    .slice(0, 3);
  if (topThree.length === 0 && !isLoading) return null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-emerald-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">3 Teratas di Top 10</h2>
        </div>
        <span className="text-[11px] text-gray-400">Urutan sama dengan menu Top 10 · bukan rekomendasi beli</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5" aria-busy={topThree.length === 0}>
        {topThree.length === 0 && [0, 1, 2].map((i) => <CardSkeleton key={i} />)}
        {topThree.map((stock, idx) => {
          const changePct = stock.change_pct ?? 0;
          const isPos = changePct >= 0;
          const price = stock.price ?? 0;
          // Market-wide notes ("Mode Defensif ...") repeat on every card; show the stock's own reasons
          const reasons = (Array.isArray(stock.reasons) ? stock.reasons : [])
            .map((text, i) => ({ text, sign: reasonSign(text, stock.reason_signs?.[i]) }))
            .filter((r) => !/^(🐻|⛔)/.test(r.text));
          const buy = stock.recommended_entry && stock.recommended_entry > 0 ? stock.recommended_entry : null;

          return (
            <div
              key={stock.ticker}
              {...clickableProps(() => onSelectTicker(stock.ticker, stock.market))}
              className={`${FOCUS_RING} p-4 min-w-0 rounded-xl bg-surface border border-borderMuted hover:border-emerald-500/40 hover:bg-surfaceHover transition-all cursor-pointer group flex flex-col justify-between`}
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2 min-w-0">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono font-bold text-gray-400">#{idx + 1}</span>
                      <span className="text-base font-extrabold text-white font-mono group-hover:text-emerald-400 transition-colors">
                        {stock.ticker.replace('.JK', '')}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 whitespace-nowrap">
                      <span className="text-xs font-bold text-white font-mono">{fmtPrice(price)}</span>
                      <span className={`text-[11px] font-mono font-semibold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmtPct(changePct)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0 space-y-1">
                    {stock.action && <ActionStatusBadge status={stock.action.status} compact />}
                    <div className="text-[11px] text-gray-400">
                      Skor <span className="font-mono font-bold text-gray-100">{stock.score ?? '-'}</span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 mb-2.5">
                  <InflowBadge status={stock.money_flow_status} cmf={stock.cmf20} />
                </div>

                {buy && (
                  <div className="text-[11px] font-mono text-gray-300 mb-2">
                    Beli limit <span className="text-cyan-300 font-bold">{fmtPrice(buy)}</span>
                    {stock.stop_loss ? <> · cut loss <span className="text-rose-300">{fmtPrice(stock.stop_loss)}</span></> : null}
                    {stock.target_tp1 ? <> · TP1 <span className="text-emerald-300">{fmtPrice(stock.target_tp1)}</span></> : null}
                  </div>
                )}

                <div className="space-y-1 text-[11px] text-gray-300">
                  {reasons.slice(0, 2).map((r, i) => (
                    <div key={i} className="flex items-center gap-1.5 line-clamp-1">
                      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${r.sign > 0 ? 'bg-emerald-400' : r.sign < 0 ? 'bg-amber-400' : 'bg-gray-500'}`} />
                      <span>{r.text}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-3 pt-2.5 border-t border-borderMuted flex items-center justify-between text-[11px] text-emerald-400 font-medium group-hover:translate-x-0.5 transition-transform">
                <span>Lihat grafik & analisis</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
