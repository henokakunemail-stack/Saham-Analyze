import React, { useEffect, useRef, useState } from 'react';
import { RefreshCw, AlertTriangle, Loader2 } from 'lucide-react';
import { signalsApi } from '../api/signals';
import type { BacktestHorizon, BacktestResponse, BacktestResult, PlanSimStats, PlanSimSummary } from '../types/signals';

const HORIZONS: BacktestHorizon[] = [5, 10, 20];
const POLL_MS = 4000;

const num = (v: number, digits = 2) => v.toLocaleString('id-ID', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined || isNaN(v) ? '-' : `${v > 0 ? '+' : ''}${num(v)}%`;
const fmtR = (v: number | null | undefined) =>
  v === null || v === undefined || isNaN(v) ? '-' : `${v > 0 ? '+' : ''}${num(v)}R`;
const pct1 = (v: number | null | undefined) => (v === null || v === undefined ? '-' : `${num(v, 1)}%`);
const rTone = (v: number | null | undefined) =>
  v === null || v === undefined ? 'text-gray-400' : v >= 0.1 ? 'text-emerald-300' : v > -0.05 ? 'text-amber-300' : 'text-rose-300';

const GROUPS: { key: keyof PlanSimSummary; label: string; names?: Record<string, string> }[] = [
  { key: 'by_score_bucket', label: 'Skor' },
  { key: 'by_rr_bucket', label: 'Risiko : untung' },
  { key: 'by_atr_bucket', label: 'Gerak harian (ATR)' },
  {
    key: 'by_market_mode',
    label: 'Kondisi pasar',
    names: { NORMAL: 'Normal', CAUTIOUS: 'Waspada', BEARISH: 'Bearish', CRASH: 'Krisis' },
  },
  {
    key: 'by_pullback_state',
    label: 'Status pullback',
    names: {
      PULLBACK_IDEAL: 'Pullback sehat',
      PULLBACK_DEEP: 'Koreksi dalam',
      UPTREND_RUNNING: 'Uptrend berjalan',
      UPTREND_EXTENDED: 'Uptrend terlalu panas',
      TREND_BROKEN: 'Tren rusak',
      NO_UPTREND: 'Bukan uptrend',
    },
  },
  {
    key: 'by_verdict',
    label: 'Vonis',
    names: {
      STRONG_BULLISH: 'Strong bullish',
      MILD_BULLISH: 'Mild bullish',
      NEUTRAL: 'Netral',
      MILD_BEARISH: 'Mild bearish',
      STRONG_BEARISH: 'Strong bearish',
    },
  },
];

/** "Uji Historis" tab: how the app's trade plans would have played out over ~3 years. */
export const BacktestPanel: React.FC<{ market: 'IDX' | 'US' }> = ({ market }) => {
  const [horizon, setHorizon] = useState<BacktestHorizon>(10);
  const [resp, setResp] = useState<BacktestResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const reqId = useRef(0);

  const load = (refresh = false) => {
    const id = ++reqId.current;
    window.clearTimeout(timer.current);
    setFetchError(null);
    signalsApi
      .getBacktest(market, horizon, refresh)
      .then((r) => {
        if (id !== reqId.current) return;
        setResp(r);
        if (r.status === 'running') timer.current = window.setTimeout(() => load(false), POLL_MS);
      })
      .catch((e) => {
        if (id !== reqId.current) return;
        setFetchError(e instanceof Error ? e.message : String(e));
      });
  };

  useEffect(() => {
    setResp(null);
    load(false);
    return () => {
      reqId.current++;
      window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, horizon]);

  const running = resp?.status === 'running';
  const result: BacktestResult | null = !resp ? null : resp.status === 'ready' ? resp : resp.previous;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-gray-400 max-w-xl">
          Rencana entry, cut loss dan TP aplikasi diterapkan ke data masa lalu (tanpa melihat masa depan): apakah harga
          sempat turun ke zona beli, lalu mana yang tersentuh lebih dulu.
        </p>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-gray-500">Batas</span>
          <div className="flex rounded-lg border border-borderMuted overflow-hidden text-[11px]">
            {HORIZONS.map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`px-2.5 py-1 font-semibold ${
                  h === horizon ? 'bg-sky-500/20 text-sky-300' : 'bg-surfaceHover text-gray-400 hover:text-white'
                }`}
              >
                {h} hari
              </button>
            ))}
          </div>
          <button
            onClick={() => load(true)}
            disabled={running}
            className="p-1.5 rounded-lg bg-surfaceHover border border-borderMuted text-gray-300 hover:text-white disabled:opacity-50"
            title="Hitung ulang dari data terbaru"
            aria-label="Hitung ulang uji historis"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${running ? 'animate-spin text-sky-400' : ''}`} />
          </button>
        </div>
      </div>

      {(running || (!resp && !fetchError)) && (
        <div className="flex items-center gap-2 text-[11px] text-sky-300">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {resp
            ? `Menghitung di latar belakang (${Math.floor((resp.status === 'running' ? resp.elapsed_sec : 0) / 60)} menit)… pertama kali bisa 5–15 menit; halaman lain tetap bisa dipakai.`
            : 'Memeriksa hasil uji historis…'}
        </div>
      )}

      {(fetchError || resp?.status === 'error') && (
        <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Uji historis gagal: {fetchError ?? (resp?.status === 'error' ? resp.message : '')}
          </span>
          <button onClick={() => load(true)} className="px-2.5 py-1 rounded-lg bg-surfaceHover border border-borderMuted text-gray-200 font-semibold">
            Coba lagi
          </button>
        </div>
      )}

      {result && !result.ok && (
        <p className="text-xs text-gray-300">{result.message || 'Data historis belum cukup untuk uji historis.'}</p>
      )}

      {result?.ok && (
        <div className={`space-y-4 transition-opacity ${running ? 'opacity-60' : ''}`}>
          {result.plans?.overall ? (
            <PlanResult result={result} plans={result.plans} />
          ) : (
            <p className="text-xs text-gray-400">Hasil simulasi rencana belum ada — sedang dihitung ulang.</p>
          )}
          <ScoreDetails result={result} />
        </div>
      )}
    </div>
  );
};

const PlanResult: React.FC<{ result: BacktestResult; plans: PlanSimSummary }> = ({ result, plans }) => {
  const o = plans.overall;
  const [group, setGroup] = useState<keyof PlanSimSummary>('by_score_bucket');
  const g = GROUPS.find((x) => x.key === group)!;
  const rows = Object.entries((plans[group] as Record<string, PlanSimStats> | undefined) ?? {});
  const ins = plans.periods?.in_sample;
  const oos = plans.periods?.out_of_sample;

  return (
    <div className="space-y-4">
      {/* The answer in one sentence */}
      <p className="text-sm text-gray-200 leading-relaxed">
        Dari <b className="text-white">{o.decided.toLocaleString('id-ID')}</b> rencana ({result.tickers} saham,{' '}
        {result.period_start?.slice(0, 4)}–{result.period_end?.slice(0, 4)}):{' '}
        <b className="text-white">{pct1(o.fill_rate_pct)}</b> sempat terisi di zona beli. Dari yang terisi,{' '}
        <b className="text-white">{pct1(o.win_rate_pct)}</b> kena TP lebih dulu, rata-rata{' '}
        <b className={rTone(o.avg_r)}>{fmtR(o.avg_r)}</b> per transaksi.
        <span className="block text-xs text-gray-400 mt-1">
          Aturan uji: separuh dijual di TP1, sisanya mengincar TP2 dengan cut loss dinaikkan ke harga beli. Belum
          termasuk biaya transaksi (±0,4% beli+jual, kira-kira 0,1 R per transaksi).
        </span>
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Sempat terisi" value={pct1(o.fill_rate_pct)} hint="harga turun ke zona beli ≤ 5 hari" />
        <Stat label="Kena TP dulu" value={pct1(o.win_rate_pct)} hint={`${(o.hit_tp1 + o.hit_tp2).toLocaleString('id-ID')} TP · ${o.stopped_out.toLocaleString('id-ID')} cut loss · ${o.expired.toLocaleString('id-ID')} habis waktu`} />
        <Stat label="Rata-rata hasil" value={fmtR(o.avg_r)} tone={rTone(o.avg_r)} hint={`≈ ${fmtPct(o.avg_return_pct)} per transaksi`} />
        <Stat label="Profit factor" value={o.profit_factor === null ? '-' : num(o.profit_factor)} hint="untung total ÷ rugi total (> 1 = untung)" />
      </div>

      {ins && oos && (
        <p className="text-[11px] text-gray-400">
          Konsistensi: periode awal (s/d {ins.until}) <b className={rTone(ins.avg_r)}>{fmtR(ins.avg_r)}</b>, menang{' '}
          {pct1(ins.win_rate_pct)} · periode uji (sejak {oos.from}) <b className={rTone(oos.avg_r)}>{fmtR(oos.avg_r)}</b>, menang{' '}
          {pct1(oos.win_rate_pct)}. Aturan baru hanya dipakai bila juga bekerja di periode uji.
        </p>
      )}

      <details className="rounded-xl border border-borderMuted">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold text-gray-200">Rincian per kelompok</summary>
        <div className="px-3 pb-3 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {GROUPS.map((x) => (
              <button
                key={x.key}
                onClick={() => setGroup(x.key)}
                className={`px-2 py-0.5 rounded-md text-[11px] border ${
                  x.key === group ? 'border-sky-500/50 bg-sky-500/15 text-sky-200' : 'border-borderMuted text-gray-400 hover:text-white'
                }`}
              >
                {x.label}
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <p className="text-[11px] text-gray-500">Sampel per kelompok belum cukup.</p>
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-gray-500 text-left">
                  <th className="py-1 pr-2 font-semibold">{g.label}</th>
                  <th className="py-1 pr-2 font-semibold text-right">Rencana</th>
                  <th className="py-1 pr-2 font-semibold text-right">Terisi</th>
                  <th className="py-1 pr-2 font-semibold text-right">TP dulu</th>
                  <th className="py-1 font-semibold text-right">Rata-rata</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([name, s]) => (
                  <tr key={name} className="border-t border-borderMuted/60">
                    <td className="py-1 pr-2 text-gray-200">{g.names?.[name] ?? name}</td>
                    <td className="py-1 pr-2 text-right font-mono text-gray-400">{s.decided.toLocaleString('id-ID')}</td>
                    <td className="py-1 pr-2 text-right font-mono text-gray-300">{pct1(s.fill_rate_pct)}</td>
                    <td className="py-1 pr-2 text-right font-mono text-gray-300">{pct1(s.win_rate_pct)}</td>
                    <td className={`py-1 text-right font-mono ${rTone(s.avg_r)}`}>{fmtR(s.avg_r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </details>

      <p className="text-[10px] text-gray-500">
        Tanpa biaya transaksi. Sentimen berita & fundamental tidak ikut diuji (tidak ada riwayatnya). Hasil masa lalu bukan
        jaminan.
      </p>
    </div>
  );
};

/** The older question (does a higher score rank stocks better?), folded away. */
const ScoreDetails: React.FC<{ result: BacktestResult }> = ({ result }) => {
  const score = result.score;
  if (!score) return null;
  return (
    <details className="rounded-xl border border-borderMuted">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold text-gray-200">
        Apakah skor tinggi = return lebih baik? <span className="font-normal text-gray-400">· {result.verdict?.text}</span>
      </summary>
      <div className="px-3 pb-3 space-y-2 text-[11px]">
        <p className="text-gray-400">
          Korelasi peringkat skor vs return {result.horizon_days} hari (IC):{' '}
          <b className="text-white">{score.ic === null ? '-' : num(score.ic, 3)}</b> (t-stat{' '}
          {score.ic_t_stat === null || score.ic_t_stat === undefined ? '-' : num(score.ic_t_stat)}). Di bawah ±0,03 atau
          t-stat di bawah ±2 = belum terbukti.
        </p>
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 text-left">
              <th className="py-1 pr-2 font-semibold">Skor</th>
              <th className="py-1 pr-2 font-semibold text-right">Sampel</th>
              <th className="py-1 pr-2 font-semibold text-right">Return {result.horizon_days}H</th>
              <th className="py-1 pr-2 font-semibold text-right">vs Indeks</th>
              <th className="py-1 font-semibold text-right">Naik</th>
            </tr>
          </thead>
          <tbody>
            {score.buckets.map((b) => (
              <tr key={b.bucket} className="border-t border-borderMuted/60">
                <td className="py-1 pr-2 text-gray-200">{b.bucket}</td>
                <td className="py-1 pr-2 text-right font-mono text-gray-400">{b.count.toLocaleString('id-ID')}</td>
                <td className={`py-1 pr-2 text-right font-mono ${b.avg_fwd_ret_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                  {fmtPct(b.avg_fwd_ret_pct)}
                </td>
                <td className="py-1 pr-2 text-right font-mono text-gray-300">{fmtPct(b.avg_excess_ret_pct)}</td>
                <td className="py-1 text-right font-mono text-gray-300">{pct1(b.hit_rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
};

const Stat: React.FC<{ label: string; value: string; hint: string; tone?: string }> = ({ label, value, hint, tone }) => (
  <div className="p-3 rounded-xl bg-surfaceHover/40 border border-borderMuted">
    <div className="text-[10px] text-gray-400 uppercase font-semibold">{label}</div>
    <div className={`text-lg font-black mt-0.5 ${tone ?? 'text-white'}`}>{value}</div>
    <div className="text-[10px] text-gray-500 mt-0.5">{hint}</div>
  </div>
);
