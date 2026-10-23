import React, { useEffect, useState } from 'react';
import { History, RefreshCw, Sparkles, ChevronDown, ChevronRight, ArrowUpRight } from 'lucide-react';
import { PredictionItem, PredictionHistoryResponse } from '../types/stock';
import { api } from '../api/client';
import { signalsApi } from '../api/signals';
import { BacktestPanel } from './BacktestPanel';
import { AiTrackRecord } from './AiTrackRecord';
import { useToast } from './ui/Toast';
import { fmtPrice } from './help/format';
import { FOCUS_RING } from '../lib/a11y';

/** 10 trading days first: the same horizon as the calibration and the plan simulation. */
const EVAL_HORIZONS = [10, 20, 40];
const DEFAULT_HORIZON = EVAL_HORIZONS[0];
const BACKFILL_DAYS = 45; // calendar days back, enough for a 20-trading-day evaluation to finish
const TAB_KEY = 'saham.historyTab';

type Tab = 'predictions' | 'backtest' | 'ai';
const TABS: { id: Tab; label: string }[] = [
  { id: 'predictions', label: 'Prediksi' },
  { id: 'backtest', label: 'Uji Historis' },
  { id: 'ai', label: 'Validasi AI' },
];

const fmtSigned = (v: number | null | undefined, suffix = '%') =>
  v === null || v === undefined || isNaN(v) ? '-' : `${v >= 0 ? '+' : ''}${v.toLocaleString('id-ID', { maximumFractionDigits: 2 })}${suffix}`;

