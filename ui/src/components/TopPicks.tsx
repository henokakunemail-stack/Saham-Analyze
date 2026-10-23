import React from 'react';
import { ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
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
  const topThree = items.slice(0, 3);
  if (topThree.length === 0 && !isLoading) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">
            Saham Terkuat Saat Ini (Skor Tertinggi)
          </h2>
        </div>
        <span className="text-[11px] text-gray-400">Peringkat relatif, bukan rekomendasi beli — cek mode pasar & rekam jejak</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3.5" aria-busy={topThree.length === 0}>
        {topThree.length === 0 && [0, 1, 2].map((i) => <CardSkeleton key={i} />)}
        {topThree.map((stock, idx) => {
          const changePct = stock.change_pct ?? 0;
          const isPos = changePct >= 0;
          const price = stock.price ?? 0;
          const reasons = Array.isArray(stock.reasons) ? stock.reasons : [];

          return (
            <div
              key={stock.ticker}
              {...clickableProps(() => onSelectTicker(stock.ticker, stock.market))}
              className={`${FOCUS_RING} p-4 min-w-0 rounded-xl bg-surface border border-borderMuted hover:border-emerald-500/40 hover:bg-surfaceHover transition-all cursor-pointer group flex flex-col justify-between relative overflow-hidden`}
            >
              {/* Rank indicator ribbon */}
              <div className="absolute top-0 right-0 px-2.5 py-0.5 rounded-bl-lg bg-emerald-500/10 text-emerald-400 border-b border-l border-emerald-500/20 text-[10px] font-mono font-bold flex items-center gap-1">
                {stock.is_confirmed_breakout && <span className="text-amber-400">★</span>}
                <span>RANK #{idx + 1}</span>
              </div>

              <div>
                <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 pr-16 mb-2 min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-base font-extrabold text-white font-mono group-hover:text-emerald-400 transition-colors">
                      {stock.ticker}
                    </span>
                    {stock.is_confirmed_breakout && (
                      <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
                        KONFLUENSI
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0 whitespace-nowrap">
                    <span className="text-xs font-bold text-white font-mono">
                      {fmtPrice(price)}
                    </span>
                    <span className={`text-[11px] font-mono font-semibold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                      ({fmtPct(changePct)})
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <InflowBadge status={stock.money_flow_status} cmf={stock.cmf20} />
                  <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-slate-800 text-white border border-slate-700">
                    Skor: <span className="text-emerald-400">{stock.score ?? '-'}</span>/100
                  </span>
                </div>

                {/* Sinyal utama */}
                <div className="space-y-1 text-[11px] text-gray-400">
                  {reasons.slice(0, 2).map((r, i) => (
                    <div key={i} className="flex items-center gap-1.5 line-clamp-1">
                      <div className="w-1 h-1 rounded-full bg-emerald-400" />
                      <span>{r}</span>
                    </div>
                  ))}
                  {reasons.length === 0 && (
                    <div className="text-[11px] text-gray-500 italic">Analisa teknikal stabil</div>
                  )}
                </div>
              </div>

              <div className="mt-3 pt-2.5 border-t border-borderMuted flex items-center justify-between text-[11px] text-emerald-400 font-medium group-hover:translate-x-0.5 transition-transform">
                <span>Lihat Chart & Analisis</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
