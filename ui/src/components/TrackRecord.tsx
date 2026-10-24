import React, { useEffect, useState } from 'react';
import { Scale } from 'lucide-react';
import { api } from '../api/client';
import type { TrackRecord, TrackVerdictCode } from '../types/stock';
import { InfoTip } from './help/InfoTip';

const TONE: Record<TrackVerdictCode, { text: string; chip: string }> = {
  BELUM_CUKUP: { text: 'text-gray-300', chip: 'bg-slate-500/15 text-slate-200 border-slate-500/30' },
  MERUGI: { text: 'text-rose-300', chip: 'bg-rose-500/15 text-rose-200 border-rose-500/40' },
  DI_BAWAH_HARAPAN: { text: 'text-amber-300', chip: 'bg-amber-500/15 text-amber-200 border-amber-500/40' },
  TERBUKTI_POSITIF: { text: 'text-emerald-300', chip: 'bg-emerald-500/15 text-emerald-200 border-emerald-500/40' },
  SESUAI_BELUM_PASTI: { text: 'text-sky-300', chip: 'bg-sky-500/15 text-sky-200 border-sky-500/40' },
};

export const fmtR = (v: number | null | undefined) =>
  v === null || v === undefined || isNaN(v) ? '-' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} R`;

const fmtDay = (d?: string | null) =>
  d ? new Date(`${d}T00:00:00`).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';

/** Loads the live track record once per market (null while loading or on failure). */
export const useTrackRecord = (market: 'IDX' | 'US') => {
  const [data, setData] = useState<TrackRecord | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    api.getTrackRecord(market).then((r) => alive && setData(r));
    return () => {
      alive = false;
    };
  }, [market]);
  return data;
};

/** Range of the scale in R: wide enough for the interval, the yardstick and zero. */
const scaleOf = (d: TrackRecord) => {
  const pts = [0, d.verdict.expected_r, ...(d.verdict.ci90 ?? []), d.verdict.mean_r ?? 0];
  const lo = Math.min(-1, ...pts);
  const hi = Math.max(1, ...pts);
  return { lo, hi, pos: (v: number) => `${((v - lo) / (hi - lo)) * 100}%` };
};

/** Mean ± 90 % interval of the live results next to zero and the backtest yardstick. */
const RangeBar: React.FC<{ d: TrackRecord }> = ({ d }) => {
  const { pos } = scaleOf(d);
  const v = d.verdict;
  const tone = TONE[v.code];
  return (
    <div className="pt-5 pb-6" aria-hidden="true">
      <div className="relative h-2 rounded-full bg-surfaceHover border border-borderMuted">
        {v.ci90 && (
          <div
            className="absolute top-0 h-full rounded-full bg-current opacity-40"
            style={{ left: pos(v.ci90[0]), width: `calc(${pos(v.ci90[1])} - ${pos(v.ci90[0])})` }}
          />
        )}
        <Tick at={pos(0)} label="0" cls="bg-gray-400" />
        <Tick at={pos(v.expected_r)} label={`uji ${fmtR(v.expected_r)}`} cls="bg-violet-400" below />
        {v.mean_r !== null && (
          <div
            className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-surface ${tone.text} bg-current`}
            style={{ left: pos(v.mean_r) }}
          />
        )}
      </div>
    </div>
  );
};

const Tick: React.FC<{ at: string; label: string; cls: string; below?: boolean }> = ({ at, label, cls, below }) => (
  <div className="absolute top-0 h-full" style={{ left: at }}>
    <div className={`absolute -top-1 -translate-x-1/2 w-0.5 h-4 ${cls}`} />
    <div className={`absolute -translate-x-1/2 whitespace-nowrap text-[10px] text-gray-400 ${below ? 'top-4' : '-top-5'}`}>{label}</div>
  </div>
);

