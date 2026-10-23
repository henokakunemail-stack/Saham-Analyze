import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api, onApiError } from './api/client';
import { feedbackApi } from './api/feedback';
import { API_BASE } from './api/base';
import { ScreenerItem, MarketIndex, WatchlistItem, ScanStatus } from './types/stock';
import { ApiErrorEvent, EngineConnection, ScanProgress } from './types/feedback';
import { Header } from './components/Header';
import { Sidebar, ActiveTab } from './components/Sidebar';
import { TopPicks } from './components/TopPicks';
import { Top10Potential } from './components/Top10Potential';
import { PredictionHistoryView } from './components/PredictionHistoryView';
import { ScreenerTable } from './components/ScreenerTable';
import { StockDetailModal } from './components/StockDetailModal';
import { Watchlist } from './components/Watchlist';
import { SettingsView } from './components/SettingsView';
import { ScanProgressBar } from './components/ScanProgressBar';
import { NotificationCenter } from './components/NotificationCenter';
import { DisclaimerBanner } from './components/DisclaimerBanner';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useToast } from './components/ui/Toast';
import { RefreshCw, SearchX, WifiOff } from 'lucide-react';

const IDLE_POLL_MS = 6000;
const ACTIVE_POLL_MS = 1500;
/** Same failing call shows at most one toast per window. */
const TOAST_DEDUP_MS = 20000;

