import React, { useEffect, useState } from 'react';
import { LayoutDashboard, TrendingUp, History, Waves, Star, Settings, ShieldCheck } from 'lucide-react';
import { universeApi } from '../api/universe';
import { marketApi } from '../api/market';
import type { Market, MarketSession } from '../types/universe';

export type ActiveTab = 'screener' | 'top10' | 'history' | 'inflow' | 'watchlist' | 'settings';

interface Props {
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
  watchlistCount: number;
}

/** Small exchange open/closed line per market, refreshed every minute. */
const MarketSessions: React.FC = () => {
  const [sessions, setSessions] = useState<Record<Market, MarketSession> | null>(null);
  const [breadth, setBreadth] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => {
      universeApi
        .getSessions()
        .then((s) => alive && setSessions(s))
        .catch(() => undefined);
      marketApi
        .getBreadth('IDX', 1)
        .then((b) => alive && setBreadth(b.label || null))
        .catch(() => undefined);
    };
    load();
    const id = window.setInterval(load, 60000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  if (!sessions) return null;
  return (
    <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted space-y-1.5">
      {(['IDX', 'US'] as Market[]).map((m) => {
        const s = sessions[m];
        if (!s) return null;
        return (
          <div key={m} className="flex items-start gap-1.5 text-[10px] leading-snug" title={s.auto_scan_label}>
            <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${s.is_open ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
            <span className={s.is_open ? 'text-emerald-300' : 'text-gray-400'}>
              <b className="font-semibold">{m}</b> · {s.label}
            </span>
          </div>
        );
      })}
      {breadth && (
        <div className="text-[10px] leading-snug text-gray-400 pt-1 border-t border-borderMuted/60" title="Breadth pasar IDX: persentase saham di atas EMA50">
          Breadth IDX: <span className="text-gray-200">{breadth}</span>
        </div>
      )}
    </div>
  );
};

export const Sidebar: React.FC<Props> = ({ activeTab, onSelectTab, watchlistCount }) => {
  const navItems = [
    {
      id: 'screener' as ActiveTab,
      label: 'Screener Saham',
      desc: 'Ranking & Kondisi Teknikal',
      icon: LayoutDashboard,
    },
    {
      id: 'top10' as ActiveTab,
      label: 'Top 10 Potensial',
      desc: 'Rencana beli · cut loss · target',
      icon: TrendingUp,
    },
    {
      id: 'history' as ActiveTab,
      label: 'Histori Prediksi',
      desc: 'Rekam jejak & uji historis',
      icon: History,
    },
    {
      id: 'inflow' as ActiveTab,
      label: 'Radar Aliran Uang',
      desc: 'Indikasi Uang Masuk / Keluar',
      icon: Waves,
    },
    {
      id: 'watchlist' as ActiveTab,
      label: 'Watchlist',
      desc: 'Saham Pilihan',
      icon: Star,
      badge: watchlistCount > 0 ? watchlistCount : undefined,
    },
    {
      id: 'settings' as ActiveTab,
      label: 'Pengaturan',
      desc: 'Konfigurasi & Engine',
      icon: Settings,
    },
  ];

  return (
    <aside className="w-64 shrink-0 border-r border-borderMuted bg-surface/50 p-4 flex flex-col justify-between gap-4 overflow-y-auto select-none">
      <div className="space-y-6">
        <div className="px-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-gray-400">Navigasi Utama</p>
        </div>

        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition-all group ${
                  isActive
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-surfaceHover border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400' : 'text-gray-400 group-hover:text-gray-200'}`} />
                  <div>
                    <div className="text-xs font-medium">{item.label}</div>
                    <div className="text-[10px] text-gray-400">{item.desc}</div>
                  </div>
                </div>
                {item.badge !== undefined && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-gray-300 border border-slate-700">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="space-y-2">
        <MarketSessions />
        <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted text-[11px] space-y-1.5 text-gray-400">
          <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Strategi: Pullback dalam Uptrend</span>
          </div>
          <p className="text-[10px] leading-relaxed text-gray-400">
            Skor mengutamakan tren 6 bulan yang sedang koreksi sehat, dan otomatis defensif saat pasar bearish/krisis.
          </p>
        </div>
      </div>
    </aside>
  );
};