const STATUS: Record<string, { text: string; cls: string }> = {
  HIT_TP2: { text: '🎯 Kena TP2', cls: 'bg-emerald-500/20 text-emerald-200 border-emerald-500/40' },
  HIT_TP1: { text: '✅ Kena TP1', cls: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' },
  STOPPED_OUT: { text: '🛑 Cut loss', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  EXPIRED: { text: '⌛ Habis waktu', cls: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
  IN_PROGRESS: { text: '⏳ Berjalan', cls: 'bg-amber-500/10 text-amber-300 border-amber-500/30' },
  WAITING_ENTRY: { text: '🕓 Menunggu zona beli', cls: 'bg-sky-500/10 text-sky-300 border-sky-500/30' },
  NOT_FILLED: { text: '⊘ Harga beli tidak tersentuh', cls: 'bg-slate-500/10 text-gray-400 border-slate-600/40' },
  CANCELLED: { text: '✖ Batal (dibuka di bawah cut loss)', cls: 'bg-slate-500/10 text-gray-400 border-slate-600/40' },
};

const readTab = (): Tab => {
  try {
    const t = localStorage.getItem(TAB_KEY) as Tab | null;
    return t && TABS.some((x) => x.id === t) ? t : 'predictions';
  } catch {
    return 'predictions';
  }
};

interface Props {
  market: 'IDX' | 'US';
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
}

/** Histori Prediksi: three short answers instead of one long page. */
export const PredictionHistoryView: React.FC<Props> = ({ market, onSelectTicker }) => {
  const [tab, setTab] = useState<Tab>(readTab);

  const choose = (t: Tab) => {
    setTab(t);
    try {
      localStorage.setItem(TAB_KEY, t);
    } catch {
      /* per-viewer convenience only */
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-white flex items-center gap-2">
            <History className="w-5 h-5 text-emerald-400" /> Histori Prediksi
          </h1>
          <p className="text-xs text-gray-400">Seberapa sering rencana aplikasi benar-benar berhasil.</p>
        </div>
        <div className="flex rounded-xl border border-borderMuted overflow-hidden text-xs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => choose(t.id)}
              className={`px-3.5 py-1.5 font-semibold ${
                tab === t.id ? 'bg-emerald-500/20 text-emerald-300' : 'bg-surfaceHover text-gray-400 hover:text-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5 rounded-2xl bg-surface border border-borderMuted">
        {tab === 'predictions' && <PredictionsTab market={market} onSelectTicker={onSelectTicker} />}
        {tab === 'backtest' && <BacktestPanel market={market} />}
        {tab === 'ai' && <AiTrackRecord market={market} onSelectTicker={onSelectTicker} />}
      </div>
    </div>
  );
};

const PredictionsTab: React.FC<Props> = ({ market, onSelectTicker }) => {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [backfilling, setBackfilling] = useState(false);
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState('');
  const [horizon, setHorizon] = useState(DEFAULT_HORIZON);
  const [data, setData] = useState<PredictionHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = async (d?: string, h = horizon) => {
    setLoading(true);
    setError(null);
    try {
      const res = await signalsApi.getPredictionHistory(market, d, h);
      setData(res);
      if (res) {
        setDates(res.available_dates || []);
        setDate(res.snapshot_date || '');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gagal memuat riwayat prediksi.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  const backfill = async () => {
    setBackfilling(true);
    const res = await api.triggerBackfill(market, BACKFILL_DAYS);
    if (res.ok) await load(res.snapshot_date);
    else toast.show({ kind: 'error', title: 'Gagal membuat snapshot', message: res.message || 'Backfill tidak berhasil.' });
    setBackfilling(false);
  };

  const price = (v?: number | null) => fmtPrice(v);

  const items = data?.items || [];
  const s = data?.summary;
  const bench = market === 'IDX' ? 'IHSG' : 'S&P 500';

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {dates.length > 0 && (
          <label className="flex items-center gap-1.5 text-gray-400">
            Rencana tanggal
            <select
              value={date}
              onChange={(e) => load(e.target.value)}
              className="bg-surfaceHover text-white font-semibold px-2 py-1 rounded-lg border border-borderMuted"
            >
              {dates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex items-center gap-1.5 text-gray-400">
          diberi waktu
          <select
            value={horizon}
            onChange={(e) => {
              const h = Number(e.target.value);
              setHorizon(h);
              load(date || undefined, h);
            }}
            className="bg-surfaceHover text-white font-semibold px-2 py-1 rounded-lg border border-borderMuted"
          >
            {EVAL_HORIZONS.map((h) => (
              <option key={h} value={h}>
                {h} hari bursa
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() => load(date || undefined)}
          disabled={loading}
          className="p-1.5 rounded-lg bg-surfaceHover border border-borderMuted text-gray-300 hover:text-white"
          aria-label="Muat ulang"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-emerald-400' : ''}`} />
        </button>
      </div>

      {loading && !data ? (
        <p className="text-xs text-gray-400">Memuat…</p>
      ) : error ? (
        <div className="py-8 text-center space-y-3" role="alert">
          <p className="text-sm font-semibold text-rose-300">Gagal memuat riwayat prediksi</p>
          <p className="text-xs text-gray-400 max-w-md mx-auto">{error}</p>
          <button
            onClick={() => load(date || undefined)}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-surfaceHover border border-borderMuted text-gray-200 hover:text-white text-xs font-semibold inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Coba lagi
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="py-8 text-center space-y-3">
          <p className="text-sm font-semibold text-white">Belum ada rekam jejak prediksi</p>
          <p className="text-xs text-gray-400 max-w-md mx-auto">
            Prediksi dicatat otomatis setiap scan, hanya untuk saham bersinyal beli. Saat pasar krisis tidak ada yang
            dicatat. Untuk melihat contoh, buat snapshot dari data {BACKFILL_DAYS} hari lalu.
          </p>
          <button
            onClick={backfill}
            disabled={backfilling}
            className="px-3 py-1.5 rounded-lg bg-emerald-500 text-black text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5" /> {backfilling ? 'Memproses…' : `Buat snapshot ${BACKFILL_DAYS} hari lalu`}
          </button>
        </div>
      ) : (
        <>
          {/* The answer first */}
          {s && (
            <>
              <p className="text-sm text-gray-200 leading-relaxed">
                Rencana {date}: <b className="text-white">{s.total_predictions} saham</b>
                {' — '}
                {[
                  s.hit_tp1_count + s.hit_tp2_count > 0 && `${s.hit_tp1_count + s.hit_tp2_count} kena TP`,
                  s.stopped_out_count > 0 && `${s.stopped_out_count} cut loss`,
                  (s.expired_count ?? 0) > 0 && `${s.expired_count} habis waktu`,
                  s.in_progress_count > 0 && `${s.in_progress_count} berjalan`,
                  (s.waiting_entry_count ?? 0) > 0 && `${s.waiting_entry_count} menunggu zona beli`,
                  (s.not_filled_count ?? 0) + (s.cancelled_count ?? 0) > 0 &&
                    `${(s.not_filled_count ?? 0) + (s.cancelled_count ?? 0)} tidak sempat dibeli`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                .
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi
                  label="Kena TP dulu"
                  value={s.win_rate_pct === null ? '-' : fmtSigned(s.win_rate_pct).replace('+', '')}
                  hint={s.closed_count ? `${s.win_count} dari ${s.closed_count} yang selesai` : 'belum ada yang selesai'}
                />
                <Kpi
                  label="Rata-rata hasil"
                  value={s.avg_r !== null && s.avg_r !== undefined ? fmtSigned(s.avg_r, 'R') : fmtSigned(s.avg_return_pct)}
                  hint={s.avg_r !== null && s.avg_r !== undefined ? `≈ ${fmtSigned(s.avg_return_pct)} per transaksi` : 'yang sudah selesai'}
                  tone={(s.avg_return_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}
                />
                <Kpi
                  label="Sempat dibeli"
                  value={s.fill_rate_pct === null || s.fill_rate_pct === undefined ? '-' : fmtSigned(s.fill_rate_pct).replace('+', '')}
                  hint="harga sempat turun ke zona beli"
                />
                <Kpi
                  label={`vs ${bench}`}
                  value={fmtSigned(s.avg_excess_return_pct)}
                  hint={`${s.beat_benchmark_count ?? 0}/${s.benchmark_compared_count ?? 0} mengalahkan indeks`}
                />
              </div>
            </>
          )}

          {/* One line per stock; details on click */}
          <div className="rounded-xl border border-borderMuted overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-surfaceHover/50 text-gray-400 text-[10px] uppercase tracking-wider text-left">
                  <th className="py-2 px-3 font-semibold">Saham</th>
                  <th className="py-2 px-3 font-semibold">Rencana</th>
                  <th className="py-2 px-3 font-semibold">Hasil</th>
                  <th className="py-2 px-3 font-semibold text-right">Return</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-borderMuted/40">
                {items.map((it) => (
                  <Row
                    key={it.ticker}
                    it={it}
                    isOpen={open === it.ticker}
                    onToggle={() => setOpen(open === it.ticker ? null : it.ticker)}
                    onChart={() => onSelectTicker(it.ticker, market)}
                    price={price}
                    bench={bench}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-gray-500">
            Dianggap terbeli bila harga turun ke harga beli dalam 5 hari bursa. Cut loss diperiksa sebelum TP; hasil tanpa
            biaya transaksi.
            <button onClick={backfill} disabled={backfilling} className="underline hover:text-gray-300 ml-1">
              {backfilling ? 'membuat snapshot…' : `buat snapshot ${BACKFILL_DAYS} hari lalu`}
            </button>
          </p>
        </>
      )}
    </div>
  );
};

const Row: React.FC<{
  it: PredictionItem;
  isOpen: boolean;
  onToggle: () => void;
  onChart: () => void;
  price: (v?: number | null) => string;
  bench: string;
}> = ({ it, isOpen, onToggle, onChart, price, bench }) => {
  const st = STATUS[it.status] ?? STATUS.IN_PROGRESS;
  const zone = it.plan_checked && it.entry_low && it.entry_high;
  const bought = it.plan_checked ? it.filled : true;
  const when = it.exit_date || it.hit_date;
  return (
    <>
      <tr
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        tabIndex={0}
        aria-expanded={isOpen}
        aria-label={`${it.ticker.replace('.JK', '')}: ${isOpen ? 'tutup' : 'buka'} detail`}
        className={`${FOCUS_RING} cursor-pointer hover:bg-surfaceHover/40`}
      >
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-1.5 font-bold text-white">
            {isOpen ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
            {it.ticker.replace('.JK', '')}
          </div>
          <div className="text-[10px] text-gray-500 pl-4">skor {it.score}</div>
        </td>
        <td className="py-2.5 px-3 text-gray-300">
          {zone ? (
            <>
              Beli limit <span className="font-mono text-cyan-300">{price(it.recommended_entry ?? it.entry_high)}</span>
              <div className="text-[10px] text-gray-400">
                zona <span className="font-mono">{price(it.entry_low)}–{price(it.entry_high)}</span>
              </div>
            </>
          ) : (
            <>
              Harga <span className="font-mono">{price(it.price_at_prediction)}</span>
            </>
          )}
          <div className="text-[10px] text-gray-400">
            TP1 <span className="font-mono text-emerald-300/80">{price(it.target_tp1)}</span> · cut loss{' '}
            <span className="font-mono text-rose-300/80">{price(it.stop_loss)}</span>
          </div>
        </td>
        <td className="py-2.5 px-3">
          <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-semibold ${st.cls}`}>{st.text}</span>
          {when && <div className="text-[10px] text-gray-500 mt-0.5">{when}</div>}
        </td>
        <td className="py-2.5 px-3 text-right font-mono">
          {bought ? (
            <>
              <span className={it.return_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{fmtSigned(it.return_pct)}</span>
              {it.r_multiple !== null && it.r_multiple !== undefined && (
                <div className="text-[10px] text-gray-500">{fmtSigned(it.r_multiple, 'R')}</div>
              )}
            </>
          ) : (
            <span className="text-gray-500">—</span>
          )}
        </td>
      </tr>
      {isOpen && (
        <tr className="bg-surfaceHover/20">
          <td colSpan={4} className="px-3 py-3 space-y-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-gray-400">
              <span>
                Harga saat prediksi <b className="text-gray-200 font-mono">{price(it.price_at_prediction)}</b>
              </span>
              <span>
                {it.plan_checked ? 'Terbeli' : 'Harga awal'}{' '}
                <b className="text-gray-200 font-mono">
                  {it.plan_checked ? (it.filled ? `${price(it.fill_price)} (${it.fill_date})` : 'tidak') : price(it.price_at_prediction)}
                </b>
              </span>
              <span>
                Tertinggi <b className="text-gray-200 font-mono">{price(it.max_price)}</b> · terendah{' '}
                <b className="text-gray-200 font-mono">{price(it.min_price)}</b>
              </span>
              <span>
                Sekarang <b className="text-gray-200 font-mono">{price(it.current_price)}</b>
                {it.excess_return_pct !== null && it.excess_return_pct !== undefined && ` · vs ${bench} ${fmtSigned(it.excess_return_pct)}`}
              </span>
            </div>
            {it.reasons?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {it.reasons.slice(0, 6).map((r, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-surfaceHover border border-borderMuted text-gray-300 text-[10px]">
                    {r}
                  </span>
                ))}
              </div>
            )}
            <button
              onClick={onChart}
              className="text-[11px] text-emerald-300 hover:text-emerald-200 inline-flex items-center gap-1"
            >
              Buka grafik & analisis <ArrowUpRight className="w-3 h-3" />
            </button>
          </td>
        </tr>
      )}
    </>
  );
};

const Kpi: React.FC<{ label: string; value: string; hint: string; tone?: string }> = ({ label, value, hint, tone }) => (
  <div className="p-3 rounded-xl bg-surfaceHover/40 border border-borderMuted">
    <div className="text-[10px] text-gray-400 uppercase font-semibold">{label}</div>
    <div className={`text-lg font-black mt-0.5 ${tone ?? 'text-white'}`}>{value}</div>
    <div className="text-[10px] text-gray-500 mt-0.5">{hint}</div>
  </div>
);