/** Merge partial scan results into the current list (update by ticker, keep sorted by score). */
function mergeByTicker(prev: ScreenerItem[], fresh: ScreenerItem[]): ScreenerItem[] {
  const map = new Map(prev.map((s) => [s.ticker, s]));
  fresh.forEach((s) => map.set(s.ticker, s));
  return [...map.values()].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

export const App: React.FC = () => {
  const toast = useToast();
  const [market, setMarket] = useState<'IDX' | 'US'>('IDX');
  // Top 10 first: it answers "what can I do today" (plan, status); the screener is for digging
  const [activeTab, setActiveTab] = useState<ActiveTab>('top10');
  const [screenerItems, setScreenerItems] = useState<ScreenerItem[]>([]);
  const [indices, setIndices] = useState<Record<string, MarketIndex>>({});
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlistLoaded, setWatchlistLoaded] = useState<boolean>(false);
  const [selectedStock, setSelectedStock] = useState<{ ticker: string; market: 'IDX' | 'US' } | null>(null);
  const [engine, setEngine] = useState<EngineConnection>('online');
  const [reconnectAttempt, setReconnectAttempt] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [initialLoaded, setInitialLoaded] = useState<boolean>(false);
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [progress, setProgress] = useState<ScanProgress | null>(null);

  const isEngineOnline = engine === 'online';

  // Refs read by the long-lived polling loop / error listener
  const marketRef = useRef(market);
  const engineRef = useRef<EngineConnection>(engine);
  const isLoadingRef = useRef(false);
  const progressActiveRef = useRef(false);
  const lastScanTimeRef = useRef<string | null>(null);
  const lastToastRef = useRef<Map<string, number>>(new Map());
  const pollNowRef = useRef<() => void>(() => {});
  marketRef.current = market;
  engineRef.current = engine;

  const watchlistSet = React.useMemo(() => {
    return new Set(watchlist.map((w) => w.ticker));
  }, [watchlist]);

  const handleSelectTicker = async (ticker: string, m?: 'IDX' | 'US') => {
    if (m || ticker.endsWith('.JK') || ticker.startsWith('^')) {
      setSelectedStock({ ticker, market: m || (ticker.endsWith('.JK') ? 'IDX' : market) });
      return;
    }
    // A bare code can belong to either exchange (MSFT while the IDX tab is open): ask the engine
    const found = await api.resolveTicker(ticker, market);
    if (found) setSelectedStock(found);
  };

  /** Reload the cached screener without triggering a scan (after a background scan finished). */
  const reloadScreenerQuietly = useCallback(async () => {
    const m = marketRef.current;
    const fresh = await api.getScreener(m, false, true); // cached_only: never starts a scan
    if (fresh.length > 0 && marketRef.current === m) setScreenerItems(fresh);
  }, []);

  // Desktop window lifecycle: heartbeat keeps the engine alive; "bye" lets it shut down when
  // the window is really closed (a reload sends heartbeats again, so it is not treated as a close).
  useEffect(() => {
    const beat = () => {
      fetch(`${API_BASE}/app/heartbeat`, { method: 'POST', keepalive: true }).catch(() => {});
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') beat();
    };
    const bye = () => {
      try {
        navigator.sendBeacon(`${API_BASE}/app/bye`);
      } catch {
        // ignore
      }
    };
    beat();
    const id = window.setInterval(beat, 20000);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pagehide', bye);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pagehide', bye);
    };
  }, []);

  // Load initial data. Summary & watchlist don't wait for the screener (which may run a full scan).
  const loadData = useCallback(async (force: boolean = false) => {
    const m = market;
    setIsLoading(true);
    isLoadingRef.current = true;
    pollNowRef.current(); // start fast progress polling right away
    try {
      const online = await api.getHealth();
      if (!online) {
        setEngine('reconnecting');
        return;
      }
      setEngine('online');

      const side = Promise.all([
        api.getMarketSummary().then(setIndices),
        api.getWatchlist().then((wl) => {
          setWatchlist(wl);
          setWatchlistLoaded(true);
        }),
      ]);
      const scr = await api.getScreener(m, force);
      if (marketRef.current === m && scr.length > 0) {
        setScreenerItems(scr);
        if (force) toast.show({ kind: 'success', title: 'Scan selesai', message: `${scr.length} saham ${m} dianalisis.` });
      }
      await side;
    } finally {
      isLoadingRef.current = false;
      setIsLoading(false);
      setInitialLoaded(true);
    }
  }, [market, toast]);

  const loadDataRef = useRef(loadData);
  loadDataRef.current = loadData;

  useEffect(() => {
    loadData(false);
  }, [loadData]);

  // API failures → de-duplicated toasts. Connection loss is shown by the reconnect banner instead.
  useEffect(() => {
    const RETRY: Record<string, () => void> = {
      screener: () => loadDataRef.current(false),
      market: () => loadDataRef.current(false),
      watchlist: () => loadDataRef.current(false),
    };
    const showToast = (e: ApiErrorEvent) => {
      const now = Date.now();
      const last = lastToastRef.current.get(e.op);
      if (last && now - last < TOAST_DEDUP_MS) return;
      lastToastRef.current.set(e.op, now);
      const retry = RETRY[e.op];
      toast.show({
        kind: 'error',
        title: e.title,
        message: e.message,
        action: retry ? { label: 'Coba lagi', onClick: retry } : undefined,
      });
    };
    return onApiError(async (e) => {
      if (e.kind === 'network') {
        if (engineRef.current !== 'online') return;
        // Engine gone? Then the banner explains it; otherwise it's a one-off failure worth a toast.
        const online = await api.getHealth();
        if (!online) {
          setEngine('reconnecting');
          pollNowRef.current();
          return;
        }
      }
      showToast(e);
    });
  }, [toast]);

  // One polling loop: health + scan status (idle, 6s) or live progress (scanning, 1.5s),
  // and backoff reconnect attempts while the engine is unreachable.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;
    let running = false;

    const tick = async () => {
      if (running) return;
      running = true;
      let delay = IDLE_POLL_MS;
      try {
        const online = await api.getHealth();
        if (cancelled) return;

        if (!online) {
          attempts += 1;
          setReconnectAttempt(attempts);
          setEngine('reconnecting');
          delay = Math.min(2000 * Math.pow(1.5, attempts - 1), 10000);
          return;
        }

        if (engineRef.current !== 'online') {
          setEngine('online');
          if (attempts > 0) {
            toast.show({ kind: 'success', title: 'Engine terhubung kembali', message: 'Memuat ulang data terbaru…', duration: 3500 });
          }
          attempts = 0;
          setReconnectAttempt(0);
          if (!isLoadingRef.current) loadDataRef.current(false);
        }

        const wasActive = progressActiveRef.current;
        const prog = await feedbackApi.getScanProgress(wasActive || isLoadingRef.current);
        if (cancelled) return;

        if (prog) {
          progressActiveRef.current = prog.active;
          setProgress(prog);
          const sameMarket = prog.market === marketRef.current;

          // Stream finished tickers into the table while the scan runs
          if (prog.active && sameMarket && prog.results && prog.results.length > 0) {
            const partial = prog.results;
            setScreenerItems((prev) => mergeByTicker(prev, partial));
          }

          if (wasActive && !prog.active) {
            if (prog.error) {
              toast.show({ kind: 'error', title: 'Scan pasar terhenti', message: prog.error });
            } else if (prog.failed > 0) {
              toast.show({
                kind: 'warning',
                title: `${prog.failed} dari ${prog.total} saham gagal dipindai`,
                message: `Data tidak tersedia: ${prog.failed_tickers.slice(0, 6).join(', ')}${prog.failed_tickers.length > 6 ? ', …' : ''}`,
              });
            }
            // Background scans don't return results to us: fetch the fresh ranking
            if (sameMarket && !isLoadingRef.current) reloadScreenerQuietly();
          }
        }

        const scanning = Boolean(prog?.active) || isLoadingRef.current;
        if (scanning) {
          // /screener/status waits on the scan lock while a scan runs, so don't call it now
          setScanStatus((s) => (s ? { ...s, is_scanning: true } : s));
          delay = ACTIVE_POLL_MS;
        } else {
          const status = await api.getScanStatus();
          if (cancelled || !status) return;
          setScanStatus(status);
          if (
            status.last_scan_time &&
            lastScanTimeRef.current &&
            status.last_scan_time !== lastScanTimeRef.current
          ) {
            reloadScreenerQuietly();
          }
          if (status.last_scan_time) lastScanTimeRef.current = status.last_scan_time;
        }
      } finally {
        running = false;
        if (!cancelled) {
          window.clearTimeout(timer);
          timer = window.setTimeout(tick, delay);
        }
      }
    };

    pollNowRef.current = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(tick, 0);
    };
    timer = window.setTimeout(tick, ACTIVE_POLL_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      pollNowRef.current = () => {};
    };
  }, [toast, reloadScreenerQuietly]);

  const handleToggleWatchlist = async (ticker: string) => {
    if (watchlistSet.has(ticker)) {
      const ok = await api.removeFromWatchlist(ticker);
      if (ok) setWatchlist((prev) => prev.filter((w) => w.ticker !== ticker));
    } else {
      const effectiveMarket = ticker.endsWith('.JK') ? 'IDX' : market;
      const ok = await api.addToWatchlist({ ticker, market: effectiveMarket });
      if (ok) setWatchlist((prev) => [...prev, { ticker, market: effectiveMarket, added_at: new Date().toISOString() }]);
    }
  };

  const scanActive = Boolean(progress?.active);
  const screenerPending = screenerItems.length === 0 && (isLoading || !initialLoaded || scanActive);
  const effectiveScanStatus: ScanStatus | null =
    scanActive && scanStatus ? { ...scanStatus, is_scanning: true } : scanStatus;

  const noResultsState = (
    <div className="p-10 text-center rounded-2xl border border-dashed border-borderMuted bg-surface/30">
      <SearchX className="w-8 h-8 text-gray-500 mx-auto mb-3" />
      <h3 className="text-sm font-bold text-gray-300">Belum ada hasil scan untuk pasar {market}</h3>
      <p className="text-xs text-gray-400 mt-1 max-w-md mx-auto">
        {isEngineOnline
          ? 'Engine belum pernah memindai pasar ini atau scan terakhir gagal mengambil data. Jalankan scan untuk membuat peringkat saham.'
          : 'Data akan dimuat otomatis setelah engine analitik terhubung kembali.'}
      </p>
      {isEngineOnline && (
        <button
          onClick={() => loadData(true)}
          className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 text-xs font-semibold"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Scan sekarang
        </button>
      )}
    </div>
  );

  const inflowItems = screenerItems.filter(
    (s) => s.money_flow_status === 'STRONG_INFLOW' || s.money_flow_status === 'STRONG_OUTFLOW'
  );

  return (
    <div className="h-screen w-screen flex flex-col bg-[#090D16] overflow-hidden">
      {/* Top Header */}
      <Header
        market={market}
        onMarketChange={(m) => {
          if (m === market) return;
          setMarket(m);
          setScreenerItems([]);
        }}
        indices={indices}
        isEngineOnline={isEngineOnline}
        engineState={engine}
        onRefresh={() => loadData(true)}
        isLoading={isLoading}
        indicesLoading={!initialLoaded || (isLoading && Object.keys(indices).length === 0)}
        onSelectTicker={(t) => handleSelectTicker(t)}
        scanStatus={effectiveScanStatus}
        rightSlot={<NotificationCenter market={market} onSelectTicker={(t, m) => handleSelectTicker(t, m)} />}
      />

      <ScanProgressBar market={market} progress={progress} />

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Navigation Sidebar */}
        <Sidebar
          activeTab={activeTab}
          onSelectTab={(t) => setActiveTab(t)}
          watchlistCount={watchlist.length}
        />

        {/* Center Main Scrollable Canvas */}
        <main className="flex-1 min-w-0 overflow-y-auto p-6 space-y-6">
          {!isEngineOnline && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-200 text-xs flex items-center justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <WifiOff className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <div className="font-semibold flex items-center gap-2">
                    <RefreshCw className="w-3 h-3 animate-spin" />
                    Menghubungkan ulang ke engine analitik…
                    {reconnectAttempt > 0 && (
                      <span className="font-mono text-amber-300/70 font-normal">percobaan ke-{reconnectAttempt}</span>
                    )}
                  </div>
                  <div className="text-amber-200/70">
                    Data terakhir tetap ditampilkan dan akan diperbarui otomatis saat engine kembali.
                    {reconnectAttempt >= 5 && (
                      <>
                        {' '}Jika tidak kunjung pulih, jalankan ulang aplikasi atau{' '}
                        <code className="bg-black/30 px-1 py-0.5 rounded font-mono">python engine/main.py</code>.
                      </>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => pollNowRef.current()}
                className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-200 hover:bg-amber-500/30 font-semibold shrink-0"
              >
                Coba sekarang
              </button>
            </div>
          )}

          {activeTab === 'screener' && (
            <>
              {/* Top Opportunity Cards */}
              <TopPicks
                items={screenerItems}
                isLoading={screenerPending}
                onSelectTicker={(t, m) => handleSelectTicker(t, m)}
              />

              {/* Full Interactive Table */}
              {screenerPending ? (
                <TableSkeleton />
              ) : screenerItems.length === 0 ? (
                noResultsState
              ) : (
                <ScreenerTable
                  market={market}
                  items={screenerItems}
                  onSelectTicker={(t, m) => handleSelectTicker(t, m)}
                  onToggleWatchlist={handleToggleWatchlist}
                  watchlistSet={watchlistSet}
                />
              )}
            </>
          )}

          {activeTab === 'top10' && (
            <Top10Potential
              market={market}
              items={screenerItems}
              isLoading={screenerPending}
              onScan={isEngineOnline ? () => loadData(true) : undefined}
              onSelectTicker={(t, m) => handleSelectTicker(t, m)}
              onToggleWatchlist={handleToggleWatchlist}
              watchlistSet={watchlistSet}
            />
          )}

          {activeTab === 'history' && (
            <PredictionHistoryView
              market={market}
              onSelectTicker={(t, m) => handleSelectTicker(t, m ?? market)}
            />
          )}

          {activeTab === 'inflow' && (
            <div className="space-y-4">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider text-white">
                  Radar Aliran Uang (Smart Money Inflow & Outflow)
                </h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  Saham dengan indikasi aliran uang ekstrem (status kuat dari CMF 20 hari): masuk deras vs keluar deras.
                  Ini indikator dari harga &amp; volume, bukan data kepemilikan institusi.
                </p>
              </div>

              {/* Inflow-filtered screener table */}
              {screenerPending ? (
                <TableSkeleton />
              ) : screenerItems.length === 0 ? (
                noResultsState
              ) : inflowItems.length === 0 ? (
                <div className="p-10 text-center rounded-2xl border border-dashed border-borderMuted bg-surface/30 text-xs text-gray-400">
                  Dari {screenerItems.length} saham yang dipindai, belum ada yang menunjukkan aliran uang masuk/keluar yang kuat (CMF ekstrem).
                </div>
              ) : (
                <ScreenerTable
                  enableFilters={false}
                  items={inflowItems}
                  onSelectTicker={(t, m) => handleSelectTicker(t, m)}
                  onToggleWatchlist={handleToggleWatchlist}
                  watchlistSet={watchlistSet}
                />
              )}
            </div>
          )}

          {activeTab === 'watchlist' && (
            <Watchlist
              watchlist={watchlist}
              screenerItems={screenerItems}
              isLoading={!watchlistLoaded && (isLoading || !initialLoaded)}
              isScreenerLoading={screenerPending}
              onSelectTicker={(t, m) => handleSelectTicker(t, m)}
              onRemove={(t) => handleToggleWatchlist(t)}
            />
          )}

          {activeTab === 'settings' && <SettingsView isEngineOnline={isEngineOnline} />}

          <DisclaimerBanner />
        </main>
      </div>

      {/* Stock Detail & Interactive Chart Modal */}
      {selectedStock && (
        // Own boundary: a render error in the detail modal must not blank the whole app
        <ErrorBoundary
          key={`${selectedStock.market}:${selectedStock.ticker}`}
          fallback={(error) => (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true">
              <div className="max-w-sm w-full p-5 rounded-2xl bg-[#0F1626] border border-rose-500/30 text-center space-y-3">
                <h2 className="text-sm font-bold text-white">Detail {selectedStock.ticker} gagal ditampilkan</h2>
                <p className="text-[11px] font-mono text-rose-300 break-words">{error?.message || 'Kesalahan tampilan'}</p>
                <button
                  onClick={() => setSelectedStock(null)}
                  className="px-3 py-1.5 rounded-lg bg-surface border border-borderMuted text-gray-200 text-xs font-semibold hover:border-slate-600"
                >
                  Tutup
                </button>
              </div>
            </div>
          )}
        >
          <StockDetailModal
            ticker={selectedStock.ticker}
            market={selectedStock.market}
            onClose={() => setSelectedStock(null)}
            isPinned={watchlistSet.has(selectedStock.ticker)}
            onToggleWatchlist={handleToggleWatchlist}
            onOpenSettings={() => setActiveTab('settings')}
          />
        </ErrorBoundary>
      )}
    </div>
  );
};

/** Placeholder rows shaped like the screener table while the first data arrives. */
const TableSkeleton: React.FC = () => (
  <div className="rounded-2xl border border-borderMuted bg-surface overflow-hidden" aria-busy="true" aria-label="Memuat tabel screener">
    <div className="h-10 border-b border-borderMuted bg-slate-900/40" />
    {Array.from({ length: 8 }).map((_, i) => (
      <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-borderMuted/50 animate-pulse">
        <div className="h-3.5 w-20 rounded bg-slate-700/60" />
        <div className="h-3 w-16 rounded bg-slate-800" />
        <div className="h-3 w-12 rounded bg-slate-800" />
        <div className="h-5 w-24 rounded-full bg-slate-800" />
        <div className="flex-1" />
        <div className="h-3 w-10 rounded bg-slate-800" />
        <div className="h-3 w-14 rounded bg-slate-700/60" />
      </div>
    ))}
  </div>
);
