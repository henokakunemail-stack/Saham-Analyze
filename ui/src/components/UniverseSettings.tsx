import React, { useCallback, useEffect, useState } from 'react';
import { Bell, Clock, Globe2, Loader2, Plus, RotateCcw, Star, X, Undo2, Radar, MonitorSmartphone } from 'lucide-react';
import { universeApi } from '../api/universe';
import type { AlertKind, AlertPrefs, AutoScanMode, Market, MarketSession, UniverseInfo } from '../types/universe';
import { useToast } from './ui/Toast';

const MODE_OPTIONS: { id: AutoScanMode; label: string; desc: string }[] = [
  { id: 'market_hours', label: 'Jam bursa', desc: 'Scan tiap 5 menit saat bursa buka + 1x setelah tutup (disarankan)' },
  { id: 'always', label: '24/7', desc: 'Scan terus, termasuk malam & akhir pekan (boros kuota data)' },
  { id: 'off', label: 'Mati', desc: 'Hanya scan manual' },
];

const KIND_ORDER: AlertKind[] = ['entry_zone', 'breakout', 'strong_bullish', 'stop_loss', 'target_hit', 'outflow'];

const Toggle: React.FC<{ checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }> = ({ checked, onChange, disabled }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative w-8 h-[18px] rounded-full transition-colors shrink-0 disabled:opacity-40 ${checked ? 'bg-emerald-500' : 'bg-gray-700'}`}
  >
    <span className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-all ${checked ? 'left-[16px]' : 'left-[2px]'}`} />
  </button>
);

