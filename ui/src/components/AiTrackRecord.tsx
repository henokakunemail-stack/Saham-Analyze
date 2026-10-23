import React, { useCallback, useEffect, useState } from 'react';
import { Bot, RefreshCw } from 'lucide-react';
import { requestJson, TIMEOUT } from '../api/feedback';
import { API_BASE } from '../api/base';
import { fmtNum, fmtPct, fmtPrice } from './help/format';
import { clickableProps, FOCUS_RING } from '../lib/a11y';

interface Outcome {
  days: number;
  final: boolean;
  return_pct?: number;
  excess_pct?: number;
  first_hit?: 'TP1' | 'SL' | null;
}

interface Group {
  verdict: string;
  count: number;
  evaluated: number;
  avg_return_pct: number | null;
  avg_excess_pct: number | null;
  win_rate_pct: number | null;
  tp1_first_pct: number | null;
}

interface Recent {
  id: number;
  trade_date: string;
  ticker: string;
  model?: string;
  ai_verdict: string;
  confidence?: number | null;
  engine_verdict?: string | null;
  price: number;
  outcome: Outcome;
}

interface Summary {
  horizon_days: number;
  total: number;
  evaluated: number;
  enough_data: boolean;
  min_sample: number;
  by_ai_verdict: Group[];
  by_engine_verdict: Group[];
  recent: Recent[];
}

const AI_LABEL: Record<string, string> = {
  STRONG_BUY: 'Strong Buy',
  SPECULATIVE_BUY: 'Speculative Buy',
  WAIT_AND_SEE: 'Wait & See',
  AVOID: 'Avoid',
};

const pct = (v?: number | null) => fmtPct(v);
const tone = (v?: number | null) => (v === undefined || v === null ? 'text-gray-400' : v > 0 ? 'text-emerald-300' : v < 0 ? 'text-rose-300' : 'text-gray-300');

const GroupTable: React.FC<{ title: string; groups: Group[]; labels?: Record<string, string> }> = ({ title, groups, labels }) => (
  <div className="space-y-1">
    <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">{title}</div>
    <table className="w-full text-[11px]">
      <thead>
        <tr className="text-gray-500 text-left">
          <th className="py-1 pr-2 font-semibold">Vonis</th>
          <th className="py-1 pr-2 font-semibold text-right">Dinilai</th>
          <th className="py-1 pr-2 font-semibold text-right">Rata-rata</th>
          <th className="py-1 pr-2 font-semibold text-right">vs Indeks</th>
          <th className="py-1 pr-2 font-semibold text-right">Naik</th>
          <th className="py-1 font-semibold text-right">TP1 dulu</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g) => (
          <tr key={g.verdict} className="border-t border-borderMuted/60">
            <td className="py-1 pr-2 text-gray-200">{labels?.[g.verdict] ?? g.verdict}</td>
            <td className="py-1 pr-2 text-right font-mono text-gray-400">{g.evaluated}/{g.count}</td>
            <td className={`py-1 pr-2 text-right font-mono ${tone(g.avg_return_pct)}`}>{pct(g.avg_return_pct)}</td>
            <td className={`py-1 pr-2 text-right font-mono ${tone(g.avg_excess_pct)}`}>{pct(g.avg_excess_pct)}</td>
            <td className="py-1 pr-2 text-right font-mono text-gray-300">{g.win_rate_pct === null ? '-' : `${fmtNum(g.win_rate_pct, 1)}%`}</td>
            <td className="py-1 text-right font-mono text-gray-300">{g.tp1_first_pct === null ? '-' : `${fmtNum(g.tp1_first_pct, 1)}%`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

/** Did the AI's verdicts work out? Outcome after N trading days, next to the engine's verdicts. */
export const AiTrackRecord: React.FC<{ market: 'IDX' | 'US'; onSelectTicker?: (t: string, m?: 'IDX' | 'US') => void }> = ({
  market,
  onSelectTicker,
}) => {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await requestJson<Summary>(`${API_BASE}/ai/validations?market=${market}`, { timeout: TIMEOUT.slow }));
    } catch {
      setData(null);
    }
    setLoading(false);
  }, [market]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-[11px] text-gray-400 leading-relaxed max-w-xl flex gap-1.5">
          <Bot className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
          Setiap "Validasi AI" dicatat. Setelah {data?.horizon_days ?? 10} hari bursa hasilnya diukur, lalu vonis AI
          dibandingkan dengan vonis engine pada saham &amp; hari yang sama.
        </p>
        <button
          type="button"
          onClick={load}
          className="text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1"
          aria-label="Muat ulang rekam jejak AI"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Muat ulang
        </button>
      </div>

      {!data ? (
        <p className="text-[11px] text-gray-500">{loading ? 'Memuat…' : 'Rekam jejak belum bisa dimuat.'}</p>
      ) : data.total === 0 ? (
        <p className="text-[11px] text-gray-500">Belum ada validasi AI yang tercatat. Jalankan "Validasi AI" di detail saham.</p>
      ) : (
        <>
          <p className={`text-[11px] font-semibold ${data.enough_data ? 'text-emerald-300' : 'text-amber-300'}`}>
            {data.evaluated} dari {data.total} validasi sudah dinilai.
            {!data.enough_data &&
              ` Sampel belum cukup (minimal ${data.min_sample}) — angka di bawah belum bisa dijadikan pegangan.`}
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GroupTable title="Menurut vonis AI" groups={data.by_ai_verdict} labels={AI_LABEL} />
            <GroupTable title="Menurut vonis engine (saham yang sama)" groups={data.by_engine_verdict} />
          </div>
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">Validasi terbaru</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-gray-500 text-left">
                    <th className="py-1 pr-2 font-semibold">Tanggal</th>
                    <th className="py-1 pr-2 font-semibold">Saham</th>
                    <th className="py-1 pr-2 font-semibold">AI</th>
                    <th className="py-1 pr-2 font-semibold">Engine</th>
                    <th className="py-1 pr-2 font-semibold text-right">Harga</th>
                    <th className="py-1 font-semibold text-right">Hasil</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((r) => (
                    <tr
                      key={r.id}
                      {...clickableProps(() => onSelectTicker?.(r.ticker, market))}
                      aria-label={`Buka detail ${r.ticker.replace('.JK', '')}`}
                      className={`${FOCUS_RING} border-t border-borderMuted/60 cursor-pointer hover:bg-white/5`}
                    >
                      <td className="py-1 pr-2 font-mono text-gray-400">{r.trade_date}</td>
                      <td className="py-1 pr-2 font-mono font-bold text-white">{r.ticker.replace('.JK', '')}</td>
                      <td className="py-1 pr-2 text-purple-200">
                        {AI_LABEL[r.ai_verdict] ?? r.ai_verdict}
                        {r.confidence ? <span className="text-gray-500"> · {r.confidence}%</span> : null}
                      </td>
                      <td className="py-1 pr-2 text-gray-300">{r.engine_verdict ?? '-'}</td>
                      <td className="py-1 pr-2 text-right font-mono text-gray-300">{fmtPrice(r.price)}</td>
                      <td className={`py-1 text-right font-mono ${tone(r.outcome?.return_pct)}`}>
                        {r.outcome?.days ? (
                          <>
                            {pct(r.outcome.return_pct)}
                            <span className="text-gray-500">
                              {r.outcome.final ? '' : ` (hari ${r.outcome.days}/${data.horizon_days})`}
                              {r.outcome.first_hit ? ` · ${r.outcome.first_hit === 'TP1' ? 'TP1' : 'CL'} dulu` : ''}
                            </span>
                          </>
                        ) : (
                          <span className="text-gray-500">menunggu</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
