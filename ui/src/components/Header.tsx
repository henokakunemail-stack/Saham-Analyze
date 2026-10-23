import React, { useEffect, useState } from 'react';
import { MarketIndex, ScanStatus } from '../types/stock';
import { EngineConnection } from '../types/feedback';
import type { Market, MarketSession } from '../types/universe';
import { universeApi } from '../api/universe';
import { fmtPct, fmtPrice } from './help/format';
import { Search, RefreshCw, Activity, Zap } from 'lucide-react';

const SESSION_POLL_MS = 60000;

interface Props {
  market: 'IDX' | 'US';
  onMarketChange: (m: 'IDX' | 'US') => void;
  indices: Record<string, MarketIndex>;
  isEngineOnline: boolean;
  onRefresh: () => void;
  isLoading: boolean;
  onSelectTicker: (ticker: string) => void;
  scanStatus?: ScanStatus | null;
  /** 'reconnecting' shows an amber pulsing dot instead of a red offline one. */
  engineState?: EngineConnection;
  /** Show placeholder pills in the market ribbon until the first summary arrives. */
  indicesLoading?: boolean;
  /** Slot rendered at the far right of the header (notification bell). */
  rightSlot?: React.ReactNode;
}

export const Header: React.FC<Props> = ({
  market,
  onMarketChange,
  indices,
  isEngineOnline,
  onRefresh,
  isLoading,
  onSelectTicker,
  scanStatus,
  engineState,
  indicesLoading = false,
  rightSlot,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [sessions, setSessions] = useState<Record<Market, MarketSession> | null>(null);

  // Real auto-scan state (mode + exchange hours) for the pill, refreshed every minute
  useEffect(() => {
    if (!isEngineOnline) return;
    let cancelled = false;
    const load = () => {
      universeApi
        .getSessions()
        .then((s) => {
          if (!cancelled) setSessions(s);
        })
        .catch(() => {
          /* keep the last known state */
        });
    };
    load();
    const id = window.setInterval(load, SESSION_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [isEngineOnline]);
  const session = sessions?.[market];
  const autoScanOff = session?.auto_scan_mode === 'off';

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    // The exchange is resolved from the data (MSFT → US even while the IDX tab is open)
    onSelectTicker(searchQuery.trim().toUpperCase());
    setSearchQuery('');
  };

  const formatLastScan = (isoStr: string | null) => {
    if (!isoStr) return null;
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return null;
    }
  };

  const isScanning = isLoading || Boolean(scanStatus?.is_scanning);
  const lastScanFormatted = formatLastScan(scanStatus?.last_scan_time || null);

  return (
    <header className="h-16 border-b border-borderMuted bg-surface/80 backdrop-blur-md px-4 lg:px-6 flex items-center justify-between gap-3 lg:gap-4 z-20 min-w-0">
      {/* Brand & Market Switcher */}
      <div className="flex items-center gap-6 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 font-bold">
            <Activity className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
              SAHAM <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Analyzer</span>
            </h1>
          </div>
        </div>

        {/* Market Switcher */}
        <div className="flex items-center bg-[#090D16] p-1 rounded-lg border border-borderMuted">
          <button
            onClick={() => onMarketChange('IDX')}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
              market === 'IDX'
                ? 'bg-emerald-500 text-black shadow-sm font-bold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <MarketBadge code="ID" /> IDX (IHSG)
          </button>
          <button
            onClick={() => onMarketChange('US')}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
              market === 'US'
                ? 'bg-blue-500 text-white shadow-sm font-bold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <MarketBadge code="US" /> Saham US
          </button>
        </div>

        {/* Auto-Scan Status Pill */}
        <div
          className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-900/90 border border-slate-700/60 text-[11px]"
          title={session ? `${session.exchange}: ${session.label} · ${session.auto_scan_label ?? ''}` : undefined}
        >
          {isScanning ? (
            <div className="flex items-center gap-1.5 text-amber-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
              <span>Memindai pasar...</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              {/* Whether the exchange is open is what explains moving / still numbers: always shown */}
              <span
                className={`w-2 h-2 rounded-full ${session?.trading_day_live ? 'bg-emerald-400' : 'bg-gray-500'}`}
                aria-hidden="true"
              />
              <span className="text-gray-200">{session?.label ?? 'Status bursa belum tersedia'}</span>
              <span className={`hidden 2xl:inline-flex items-center gap-1 border-l border-slate-700 pl-1.5 font-mono ${autoScanOff ? 'text-gray-400' : 'text-emerald-400'}`}>
                <Zap className={`w-3 h-3 ${autoScanOff ? 'text-gray-500' : 'text-emerald-400 fill-emerald-400/30'}`} />
                {session?.auto_scan_label ?? ''}
              </span>
              {lastScanFormatted && (
                <span className="hidden 2xl:inline text-gray-400 border-l border-slate-700 pl-1.5">{lastScanFormatted}</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Market Ribbon (IHSG, S&P 500, USD/IDR) */}
      <div className="hidden xl:flex flex-1 min-w-0 overflow-hidden items-center gap-4 bg-[#090D16] px-3.5 py-1.5 rounded-lg border border-borderMuted text-xs">
        {Object.keys(indices).length === 0 && (
          indicesLoading ? (
            [0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-2 animate-pulse" aria-hidden="true">
                <div className="h-3 w-12 rounded bg-slate-800" />
                <div className="h-3 w-16 rounded bg-slate-700/60" />
                <div className="h-3 w-10 rounded bg-slate-800" />
              </div>
            ))
          ) : (
            <span className="text-gray-500 text-[11px]">
              {isEngineOnline ? 'Data indeks belum tersedia' : 'Indeks pasar menunggu engine'}
            </span>
          )
        )}
        {Object.entries(indices).map(([label, idx]) => {
          const isPos = idx.change_pct >= 0;
          return (
            <div key={label} className="flex items-center gap-2 shrink-0 whitespace-nowrap">
              <span className="text-gray-400 font-medium">{label}:</span>
              <span className="font-mono text-white font-semibold">
                {idx.price ? fmtPrice(idx.price) : '-'}
              </span>
              <span className={`font-mono text-[11px] font-semibold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                {fmtPct(idx.change_pct)}
              </span>
              <span className="text-slate-700">|</span>
            </div>
          );
        })}
      </div>

      {/* Search Bar & Actions */}
      <div className="flex items-center gap-3 shrink-0">
        {rightSlot}
        <form onSubmit={handleSearchSubmit} className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={market === 'IDX' ? 'Cari BBCA, BBRI, ADRO...' : 'Cari NVDA, AAPL, TSLA...'}
            aria-label="Cari kode saham"
            className="w-52 bg-[#090D16] border border-borderMuted rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 transition-all font-mono"
          />
        </form>

        <button
          onClick={onRefresh}
          disabled={isScanning}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surfaceHover hover:bg-slate-700 border border-borderMuted text-xs text-gray-200 transition-all disabled:opacity-50"
          title="Scan ulang sekarang"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin text-emerald-400' : ''}`} />
          <span className="hidden sm:inline">Scan</span>
        </button>

        {/* Engine status indicator */}
        <div
          className="flex items-center gap-1.5 pl-2 border-l border-borderMuted"
          title={isEngineOnline ? 'Engine analitik terhubung' : 'Engine tidak merespons — mencoba menghubungkan ulang otomatis'}
        >
          <div
            className={`w-2 h-2 rounded-full ${
              isEngineOnline
                ? 'bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]'
                : engineState === 'reconnecting'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-rose-500'
            }`}
          />
          <span className="text-[11px] font-mono text-gray-400 hidden xl:inline">
            {isEngineOnline ? 'Online' : engineState === 'reconnecting' ? 'Menyambung…' : 'Offline'}
          </span>
        </div>
      </div>
    </header>
  );
};

/** Text badge instead of a flag emoji (Windows renders 🇮🇩/🇺🇸 as plain letters). */
const MarketBadge: React.FC<{ code: 'ID' | 'US' }> = ({ code }) => (
  <span className="inline-block mr-0.5 px-1 rounded-sm border border-current text-[9px] font-mono font-bold leading-[14px] opacity-80 align-[1px]">
    {code}
  </span>
);
