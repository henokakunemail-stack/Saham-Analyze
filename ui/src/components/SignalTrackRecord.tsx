import React, { useEffect, useState } from 'react';
import { History, Loader2 } from 'lucide-react';
import { signalsApi } from '../api/signals';
import type { ReliabilityResponse, TrackRecordStat } from '../types/signals';

const MODE_LABELS: Record<string, string> = {
  NORMAL: 'Pasar Normal',
  CAUTIOUS: 'Pasar Waspada',
  BEARISH: 'Pasar Bearish',
  CRASH: 'Pasar Krisis',
};

const BUCKETS: Array<[number, number, string]> = [
  [0, 35, '0-34'],
  [35, 45, '35-44'],
  [45, 55, '45-54'],
  [55, 65, '55-64'],
  [65, 75, '65-74'],
  [75, 101, '75-100'],
];

const pct = (v?: number | null, signed = false) =>
  v === undefined || v === null
    ? '-'
    : `${signed && v > 0 ? '+' : ''}${v.toLocaleString('id-ID', { maximumFractionDigits: 1 })}%`;

interface Props {
  market: 'IDX' | 'US';
  score?: number;
  pullbackState?: string;
  pullbackLabel?: string;
  marketMode?: string;
}

/** How often signals like this one were right in the past (walk-forward backtest, no look-ahead). */
export const SignalTrackRecord: React.FC<Props> = ({ market, score, pullbackState, pullbackLabel, marketMode }) => {
  const [data, setData] = useState<ReliabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let polls = 0;
    const load = async () => {
      const res = await signalsApi.getReliability(market, 10);
      if (cancelled) return;
      setData(res);
      setLoading(false);
      // First computation runs in the background (a few minutes): poll gently until it lands
      if (res && !res.available && res.status === 'running' && polls++ < 60) {
        timer = window.setTimeout(load, 10000);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [market]);

  const indexName = market === 'IDX' ? 'IHSG' : 'S&P 500';

  if (loading) return null;
  if (!data) return null;

  if (!data.available) {
    return (
      <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted text-[11px] text-gray-400 flex items-center gap-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-sky-400 shrink-0" />
        <span>
          Menghitung rekam jejak historis sinyal (uji 3 tahun, berjalan di latar belakang, ±3–8 menit). Bagian ini akan
          terisi otomatis.
        </span>
      </div>
    );
  }

  const bucket = score === undefined ? undefined : BUCKETS.find(([lo, hi]) => score >= lo && score < hi)?.[2];
  const bucketStat = data.by_score_bucket.find((b) => b.bucket === bucket);
  const rows: Array<{ label: string; stat?: TrackRecordStat }> = [
    {
      label: `Status: ${pullbackLabel ?? pullbackState ?? '-'}`,
      stat: pullbackState ? data.by_pullback_state[pullbackState] : undefined,
    },
    {
      label: `Skor ${bucket ?? '-'}`,
      stat: bucketStat
        ? { count: bucketStat.count, hit_rate_pct: bucketStat.hit_rate_pct, avg_excess_ret_pct: bucketStat.avg_excess_ret_pct }
        : undefined,
    },
    {
      label: MODE_LABELS[marketMode ?? ''] ?? `Mode ${marketMode ?? '-'}`,
      stat: marketMode ? data.by_market_mode[marketMode] : undefined,
    },
  ];
  const baseline = data.baseline_hit_rate_pct;

  return (
    <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-sky-400">
          <History className="w-4 h-4" />
          <span>Rekam Jejak Sinyal Serupa ({data.horizon_days} hari ke depan)</span>
        </div>
        <span className="text-[10px] text-gray-500 font-mono">
          Uji {data.period_start ?? '?'} s/d {data.period_end ?? '?'} · {data.tickers ?? '?'} saham
          {data.status === 'running' ? ' · sedang diperbarui' : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {rows.map((r) => (
          <div key={r.label} className="p-2.5 rounded-lg bg-surface border border-borderMuted text-[11px]">
            <div className="text-gray-400 truncate" title={r.label}>
              {r.label}
            </div>
            {r.stat ? (
              <>
                <div className="mt-1 font-mono text-white">
                  <span
                    className={`font-bold ${
                      baseline !== undefined && r.stat.hit_rate_pct > baseline + 2
                        ? 'text-emerald-400'
                        : baseline !== undefined && r.stat.hit_rate_pct < baseline - 2
                        ? 'text-rose-400'
                        : 'text-gray-200'
                    }`}
                  >
                    {pct(r.stat.hit_rate_pct)}
                  </span>{' '}
                  naik
                  <span className="text-gray-500"> dari {r.stat.count.toLocaleString('id-ID')} kasus</span>
                </div>
                <div className="text-gray-400 mt-0.5">
                  Rata-rata vs {indexName}: <span className="font-mono text-gray-200">{pct(r.stat.avg_excess_ret_pct, true)}</span>
                </div>
                {r.stat.count < 60 && <div className="text-amber-400/80 mt-0.5">Sampel kecil — kurang bisa diandalkan</div>}
              </>
            ) : (
              <div className="mt-1 text-gray-500">Belum cukup kasus historis</div>
            )}
          </div>
        ))}
      </div>

      <p className="text-[10px] text-gray-500 leading-relaxed">
        Pembanding: rata-rata semua saham naik {pct(baseline)} dalam {data.horizon_days} hari pada periode yang sama.
        Angka ini catatan masa lalu (tanpa berita &amp; fundamental), bukan jaminan hasil ke depan.
      </p>
    </div>
  );
};