/** Histori Prediksi: are the current rules doing in real life what the backtest led us to expect? */
export const TrackRecordPanel: React.FC<{ market: 'IDX' | 'US' }> = ({ market }) => {
  const d = useTrackRecord(market);
  if (!d) return null;
  const v = d.verdict;
  const tone = TONE[v.code];
  const progress = Math.min(100, (v.n / v.min_trades) * 100);

  return (
    <section aria-label="Rekam jejak nyata" className="p-4 rounded-xl border border-borderMuted bg-surfaceHover/30 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Scale className="w-4 h-4 text-violet-300" />
          <h2 className="text-sm font-bold text-white">Nyata vs uji historis</h2>
          <InfoTip label="Cara membaca rekam jejak nyata">
            <div className="text-xs leading-relaxed space-y-1.5">
              <p>
                Semua saham berstatus LAYAK di rencana penutupan sejak aturan sekarang berlaku ({d.rules_version}) dinilai
                bersama, dengan cara yang sama seperti uji historis: beli limit berlaku 5 hari bursa, jual separuh di TP1, sisa
                dijaga di harga beli, paling lama 10 hari bursa.
              </p>
              <p>
                R = besar risiko per transaksi (harga beli − cut loss). Hasil per transaksi sangat beragam, jadi kesimpulan baru
                diambil setelah {v.min_trades} transaksi selesai, memakai rentang 90 % dari rata-ratanya. Aturan penilaian ini
                ditulis sebelum ada data nyata dan tidak diubah.
              </p>
              <p>Hasil sebelum biaya transaksi (±0,1 R per transaksi).</p>
            </div>
          </InfoTip>
        </div>
        <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${tone.chip}`}>{v.label}</span>
      </div>

      <p className="text-xs text-gray-200 leading-relaxed">{v.text}</p>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_1.4fr] gap-4 items-center">
        <div className="space-y-1">
          <div className="flex justify-between text-[11px] text-gray-400">
            <span>Transaksi selesai</span>
            <span className="font-mono text-gray-200">
              {v.n} / {v.min_trades}
            </span>
          </div>
          <div
            className="h-1.5 rounded-full bg-surfaceHover overflow-hidden"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={v.min_trades}
            aria-valuenow={v.n}
            aria-label="Transaksi selesai menuju jumlah minimal"
          >
            <div className="h-full bg-violet-400/70" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-[10px] text-gray-500">
            {d.predictions} rencana sejak {fmtDay(d.since)} · {d.filled} terbeli · {d.in_progress} berjalan · {d.waiting}{' '}
            menunggu · {d.not_filled} tidak sempat dibeli
            {d.win_pct !== null && ` · ${d.win_pct.toLocaleString('id-ID')}% untung`}
          </p>
        </div>
        {v.n > 0 ? (
          <div>
            <div className={tone.text}>
              <RangeBar d={d} />
            </div>
            <p className="text-[10px] text-gray-500">
              Titik = rata-rata nyata {fmtR(v.mean_r)} · pita = rentang 90 % (makin banyak transaksi, makin sempit) · garis
              ungu = patokan uji historis
            </p>
          </div>
        ) : (
          <p className="text-[11px] text-gray-400">
            Belum ada transaksi yang selesai. Patokan dari uji historis: rata-rata {fmtR(v.expected_r)} per transaksi.
          </p>
        )}
      </div>

      {d.older_rules_predictions > 0 && (
        <p className="text-[10px] text-gray-500">
          {d.older_rules_predictions} prediksi lama dibuat dengan aturan sebelumnya — tidak dihitung di sini, tetap bisa dilihat
          per tanggal di bawah.
        </p>
      )}
    </section>
  );
};

/** One line for Analisa Penutupan. */
export const TrackRecordLine: React.FC<{ market: 'IDX' | 'US' }> = ({ market }) => {
  const d = useTrackRecord(market);
  if (!d) return null;
  const v = d.verdict;
  return (
    <p className="text-[11px] text-gray-400">
      Rekam jejak nyata aturan ini: <span className={TONE[v.code].text}>{v.label}</span> ({v.n} dari minimal {v.min_trades}{' '}
      transaksi selesai{v.mean_r !== null && `, rata-rata ${fmtR(v.mean_r)}`}) — rinciannya di Histori Prediksi.
    </p>
  );
};
