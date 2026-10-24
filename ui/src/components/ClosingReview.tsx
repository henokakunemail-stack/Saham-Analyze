import React, { useCallback, useEffect, useState } from 'react';
import { ClipboardCheck, ChevronDown, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { ClosingReview as Review, ClosingReviewRow, RecapOutcome } from '../types/stock';
import { ActionStatusBadge } from './ActionStatusBadge';
import { InfoTip } from './help/InfoTip';
import { TrackRecordLine } from './TrackRecord';
import { clickableProps, FOCUS_RING } from '../lib/a11y';

const fmt = (v?: number | null) =>
  v === undefined || v === null ? '-' : v.toLocaleString('id-ID', { maximumFractionDigits: 2 });

const fmtDay = (d?: string | null) => {
  if (!d) return '-';
  const date = new Date(`${d.slice(0, 10)}T00:00:00`);
  return isNaN(date.getTime()) ? d : date.toLocaleDateString('id-ID', { weekday: 'short', day: 'numeric', month: 'short' });
};

const fmtR = (r: number) => `${r >= 0 ? '+' : '−'}${Math.abs(r).toLocaleString('id-ID', { maximumFractionDigits: 2 })} R`;

const POLL_MS = 15 * 60 * 1000; // the analysis only changes when a new close becomes final
const VISIBLE = 5;

export const OUTCOME: Record<RecapOutcome, { label: string; count: string; cls: string }> = {
  STOP: { label: 'Kena cut loss', count: 'kena cut loss', cls: 'text-rose-300' },
  TP2: { label: 'Mencapai TP2', count: 'mencapai TP2', cls: 'text-emerald-300' },
  TP1: { label: 'Mencapai TP1', count: 'mencapai TP1', cls: 'text-emerald-300' },
  FILLED: { label: 'Harga beli terisi', count: 'harga beli terisi', cls: 'text-cyan-300' },
  ZONE: { label: 'Masuk zona beli', count: 'masuk zona beli', cls: 'text-sky-300' },
  ABOVE: { label: 'Tidak turun ke zona', count: 'tidak turun ke zona', cls: 'text-gray-400' },
};

const Row: React.FC<{ r: ClosingReviewRow; market: 'IDX' | 'US'; onSelect: (t: string, m?: 'IDX' | 'US') => void }> = ({
  r,
  market,
  onSelect,
}) => {
  const a = r.assessment;
  const p = r.plan;
  const out = r.recap ? OUTCOME[r.recap.outcome] : null;
  return (
    <details className="group rounded-xl border border-borderMuted bg-[#090D16]/60">
      <summary className="list-none cursor-pointer select-none px-3 py-2.5 flex flex-wrap items-start gap-x-3 gap-y-1 hover:bg-white/5 rounded-xl">
        <ChevronDown className="w-3.5 h-3.5 mt-0.5 text-gray-400 transition-transform group-open:rotate-180" />
        <div className="min-w-[90px] flex items-center gap-1.5 flex-wrap">
          <span className="font-mono font-bold text-white">{r.ticker.replace('.JK', '')}</span>
          {r.status && <ActionStatusBadge status={r.status} compact />}
          {!r.in_top && (
            <span className="text-[10px] text-gray-400">{r.watchlist ? 'Watchlist' : 'keluar dari Top 10'}</span>
          )}
        </div>
        <div className="flex-1 min-w-[220px] space-y-0.5">
          <p className="text-xs text-gray-100">{a?.verdict ?? 'Belum ada rencana untuk sesi berikutnya.'}</p>
          {a && (a.caution || a.fill_pct !== null) && (
            <p className="text-[11px]">
              {a.fill_pct !== null && <span className="text-gray-300">Peluang terisi ±{a.fill_pct}%</span>}
              {a.caution && (
                <span className="text-amber-300">
                  {a.fill_pct !== null ? ' · ' : ''}
                  {a.caution}
                </span>
              )}
            </p>
          )}
          {out && (
            <p className="text-[11px]">
              <span className="text-gray-400">Sesi lalu: </span>
              <span className={`font-semibold ${out.cls}`}>{out.label}</span>
            </p>
          )}
        </div>
        {p?.recommended_entry ? (
          <div className="text-[11px] font-mono text-right whitespace-nowrap">
            <div>
              beli <span className="text-cyan-300 font-bold">{fmt(p.recommended_entry)}</span>
            </div>
            <div className="text-gray-400">
              CL <span className="text-rose-300">{fmt(p.stop_loss)}</span> · TP1{' '}
              <span className="text-emerald-300">{fmt(p.target_tp1)}</span>
            </div>
          </div>
        ) : null}
      </summary>
      <div className="px-4 pb-3 pt-1 space-y-2 text-[11px] text-gray-300">
        {a && a.points.length > 0 && (
          <ul className="space-y-1">
            {a.points.map((pt) => (
              <li key={pt} className="flex gap-1.5">
                <span className="text-gray-500" aria-hidden="true">•</span>
                <span>{pt}</span>
              </li>
            ))}
          </ul>
        )}
        {r.recap && (
          <p className="text-gray-400">
            Sesi {fmtDay(r.recap.session_date)} (tutup {fmt(r.recap.close)}
            {r.recap.change_pct !== null && r.recap.change_pct !== undefined
              ? `, ${r.recap.change_pct >= 0 ? '+' : ''}${r.recap.change_pct.toLocaleString('id-ID', { maximumFractionDigits: 2 })}%`
              : ''}
            ; rentang {fmt(r.recap.low)}–{fmt(r.recap.high)}): {r.recap.text}.
          </p>
        )}
        <button
          type="button"
          {...clickableProps(() => onSelect(r.ticker, market))}
          className={`${FOCUS_RING} text-emerald-300 hover:text-emerald-200 font-semibold`}
        >
          Buka analisis lengkap →
        </button>
      </div>
    </details>
  );
};

/**
 * Analisa Penutupan: everything is measured from the last final close (not from minute-to-minute
 * prices): what the last session did to its plan, and the plan for the next session with an
 * assessment built from backtest numbers.
 */
export const ClosingReview: React.FC<{
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}> = ({ market, onSelectTicker }) => {
  const [data, setData] = useState<Review | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await api.getClosingReview(market);
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
        <span>Analisa penutupan belum bisa dimuat.</span>
        <button type="button" onClick={load} className="text-emerald-300 hover:text-emerald-200 font-semibold">
          Coba lagi
        </button>
      </div>
    ) : null;
  }
  if (data.rows.length === 0) return null;

  const live = Boolean(data.session?.trading_day_live);
  const counts = data.counts
    ? (Object.keys(OUTCOME) as RecapOutcome[]).filter((k) => data.counts?.[k]).map((k) => `${data.counts![k]} ${OUTCOME[k].count}`)
    : [];
  const hist = data.status_history ?? {};

  return (
    <section aria-label="Analisa penutupan" className="p-4 rounded-2xl border border-borderMuted bg-surface space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <ClipboardCheck className="w-4 h-4 text-violet-300" />
          <h2 className="text-sm font-bold text-white">Analisa Penutupan</h2>
          <span className="text-[11px] text-gray-400">patokan: penutupan {fmtDay(data.plan_as_of)} (final)</span>
        </div>
        <button
          type="button"
          onClick={load}
          className="text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1"
          aria-label="Muat ulang analisa penutupan"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Perbarui
        </button>
      </div>

      <div className="text-xs text-gray-300 space-y-1 leading-relaxed">
        {live && (
          <p className="text-sky-300">
            Bursa sedang berjalan — analisa ini tetap memakai penutupan terakhir; harga hari ini tidak dipakai untuk menilai.
          </p>
        )}
        {data.session_date && counts.length > 0 && (
          <p>
            <span className="text-gray-400">Sesi {fmtDay(data.session_date)}:</span> {counts.join(' · ')}.
          </p>
        )}
        {hist.LAYAK && (
          <p className="text-[11px] text-gray-400 flex flex-wrap items-center gap-x-1">
            Rata-rata historis per transaksi: LAYAK <span className="text-gray-200">{fmtR(hist.LAYAK.avg_r)}</span> · TUNGGU{' '}
            <span className="text-gray-200">{fmtR(hist.TUNGGU.avg_r)}</span> · HINDARI{' '}
            <span className="text-gray-200">{fmtR(hist.HINDARI.avg_r)}</span>
            <InfoTip label="Tentang angka historis">
              <p className="text-xs leading-relaxed">
                Uji historis periode Des 2025–Okt 2026 dengan aturan sekarang (termasuk syarat untung ke TP1 ≥ 1,2× risiko),
                sebelum biaya transaksi (±0,4% beli+jual ≈ 0,1 R). Angka LAYAK berasal dari hanya 37 transaksi — belum
                cukup untuk dipastikan; rekam jejak nyata di Histori Prediksi yang menentukan. R = besar risiko per
                transaksi (harga beli − cut loss).
              </p>
            </InfoTip>
          </p>
        )}
        <TrackRecordLine market={market} />
      </div>

      <div className="space-y-1.5">
        {(showAll ? data.rows : data.rows.slice(0, VISIBLE)).map((r) => (
          <Row key={r.ticker} r={r} market={market} onSelect={onSelectTicker} />
        ))}
      </div>
      {data.rows.length > VISIBLE && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="w-full py-1.5 rounded-lg border border-borderMuted text-xs font-semibold text-gray-300 hover:text-white hover:bg-white/5"
        >
          {showAll ? 'Tampilkan lebih sedikit' : `Tampilkan semua (${data.rows.length} saham)`}
        </button>
      )}
    </section>
  );
};
