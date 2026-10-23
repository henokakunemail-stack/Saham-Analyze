import React, { useCallback, useEffect, useState } from 'react';
import { Coffee, MapPin, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { PlanCheckpoint as Checkpoint } from '../types/stock';
import { POSITION_CLS } from './FlowSummaryCard';
import { clickableProps, FOCUS_RING } from '../lib/a11y';

const fmt = (v?: number | null) =>
  v === undefined || v === null ? '-' : v.toLocaleString('id-ID', { maximumFractionDigits: 2 });

const POLL_MS = 120000;

/**
 * Where today's price stands against each Top-10 / watchlist plan. Shown only while the
 * exchange day is live; during the BEI lunch break it becomes the "Cek Tengah Hari" list.
 */
export const PlanCheckpoint: React.FC<{
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}> = ({ market, onSelectTicker }) => {
  const [data, setData] = useState<Checkpoint | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await api.getPlanCheckpoint(market);
    setData(r);
    setLoading(false);
  }, [market]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  if (!data?.live) return null;
  const lunch = data.session?.session === 'lunch_break';
  const tz = data.session?.tz_label ?? '';
  const ends = data.session?.session_ends ? new Date(data.session.session_ends) : null;
  const endsAt = ends && !isNaN(ends.getTime())
    ? ends.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', timeZone: market === 'IDX' ? 'Asia/Jakarta' : 'America/New_York' })
    : null;

  return (
    <div className={`p-4 rounded-2xl border space-y-3 ${lunch ? 'bg-amber-500/5 border-amber-500/30' : 'bg-surface border-borderMuted'}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {lunch ? <Coffee className="w-4 h-4 text-amber-300" /> : <MapPin className="w-4 h-4 text-sky-300" />}
          <h2 className="text-sm font-bold text-white">
            {lunch ? 'Cek Tengah Hari' : 'Posisi Harga vs Rencana'}
          </h2>
          <span className="text-[10px] text-gray-400">
            {data.session?.session_name}
            {endsAt ? (lunch ? ` · sesi 2 buka ${endsAt} ${tz}` : ` · sampai ${endsAt} ${tz}`) : ''}
          </span>
        </div>
        <button
          type="button"
          onClick={load}
          className="text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1"
          aria-label="Perbarui posisi harga"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Perbarui
        </button>
      </div>

      <p className="text-[11px] text-gray-400 leading-relaxed">
        Rencana tetap dari penutupan terakhir yang final; yang dibandingkan hanya harga hari ini (data tertunda ±15 menit).
        {lunch && ' Harga sedang diam — waktu yang tepat untuk memutuskan sebelum sesi 2. Sesi 2 bisa dibuka melompat bila ada berita selama istirahat.'}
      </p>

      {data.rows.length === 0 ? (
        <p className="text-[11px] text-gray-500">{data.message ?? 'Belum ada saham untuk dicek.'}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-500 text-left">
                <th className="py-1 pr-3 font-semibold">Saham</th>
                <th className="py-1 pr-3 font-semibold text-right">Harga</th>
                <th className="py-1 pr-3 font-semibold">Status</th>
                <th className="py-1 pr-3 font-semibold text-right">Zona beli</th>
                <th className="py-1 pr-3 font-semibold text-right">Cut loss</th>
                <th className="py-1 font-semibold text-right">TP1</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr
                  key={r.ticker}
                  {...clickableProps(() => onSelectTicker(r.ticker, market))}
                  aria-label={`Buka detail ${r.ticker.replace('.JK', '')}`}
                  className={`${FOCUS_RING} border-t border-borderMuted/60 cursor-pointer hover:bg-white/5`}
                >
                  <td className="py-1.5 pr-3">
                    <span className="font-mono font-bold text-white">{r.ticker.replace('.JK', '')}</span>
                    <span className="ml-1.5 text-[9px] text-gray-500">{r.source}</span>
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-gray-200">{fmt(r.price)}</td>
                  <td className={`py-1.5 pr-3 ${POSITION_CLS[r.status] ?? 'text-gray-300'}`}>
                    {r.label}
                    {r.touched_stop && r.status !== 'BELOW_STOP' && (
                      <span className="block text-[10px] text-rose-300/80">sempat menyentuh cut loss</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-gray-300">
                    {fmt(r.entry_low)}–{fmt(r.entry_high)}
                    {r.recommended_entry ? (
                      <span className="block text-[10px] text-cyan-300/90 font-sans">Harga saran (limit) {fmt(r.recommended_entry)}</span>
                    ) : null}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-rose-300">{fmt(r.stop_loss)}</td>
                  <td className="py-1.5 text-right font-mono text-emerald-300">{fmt(r.target_tp1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
