import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, BellRing, CheckCheck, Crosshair, Trash2, TrendingUp, Rocket, ShieldAlert, Target, Waves, X } from 'lucide-react';
import { universeApi } from '../api/universe';
import type { AlertItem, AlertKind } from '../types/universe';
import { useToast } from './ui/Toast';

const POLL_MS = 15000;

const KIND_STYLE: Record<AlertKind, { Icon: React.FC<{ className?: string }>; color: string; toast: 'success' | 'warning' | 'info' }> = {
  breakout: { Icon: Rocket, color: 'text-emerald-400', toast: 'success' },
  strong_bullish: { Icon: TrendingUp, color: 'text-emerald-300', toast: 'success' },
  target_hit: { Icon: Target, color: 'text-sky-400', toast: 'success' },
  stop_loss: { Icon: ShieldAlert, color: 'text-rose-400', toast: 'warning' },
  outflow: { Icon: Waves, color: 'text-amber-400', toast: 'warning' },
  entry_zone: { Icon: Crosshair, color: 'text-green-400', toast: 'success' },
};

const timeAgo = (iso: string): string => {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!isFinite(diff) || diff < 60) return 'baru saja';
  if (diff < 3600) return `${Math.floor(diff / 60)} mnt lalu`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} jam lalu`;
  return `${Math.floor(diff / 86400)} hari lalu`;
};

/** Coverage & Control: alerts from scans (mounted in App). Floating bell under the header, top-right. */
export const NotificationCenter: React.FC<{
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}> = ({ onSelectTicker }) => {
  const toast = useToast();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const lastSeenId = useRef<number | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const selectRef = useRef(onSelectTicker);
  selectRef.current = onSelectTicker;

  const refresh = useCallback(async () => {
    try {
      const res = await universeApi.listAlerts({ limit: 40 });
      setAlerts(res.alerts);
      setUnread(res.unread_count);
      const prev = lastSeenId.current;
      lastSeenId.current = res.latest_id;
      if (prev === null) return; // first load: alerts from before this session only show in the list
      const fresh = res.alerts.filter((a) => a.id > prev && !a.read);
      fresh.slice(0, 3).forEach((a) =>
        toast.show({
          kind: KIND_STYLE[a.kind]?.toast ?? 'info',
          title: a.title,
          message: a.message,
          duration: 9000,
          action: { label: 'Lihat detail', onClick: () => selectRef.current(a.ticker, a.market) },
        })
      );
      if (fresh.length > 3) {
        toast.show({ kind: 'info', title: `+${fresh.length - 3} alert lain`, message: 'Buka ikon lonceng untuk melihat semuanya.' });
      }
    } catch {
      /* engine offline: keep the last list, try again next tick */
    }
  }, [toast]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(() => {
      if (!document.hidden) refresh();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const markRead = async (ids: number[] | 'all') => {
    setAlerts((prev) => prev.map((a) => (ids === 'all' || ids.includes(a.id) ? { ...a, read: true } : a)));
    try {
      const res = await universeApi.markRead(ids);
      setUnread(res.unread_count);
    } catch {
      /* next poll resyncs */
    }
  };

  const clearAll = async () => {
    if (!window.confirm(`Hapus semua ${alerts.length} notifikasi? Tindakan ini tidak bisa dibatalkan.`)) return;
    try {
      await universeApi.clearAlerts();
      setAlerts([]);
      setUnread(0);
    } catch {
      toast.show({ kind: 'error', title: 'Gagal menghapus notifikasi', message: 'Engine tidak merespons.' });
    }
  };

  const BellIcon = unread > 0 ? BellRing : Bell;

  return (
    <div ref={panelRef} className="relative z-40">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`relative w-9 h-9 rounded-full border flex items-center justify-center shadow-lg backdrop-blur transition-colors ${
          unread > 0
            ? 'bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-amber-500/25'
            : 'bg-surface/90 border-borderMuted text-gray-400 hover:text-gray-100'
        }`}
        aria-label={unread > 0 ? `${unread} notifikasi belum dibaca` : 'Notifikasi'}
        title="Notifikasi sinyal"
      >
        <BellIcon className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-borderMuted bg-[#0D1320]/95 backdrop-blur shadow-2xl overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-borderMuted">
            <div>
              <div className="text-xs font-bold text-white">Notifikasi Sinyal</div>
              <div className="text-[10px] text-gray-400">{unread > 0 ? `${unread} belum dibaca` : 'Semua sudah dibaca'}</div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => markRead('all')}
                disabled={unread === 0}
                className="p-1.5 rounded-md text-gray-400 hover:text-emerald-300 hover:bg-surfaceHover disabled:opacity-30"
                title="Tandai semua dibaca"
                aria-label="Tandai semua notifikasi dibaca"
              >
                <CheckCheck className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={clearAll}
                disabled={alerts.length === 0}
                className="p-1.5 rounded-md text-gray-400 hover:text-rose-300 hover:bg-surfaceHover disabled:opacity-30"
                title="Hapus semua"
                aria-label="Hapus semua notifikasi"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => setOpen(false)} className="p-1.5 rounded-md text-gray-400 hover:text-gray-100" aria-label="Tutup">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="max-h-[60vh] overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-[11px] text-gray-400 leading-relaxed">
                Belum ada notifikasi. Alert muncul setelah scan bila ada breakout baru, saham naik ke STRONG BULLISH,
                harga masuk zona beli (Watchlist / Top 10), atau saham Watchlist menyentuh Stop Loss / Target.
              </div>
            ) : (
              alerts.map((a) => {
                const st = KIND_STYLE[a.kind] ?? KIND_STYLE.breakout;
                return (
                  <button
                    key={a.id}
                    onClick={() => {
                      if (!a.read) markRead([a.id]);
                      setOpen(false);
                      onSelectTicker(a.ticker, a.market);
                    }}
                    className={`w-full text-left px-3 py-2.5 flex gap-2.5 border-b border-borderMuted/60 hover:bg-surfaceHover transition-colors ${
                      a.read ? 'opacity-60' : ''
                    }`}
                  >
                    <st.Icon className={`w-4 h-4 mt-0.5 shrink-0 ${st.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-gray-100 truncate">{a.title}</span>
                        {!a.read && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />}
                      </div>
                      <div className="text-[11px] text-gray-400 mt-0.5 leading-snug">{a.message}</div>
                      <div className="text-[10px] text-gray-500 mt-1">
                        {a.market} · {timeAgo(a.created_at)}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
