import React, { useCallback, useEffect, useState } from 'react';
import { ClipboardCheck, Coffee, MapPin, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { PlanCheckpoint as Checkpoint, RecapOutcome, SessionRecap } from '../types/stock';
import { POSITION_CLS } from './FlowSummaryCard';
import { ActionStatusBadge } from './ActionStatusBadge';
import { clickableProps, FOCUS_RING } from '../lib/a11y';

const fmt = (v?: number | null) =>
  v === undefined || v === null ? '-' : v.toLocaleString('id-ID', { maximumFractionDigits: 2 });

const POLL_MS = 120000;

const fmtDay = (d?: string | null) => {
  if (!d) return '-';
  const date = new Date(`${d.slice(0, 10)}T00:00:00`);
  return isNaN(date.getTime())
    ? d
    : date.toLocaleDateString('id-ID', { weekday: 'short', day: 'numeric', month: 'short' });
};

const OUTCOME: Record<RecapOutcome, { label: string; count: string; cls: string }> = {
  STOP: { label: 'Kena cut loss', count: 'kena cut loss', cls: 'text-rose-300' },
  TP2: { label: 'Mencapai TP2', count: 'mencapai TP2', cls: 'text-emerald-300' },
  TP1: { label: 'Mencapai TP1', count: 'mencapai TP1', cls: 'text-emerald-300' },
  FILLED: { label: 'Harga beli terisi', count: 'harga beli terisi', cls: 'text-cyan-300' },
  ZONE: { label: 'Masuk zona beli', count: 'masuk zona beli', cls: 'text-sky-300' },
  ABOVE: { label: 'Tidak turun ke zona', count: 'tidak turun ke zona', cls: 'text-gray-400' },
};

/** After the close: the session that just ended, read against the plans it traded on. */
const RecapView: React.FC<{
  recap: SessionRecap;
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}> = ({ recap, market, onSelectTicker }) => {
  const summary = (Object.keys(OUTCOME) as RecapOutcome[])
    .filter((k) => recap.counts?.[k])
    .map((k) => `${recap.counts[k]} ${OUTCOME[k].count}`);
  return (
    <div className="p-4 rounded-2xl border space-y-3 bg-surface border-borderMuted">
      <div className="flex flex-wrap items-center gap-2">
        <ClipboardCheck className="w-4 h-4 text-violet-300" />
        <h2 className="text-sm font-bold text-white">Rekap Sesi {fmtDay(recap.session_date)}</h2>
        <span className="text-[10px] text-gray-400">
          vs rencana dari penutupan {fmtDay(recap.plan_as_of)}
          {recap.final === false ? ' · harga penutupan belum final' : ''}
        </span>
      </div>
      <p className="text-[11px] text-gray-400 leading-relaxed">
        Apa yang terjadi pada sesi tadi terhadap rencana yang berlaku saat itu
        {recap.list_from_plan ? ` (Top 10 yang tampil selama sesi)` : ''}. Rencana untuk sesi berikutnya ada di kartu di bawah.
        {summary.length > 0 && <span className="block text-gray-300 mt-0.5">{summary.join(' · ')}.</span>}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-gray-500 text-left">
              <th className="py-1 pr-3 font-semibold">Saham</th>
              <th className="py-1 pr-3 font-semibold text-right">Tutup</th>
              <th className="py-1 pr-3 font-semibold">Hasil vs rencana</th>
              <th className="py-1 pr-3 font-semibold text-right">Rentang sesi</th>
              <th className="py-1 font-semibold text-right">Rencana (beli · cut loss · TP1)</th>
            </tr>
          </thead>
          <tbody>
            {recap.rows.map((r) => (
              <tr
                key={r.ticker}
                {...clickableProps(() => onSelectTicker(r.ticker, market))}
                aria-label={`Buka detail ${r.ticker.replace('.JK', '')}`}
                className={`${FOCUS_RING} border-t border-borderMuted/60 cursor-pointer hover:bg-white/5 align-top`}
              >
                <td className="py-1.5 pr-3 whitespace-nowrap">
                  <span className="font-mono font-bold text-white">{r.ticker.replace('.JK', '')}</span>
                  <span className="ml-1.5 text-[9px] text-gray-500">{r.source}</span>
                </td>
                <td className="py-1.5 pr-3 text-right font-mono text-gray-200">
                  {fmt(r.close)}
                  {r.change_pct !== null && r.change_pct !== undefined && (
                    <span className={`block text-[10px] ${r.change_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                      {r.change_pct >= 0 ? '+' : ''}
                      {r.change_pct.toLocaleString('id-ID', { maximumFractionDigits: 2 })}%
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-3">
                  <span className={`font-semibold ${OUTCOME[r.outcome]?.cls ?? 'text-gray-300'}`}>
                    {OUTCOME[r.outcome]?.label ?? r.outcome}
                  </span>
                  <span className="block text-[10px] text-gray-400">{r.text}</span>
                </td>
                <td className="py-1.5 pr-3 text-right font-mono text-gray-300">
                  {fmt(r.low)}–{fmt(r.high)}
                </td>
                <td className="py-1.5 text-right font-mono">
                  <span className="text-cyan-300/90">{fmt(r.recommended_entry ?? r.entry_high)}</span>
                  <span className="text-gray-500"> · </span>
                  <span className="text-rose-300">{fmt(r.stop_loss)}</span>
                  <span className="text-gray-500"> · </span>
                  <span className="text-emerald-300">{fmt(r.target_tp1)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

/**
 * Where today's price stands against each Top-10 / watchlist plan while the exchange day is live
 * (during the BEI lunch break: "Cek Tengah Hari"); after the close, the recap of that session.
 */
export const PlanCheckpoint: React.FC<{
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}> = ({ market, onSelectTicker }) => {
  const [data, setData] = useState<Checkpoint | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await api.getPlanCheckpoint(market);
    if (r) setData(r);
    setFailed(!r);
    setLoading(false);
  }, [market]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  if (!data) {
    return failed ? (
      <div className="p-3 rounded-2xl border border-borderMuted bg-surface text-[11px] text-gray-300 flex items-center justify-between gap-2">
        <span>Posisi harga terhadap rencana belum bisa dimuat.</span>
        <button type="button" onClick={load} className="text-emerald-300 hover:text-emerald-200 font-semibold">
          Coba lagi
        </button>
      </div>
    ) : null;
  }
  if (!data.live) {
    return data.recap?.rows?.length ? (
      <RecapView recap={data.recap} market={market} onSelectTicker={onSelectTicker} />
    ) : null;
  }
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
              <tr className="text-gray-400 text-left">
                <th className="py-1 pr-3 font-semibold">Saham</th>
                <th className="py-1 pr-3 font-semibold text-right">Harga</th>
                <th className="py-1 pr-3 font-semibold">Status</th>
                <th className="py-1 pr-3 font-semibold">Posisi harga</th>
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
                  <td className="py-1.5 pr-3">
                    {r.action_status ? <ActionStatusBadge status={r.action_status} compact /> : <span className="text-gray-500">-</span>}
                  </td>
                  <td
                    className={`py-1.5 pr-3 ${
                      // "In the zone" is only a buy for a LAYAK plan; otherwise it is just where the price is
                      r.status === 'IN_ZONE' && r.action_status && r.action_status !== 'LAYAK'
                        ? 'text-gray-300'
                        : POSITION_CLS[r.status] ?? 'text-gray-300'
                    }`}
                  >
                    {r.label}
                    {r.status === 'IN_ZONE' && r.action_status && r.action_status !== 'LAYAK' && (
                      <span className="block text-[10px] text-amber-300/90">status {r.action_status} — belum layak dibeli</span>
                    )}
                    {r.touched_stop && r.status !== 'BELOW_STOP' && (
                      <span className="block text-[10px] text-rose-300/80">sempat menyentuh cut loss</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-gray-300">
                    {fmt(r.entry_low)}–{fmt(r.entry_high)}
                    {r.recommended_entry ? (
                      <span className="block text-[10px] text-cyan-300/90 font-sans">Harga beli (limit) {fmt(r.recommended_entry)}</span>
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