export const SessionPill: React.FC<{ session: MarketSession }> = ({ session }) => (
  <span className={`inline-flex items-center gap-1.5 text-[11px] ${session.is_open ? 'text-emerald-300' : 'text-gray-400'}`}>
    <span className={`w-1.5 h-1.5 rounded-full ${session.is_open ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
    {session.label}
  </span>
);

/** Coverage & Control: which tickers get scanned, alert & auto-scan preferences (mounted in SettingsView). */
export const UniverseSettings: React.FC<{ isEngineOnline: boolean }> = ({ isEngineOnline }) => {
  const toast = useToast();
  const [market, setMarket] = useState<Market>('IDX');
  const [info, setInfo] = useState<UniverseInfo | null>(null);
  const [sessions, setSessions] = useState<Record<Market, MarketSession> | null>(null);
  const [mode, setMode] = useState<AutoScanMode>('market_hours');
  const [prefs, setPrefs] = useState<AlertPrefs | null>(null);
  const [input, setInput] = useState('');
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadUniverse = useCallback(async (m: Market) => {
    try {
      setInfo(await universeApi.getUniverse(m));
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Gagal memuat daftar scan');
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await universeApi.getSessions());
    } catch {
      /* engine offline */
    }
  }, []);

  useEffect(() => {
    if (!isEngineOnline) return;
    loadUniverse(market);
  }, [market, isEngineOnline, loadUniverse]);

  useEffect(() => {
    if (!isEngineOnline) return;
    loadSessions();
    universeApi.getAutoScan().then((r) => setMode(r.mode)).catch(() => undefined);
    universeApi.getAlertPrefs().then(setPrefs).catch(() => undefined);
    const id = window.setInterval(loadSessions, 60000);
    return () => window.clearInterval(id);
  }, [isEngineOnline, loadSessions]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const t = input.trim();
    if (!t || adding) return;
    setAdding(true);
    try {
      const res = await universeApi.addTicker(market, t);
      if (res.universe) setInfo(res.universe);
      toast.show({ kind: res.ok ? 'success' : 'warning', title: res.ok ? 'Saham ditambahkan' : 'Tidak bisa menambahkan', message: res.message });
      if (res.ok) setInput('');
    } catch (err) {
      toast.show({ kind: 'error', title: 'Gagal menambahkan', message: err instanceof Error ? err.message : 'Engine tidak merespons.' });
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (ticker: string) => {
    setBusy(true);
    try {
      const res = await universeApi.removeTicker(market, ticker);
      if (res.universe) setInfo(res.universe);
      if (!res.ok) toast.show({ kind: 'info', title: ticker, message: res.message });
    } catch (err) {
      toast.show({ kind: 'error', title: 'Gagal menghapus', message: err instanceof Error ? err.message : 'Engine tidak merespons.' });
    } finally {
      setBusy(false);
    }
  };

  const handleRestore = async (ticker: string) => {
    setBusy(true);
    try {
      const res = await universeApi.addTicker(market, ticker);
      if (res.universe) setInfo(res.universe);
    } catch {
      /* ignore; list stays as is */
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm(`Kembalikan daftar scan ${market} ke default? Saham tambahan Anda akan dihapus (Watchlist tetap di-scan).`)) return;
    setBusy(true);
    try {
      setInfo(await universeApi.resetUniverse(market));
      toast.show({ kind: 'success', title: `Daftar scan ${market} direset` });
    } catch (err) {
      toast.show({ kind: 'error', title: 'Gagal reset', message: err instanceof Error ? err.message : '' });
    } finally {
      setBusy(false);
    }
  };

  const handleMode = async (m: AutoScanMode) => {
    const prev = mode;
    setMode(m);
    try {
      await universeApi.setAutoScan(m);
      loadSessions();
    } catch {
      setMode(prev);
      toast.show({ kind: 'error', title: 'Gagal menyimpan mode auto-scan' });
    }
  };

  const handlePref = async (patch: { kinds?: Partial<Record<AlertKind, boolean>>; os_toast?: boolean }) => {
    if (!prefs) return;
    const prev = prefs;
    setPrefs({ ...prefs, kinds: { ...prefs.kinds, ...(patch.kinds ?? {}) }, os_toast: patch.os_toast ?? prefs.os_toast });
    try {
      setPrefs(await universeApi.setAlertPrefs(patch));
    } catch {
      setPrefs(prev);
      toast.show({ kind: 'error', title: 'Gagal menyimpan preferensi notifikasi' });
    }
  };

  const removedDefaults = info?.defaults.filter((d) => d.removed) ?? [];
  const pct = info ? Math.min(100, (info.total_requested / info.limit) * 100) : 0;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Radar className="w-4 h-4 text-emerald-400" /> Cakupan Scan & Notifikasi
        </h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Atur saham yang dipindai, kapan auto-scan berjalan, dan alert apa yang ingin Anda terima.
        </p>
      </div>

      {!isEngineOnline && (
        <div className="p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-[11px] text-amber-200">
          Engine offline — pengaturan cakupan scan tidak dapat dimuat.
        </div>
      )}

      {/* Market session + auto-scan mode */}
      <div className="p-4 rounded-xl border border-borderMuted bg-surface/60 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-200">
          <Clock className="w-3.5 h-3.5 text-sky-400" /> Status Bursa & Auto-Scan
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {(['IDX', 'US'] as Market[]).map((m) => {
            const s = sessions?.[m];
            return (
              <div key={m} className="p-2.5 rounded-lg bg-[#090D16] border border-borderMuted">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-gray-200">{m === 'IDX' ? 'IDX (BEI)' : 'US (NYSE/Nasdaq)'}</span>
                  {s && <span className="text-[10px] text-gray-500">{s.open_time}–{s.close_time} {s.tz_label}</span>}
                </div>
                {s ? (
                  <div className="mt-1 space-y-0.5">
                    <SessionPill session={s} />
                    <div className="text-[10px] text-gray-400">{s.auto_scan_label}</div>
                    {s.note && <div className="text-[10px] text-amber-300/80">{s.note}</div>}
                  </div>
                ) : (
                  <div className="text-[10px] text-gray-500 mt-1">Memuat…</div>
                )}
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {MODE_OPTIONS.map((o) => (
            <button
              key={o.id}
              onClick={() => handleMode(o.id)}
              disabled={!isEngineOnline}
              className={`p-2.5 rounded-lg border text-left transition-colors disabled:opacity-40 ${
                mode === o.id
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                  : 'border-borderMuted bg-[#090D16] text-gray-300 hover:border-gray-600'
              }`}
            >
              <div className="text-xs font-semibold">{o.label}</div>
              <div className="text-[10px] text-gray-400 mt-0.5 leading-snug">{o.desc}</div>
            </button>
          ))}
        </div>
        <p className="text-[10px] text-gray-500">Hari libur bursa belum diperhitungkan; pada hari libur scan tetap berjalan pada jam bursa.</p>
      </div>

      {/* Universe */}
      <div className="p-4 rounded-xl border border-borderMuted bg-surface/60 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-200">
            <Globe2 className="w-3.5 h-3.5 text-emerald-400" /> Daftar Saham yang Di-scan
          </div>
          <div className="flex items-center bg-[#090D16] p-0.5 rounded-lg border border-borderMuted">
            {(['IDX', 'US'] as Market[]).map((m) => (
              <button
                key={m}
                onClick={() => setMarket(m)}
                className={`px-3 py-1 text-[11px] font-semibold rounded-md ${market === m ? 'bg-emerald-500/15 text-emerald-300' : 'text-gray-400 hover:text-gray-200'}`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {loadError && <div className="text-[11px] text-rose-300">{loadError}</div>}

        {info && (
          <>
            <div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-gray-300">
                  <b className="text-white">{info.count}</b> saham di-scan · batas {info.limit}
                </span>
                <span className="text-gray-500">
                  {info.watchlist.length} dari Watchlist · {info.added.length} tambahan
                </span>
              </div>
              <div className="h-1.5 mt-1 rounded-full bg-gray-800 overflow-hidden">
                <div className={`h-full ${info.truncated ? 'bg-rose-500' : pct > 85 ? 'bg-amber-400' : 'bg-emerald-500'}`} style={{ width: `${pct}%` }} />
              </div>
              {info.truncated && (
                <div className="text-[10px] text-rose-300 mt-1">
                  {info.total_requested - info.limit} saham melebihi batas dan tidak di-scan. Watchlist & tambahan Anda diprioritaskan.
                </div>
              )}
            </div>

            <form onSubmit={handleAdd} className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value.toUpperCase())}
                placeholder={market === 'IDX' ? 'Kode saham, mis. TINS atau WIFI.JK' : 'Ticker, mis. ORCL atau BRK-B'}
                className="flex-1 bg-[#090D16] border border-borderMuted rounded-lg px-3 py-1.5 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:border-emerald-500/50"
                disabled={!isEngineOnline || adding}
                maxLength={12}
              />
              <button
                type="submit"
                disabled={!isEngineOnline || adding || !input.trim()}
                className="px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs font-semibold flex items-center gap-1.5 hover:bg-emerald-500/25 disabled:opacity-40"
              >
                {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                {adding ? 'Memeriksa…' : 'Tambah'}
              </button>
            </form>

            <div className="flex flex-wrap gap-1.5 max-h-52 overflow-y-auto">
              {info.items.map((it) => {
                const fromWatchlist = it.sources.includes('watchlist');
                const isUser = it.sources.includes('user') && !it.sources.includes('default');
                return (
                  <span
                    key={it.ticker}
                    className={`inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-md border text-[11px] font-mono ${
                      !it.scanned
                        ? 'border-rose-500/30 bg-rose-500/5 text-rose-300/70 line-through'
                        : fromWatchlist
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                        : isUser
                        ? 'border-sky-500/30 bg-sky-500/10 text-sky-200'
                        : 'border-borderMuted bg-[#090D16] text-gray-300'
                    }`}
                    title={fromWatchlist ? 'Dari Watchlist (hapus dari Watchlist untuk berhenti scan)' : isUser ? 'Tambahan Anda' : 'Default'}
                  >
                    {fromWatchlist && <Star className="w-3 h-3" />}
                    {it.ticker.replace('.JK', '')}
                    {!fromWatchlist ? (
                      <button
                        onClick={() => handleRemove(it.ticker)}
                        disabled={busy}
                        className="p-0.5 rounded hover:bg-rose-500/20 hover:text-rose-300 text-gray-500"
                        aria-label={`Hapus ${it.ticker}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    ) : (
                      <span className="w-1" />
                    )}
                  </span>
                );
              })}
            </div>

            {removedDefaults.length > 0 && (
              <div className="text-[11px] text-gray-400">
                <span className="mr-1">Default yang dihapus:</span>
                {removedDefaults.map((d) => (
                  <button
                    key={d.ticker}
                    onClick={() => handleRestore(d.ticker)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 mr-1.5 mb-1 px-1.5 py-0.5 rounded border border-borderMuted text-gray-500 hover:text-emerald-300 hover:border-emerald-500/30 font-mono"
                    title="Kembalikan ke daftar scan"
                  >
                    <Undo2 className="w-3 h-3" />
                    {d.ticker.replace('.JK', '')}
                  </button>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-3 text-[10px] text-gray-500">
                <span className="inline-flex items-center gap-1"><Star className="w-3 h-3 text-amber-300" /> Watchlist</span>
                <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-sky-500/40" /> Tambahan</span>
                <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-gray-600" /> Default</span>
              </div>
              <button
                onClick={handleReset}
                disabled={busy || !isEngineOnline}
                className="text-[11px] text-gray-400 hover:text-gray-100 flex items-center gap-1 disabled:opacity-40"
              >
                <RotateCcw className="w-3 h-3" /> Reset ke default
              </button>
            </div>
          </>
        )}
      </div>

      {/* Alert preferences */}
      <div className="p-4 rounded-xl border border-borderMuted bg-surface/60 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-200">
          <Bell className="w-3.5 h-3.5 text-amber-400" /> Jenis Notifikasi
        </div>
        {prefs ? (
          <div className="space-y-2">
            {KIND_ORDER.map((k) => (
              <label key={k} className="flex items-center justify-between gap-3 text-xs text-gray-300">
                <span>{prefs.labels[k] ?? k}</span>
                <Toggle checked={prefs.kinds[k]} onChange={(v) => handlePref({ kinds: { [k]: v } })} />
              </label>
            ))}
            <div className="border-t border-borderMuted pt-2">
              <label className="flex items-center justify-between gap-3 text-xs text-gray-300">
                <span className="flex items-center gap-1.5">
                  <MonitorSmartphone className="w-3.5 h-3.5 text-gray-400" />
                  Juga tampilkan notifikasi Windows
                  <span className="text-[10px] text-gray-500">(saat aplikasi di belakang)</span>
                </span>
                <Toggle checked={prefs.os_toast} onChange={(v) => handlePref({ os_toast: v })} />
              </label>
            </div>
            <p className="text-[10px] text-gray-500">
              Alert Stop Loss, Target & uang keluar hanya untuk saham di Watchlist. Alert yang sama tidak diulang dalam 12 jam.
            </p>
          </div>
        ) : (
          <div className="text-[11px] text-gray-500">{isEngineOnline ? 'Memuat…' : '—'}</div>
        )}
      </div>
    </div>
  );
};
