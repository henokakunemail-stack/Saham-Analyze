import React from 'react';
import { WatchlistItem, ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
import { fmtPct, fmtPrice } from './help/format';
import { clickableProps, FOCUS_RING } from '../lib/a11y';
import { Star, Trash2 } from 'lucide-react';

interface Props {
  watchlist: WatchlistItem[];
  screenerItems: ScreenerItem[];
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
  onRemove: (ticker: string) => void;
  /** Watchlist itself not loaded yet. */
  isLoading?: boolean;
  /** Screener data (live prices) still loading. */
  isScreenerLoading?: boolean;
}

export const Watchlist: React.FC<Props> = ({
  watchlist,
  screenerItems,
  onSelectTicker,
  onRemove,
  isLoading = false,
  isScreenerLoading = false,
}) => {
  const stockMap = new Map(screenerItems.map((s) => [s.ticker, s]));

  if (watchlist.length === 0 && isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-3 w-48 rounded bg-slate-800 animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="p-4 rounded-xl bg-surface border border-borderMuted animate-pulse space-y-3" aria-hidden="true">
              <div className="h-4 w-24 rounded bg-slate-700/60" />
              <div className="h-4 w-32 rounded bg-slate-800" />
              <div className="pt-2 border-t border-borderMuted flex justify-between">
                <div className="h-5 w-24 rounded-full bg-slate-800" />
                <div className="h-3 w-14 rounded bg-slate-800" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (watchlist.length === 0) {
    return (
      <div className="p-12 text-center rounded-2xl border border-dashed border-borderMuted bg-surface/30">
        <Star className="w-8 h-8 text-gray-500 mx-auto mb-3" />
        <h3 className="text-sm font-bold text-gray-300">Watchlist Kosong</h3>
        <p className="text-xs text-gray-400 mt-1 max-w-sm mx-auto">
          Klik ikon bintang pada saham di tabel screener untuk menyimpannya ke daftar pantau harian.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">
          Daftar Pantau Saham ({watchlist.length})
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {watchlist.map((item) => {
          const live = stockMap.get(item.ticker);
          const isPos = live ? live.change_pct >= 0 : true;
          const itemMarket = (item.market as 'IDX' | 'US') || (item.ticker.endsWith('.JK') ? 'IDX' : 'US');

          return (
            <div
              key={item.ticker}
              {...clickableProps(() => onSelectTicker(item.ticker, itemMarket))}
              className={`${FOCUS_RING} p-4 rounded-xl bg-surface border border-borderMuted hover:border-emerald-500/40 hover:bg-surfaceHover transition-all cursor-pointer group flex flex-col justify-between`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-extrabold font-mono text-white group-hover:text-emerald-400 transition-colors">
                      {item.ticker}
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-gray-400 border border-slate-700">
                      {item.market || 'IDX'}
                    </span>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemove(item.ticker);
                    }}
                    className="text-gray-500 hover:text-rose-400 p-1 rounded-md transition-colors"
                    title="Hapus dari Watchlist"
                    aria-label={`Hapus ${item.ticker} dari watchlist`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {live ? (
                  <>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-base font-bold font-mono text-white">
                        {fmtPrice(live.price)}
                      </span>
                      <span className={`text-xs font-mono font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        ({fmtPct(live.change_pct)})
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-borderMuted">
                      <InflowBadge status={live.money_flow_status} cmf={live.cmf20} />
                      <span
                        className={`text-xs font-mono font-bold ${
                          live.score >= 65 ? 'text-emerald-400' : live.score >= 45 ? 'text-gray-200' : 'text-rose-400'
                        }`}
                      >
                        Skor: {live.score}/100
                      </span>
                    </div>
                    {(live.badge_text || live.pullback_label) && (
                      <div className="mt-2 space-y-0.5 text-[11px]">
                        {live.badge_text && <div className="font-semibold text-gray-200">{live.badge_text}</div>}
                        {live.pullback_label && <div className="text-gray-400">{live.pullback_label}</div>}
                        {live.stop_loss ? (
                          <div className="text-gray-500 font-mono">
                            Cut loss: {fmtPrice(live.stop_loss)}
                            {live.price && live.price <= live.stop_loss ? (
                              <span className="ml-1 text-rose-400 font-bold">· sudah tembus</span>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    )}
                  </>
                ) : isScreenerLoading ? (
                  <div className="space-y-2 mt-2 animate-pulse" aria-hidden="true">
                    <div className="h-4 w-28 rounded bg-slate-800" />
                    <div className="h-3 w-40 rounded bg-slate-800" />
                  </div>
                ) : (
                  <p className="text-xs text-gray-500 mt-2">
                    Belum ada di hasil scan {itemMarket} terakhir. Klik untuk membuka analisis lengkap.
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
