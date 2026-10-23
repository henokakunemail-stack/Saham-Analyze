import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, LineStyle, Time } from 'lightweight-charts';
import { Activity, AlertTriangle, ChevronDown, Loader2, RefreshCw } from 'lucide-react';
import {
  marketApi,
  BreadthLabelCode,
  BreadthPoint,
  BreadthResponse,
  Market,
  SectorStrength,
  SectorsResponse,
} from '../api/market';

const OPEN_KEY = 'saham.marketBreadthPanel.open';
const SECTOR_POLL_MS = 8000;
const SECTOR_POLL_MAX = 15;

const LABEL_CLS: Record<BreadthLabelCode, string> = {
  STRONG: 'text-emerald-300',
  HEALTHY: 'text-emerald-200',
  NEUTRAL: 'text-amber-300',
  WEAK: 'text-orange-300',
  VERY_WEAK: 'text-rose-300',
  NO_DATA: 'text-gray-400',
};

const num = (v: number, digits = 1) =>
  v.toLocaleString('id-ID', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? '-' : `${num(v, digits)}%`);
const ret = (v: number | null | undefined) =>
  v === null || v === undefined ? '-' : `${v > 0 ? '+' : ''}${num(v, 1)}%`;
const retCls = (v: number | null | undefined) =>
  v === null || v === undefined ? 'text-gray-500' : v > 0 ? 'text-emerald-300' : v < 0 ? 'text-rose-300' : 'text-gray-300';

const fmtDay = (d?: string | null) => {
  if (!d) return '-';
  const date = new Date(`${d.slice(0, 10)}T00:00:00`);
  return isNaN(date.getTime())
    ? d
    : date.toLocaleDateString('id-ID', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};

const readOpen = (): boolean => {
  try {
    return localStorage.getItem(OPEN_KEY) !== '0';
  } catch {
    return true;
  }
};

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

interface Props {
  market: Market;
  /** Clicking a sector row; the selected sector again passes null (clear filter). */
  onSelectSector?: (sector: string | null) => void;
  selectedSector?: string | null;
}

/** "Kondisi Pasar & Sektor": breadth of the scan universe + sector strength (display only). */
export const MarketBreadthPanel: React.FC<Props> = ({ market, onSelectSector, selectedSector }) => {
  const [open, setOpen] = useState<boolean>(readOpen);
  const [breadth, setBreadth] = useState<BreadthResponse | null>(null);
  const [sectors, setSectors] = useState<SectorsResponse | null>(null);
  const [breadthError, setBreadthError] = useState<string | null>(null);
  const [sectorError, setSectorError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reqId = useRef(0);
  const pollTimer = useRef<number | undefined>(undefined);

  const loadSectors = (id: number, attempt: number) => {
    marketApi
      .getSectors(market)
      .then((s) => {
        if (id !== reqId.current) return;
        setSectors(s);
        setSectorError(null);
        // Sector labels are fetched from Yahoo in the background: reload until they are in
        if (s.refreshing && attempt < SECTOR_POLL_MAX) {
          pollTimer.current = window.setTimeout(() => loadSectors(id, attempt + 1), SECTOR_POLL_MS);
        }
      })
      .catch((e) => {
        if (id === reqId.current) setSectorError(errText(e));
      });
  };

  const load = () => {
    const id = ++reqId.current;
    window.clearTimeout(pollTimer.current);
    setLoading(true);
    setBreadthError(null);
    setSectorError(null);
    marketApi
      .getBreadth(market, 120)
      .then((b) => {
        if (id === reqId.current) setBreadth(b);
      })
      .catch((e) => {
        if (id === reqId.current) setBreadthError(errText(e));
      })
      .finally(() => {
        if (id === reqId.current) setLoading(false);
      });
    loadSectors(id, 0);
  };

  useEffect(() => {
    setBreadth(null);
    setSectors(null);
    load();
    return () => {
      reqId.current++;
      window.clearTimeout(pollTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market]);

  const toggle = () => {
    setOpen((o) => {
      try {
        localStorage.setItem(OPEN_KEY, o ? '0' : '1');
      } catch {
        /* per-viewer convenience only */
      }
      return !o;
    });
  };

  const code: BreadthLabelCode = breadth?.label_code ?? 'NO_DATA';

  return (
    <div className="rounded-xl bg-surface border border-borderMuted">
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <button
          onClick={toggle}
          className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-400 hover:text-cyan-300"
          aria-expanded={open}
        >
          <ChevronDown className={`w-4 h-4 transition-transform ${open ? '' : '-rotate-90'}`} />
          <Activity className="w-4 h-4" />
          <span>Kondisi Pasar &amp; Sektor</span>
        </button>
        <div className="flex items-center gap-2 min-w-0">
          {breadth?.latest && (
            <span className={`text-[11px] font-semibold truncate ${LABEL_CLS[code]}`}>Breadth: {breadth.label}</span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="p-1.5 rounded-lg bg-surfaceHover border border-borderMuted text-gray-300 hover:text-white disabled:opacity-50"
            title="Muat ulang kondisi pasar"
            aria-label="Muat ulang kondisi pasar"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-sky-400' : ''}`} />
          </button>
        </div>
      </div>

      {open && (
        <div className="px-4 pb-4 space-y-4">
          <BreadthSection breadth={breadth} error={breadthError} loading={loading && !breadth} onRetry={load} />
          <SectorSection
            data={sectors}
            error={sectorError}
            loading={!sectors && !sectorError}
            onRetry={load}
            onSelectSector={onSelectSector}
            selectedSector={selectedSector}
          />
        </div>
      )}
    </div>
  );
};

const ErrorRow: React.FC<{ text: string; onRetry: () => void }> = ({ text, onRetry }) => (
  <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
    <span className="flex items-center gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      {text}
    </span>
    <button onClick={onRetry} className="px-2.5 py-1 rounded-lg bg-surfaceHover border border-borderMuted text-gray-200 font-semibold">
      Coba lagi
    </button>
  </div>
);

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <div className="p-2 rounded-lg bg-[#090D16] border border-borderMuted" title={hint}>
    <div className="text-[10px] text-gray-400">{label}</div>
    <div className="font-mono font-bold text-white text-xs">{value}</div>
  </div>
);

const BreadthSection: React.FC<{
  breadth: BreadthResponse | null;
  error: string | null;
  loading: boolean;
  onRetry: () => void;
}> = ({ breadth, error, loading, onRetry }) => {
  if (error) return <ErrorRow text={`Gagal memuat breadth pasar: ${error}`} onRetry={onRetry} />;
  if (loading || !breadth) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-sky-300">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Menghitung breadth pasar… (pertama kali beberapa detik)
      </div>
    );
  }
  const l = breadth.latest;
  if (!l || breadth.history.length === 0) {
    return (
      <p className="text-xs text-gray-400">
        Belum ada data breadth. Jalankan scan agar data harga harian tersedia, lalu muat ulang panel ini.
      </p>
    );
  }
  const code = breadth.label_code;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)] gap-4">
      <div className="space-y-3">
        <div>
          <div className="text-[11px] text-gray-400">Saham di atas EMA50</div>
          <div className={`text-4xl font-black font-mono ${LABEL_CLS[code]}`}>{pct(l.pct_above_ema50)}</div>
          <div className={`text-xs font-semibold ${LABEL_CLS[code]}`}>{breadth.label}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            {fmtDay(l.date)} · {l.n} saham
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Stat
            label="Naik / turun"
            value={
              <>
                <span className="text-emerald-300">{l.advancers}</span> / <span className="text-rose-300">{l.decliners}</span>
                {l.unchanged > 0 && <span className="text-gray-500"> · {l.unchanged} tetap</span>}
              </>
            }
            hint="Jumlah saham yang ditutup naik / turun dibanding hari sebelumnya"
          />
          <Stat
            label="High / low 20 hari"
            value={
              <>
                <span className="text-emerald-300">{l.new_high_20d}</span> / <span className="text-rose-300">{l.new_low_20d}</span>
              </>
            }
            hint="Saham yang ditutup di harga tertinggi / terendah 20 hari bursa terakhir"
          />
          <Stat label="Di atas EMA20 · EMA200" value={`${pct(l.pct_above_ema20)} · ${pct(l.pct_above_ema200)}`} />
          <Stat label="CMF positif" value={pct(l.pct_cmf_pos)} hint="Saham dengan Chaikin Money Flow 20 hari > 0 (uang cenderung masuk)" />
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
          <span>% saham di atas EMA50 — {breadth.history.length} hari bursa</span>
          <span>garis putus: 30% (lemah) · 50%</span>
        </div>
        <BreadthChart history={breadth.history} />
        <p className="text-[10px] text-gray-500 mt-1">
          Hanya informasi kondisi pasar — belum memengaruhi skor. Di bawah 30% berarti mayoritas saham sedang dalam tren
          turun; peluang beli lebih berisiko.
        </p>
      </div>
    </div>
  );
};

const BreadthChart: React.FC<{ history: BreadthPoint[]; height?: number }> = ({ history, height = 150 }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = ref.current;
    const points = history.filter((p) => p.pct_above_ema50 !== null);
    if (!container || points.length === 0) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#090D16' },
        textColor: '#94A3B8',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.4)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.4)' },
      },
      crosshair: {
        vertLine: { color: '#38BDF8', width: 1, style: LineStyle.Dotted },
        horzLine: { color: '#38BDF8', width: 1, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: '#1E293B' },
      timeScale: { borderColor: '#1E293B' },
      handleScroll: false,
      handleScale: false,
    });
    chartRef.current = chart;

    const series = chart.addLineSeries({
      color: '#38BDF8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: { type: 'custom', minMove: 0.1, formatter: (v: number) => `${Math.round(v)}%` },
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    });
    series.setData(points.map((p) => ({ time: p.date as Time, value: p.pct_above_ema50 as number })));
    series.createPriceLine({
      price: 30,
      color: 'rgba(251, 113, 133, 0.7)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
      title: '30%',
    });
    series.createPriceLine({
      price: 50,
      color: 'rgba(148, 163, 184, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
      title: '50%',
    });
    chart.timeScale().fitContent();

    const resize = new ResizeObserver(() => {
      if (chartRef.current) chartRef.current.applyOptions({ width: container.clientWidth });
    });
    resize.observe(container);

    return () => {
      resize.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [history, height]);

  return (
    <div className="w-full rounded-lg overflow-hidden border border-borderMuted bg-[#090D16]">
      <div ref={ref} className="w-full" style={{ height: `${height}px` }} />
    </div>
  );
};

const SectorSection: React.FC<{
  data: SectorsResponse | null;
  error: string | null;
  loading: boolean;
  onRetry: () => void;
  onSelectSector?: (sector: string | null) => void;
  selectedSector?: string | null;
}> = ({ data, error, loading, onRetry, onSelectSector, selectedSector }) => {
  if (error) return <ErrorRow text={`Gagal memuat kekuatan sektor: ${error}`} onRetry={onRetry} />;
  if (loading || !data) {
    return (
      <div className="flex items-center gap-2 text-[11px] text-sky-300">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Memuat kekuatan sektor…
      </div>
    );
  }
  if (data.sectors.length === 0) {
    return <p className="text-xs text-gray-400">Belum ada hasil scan untuk menghitung kekuatan sektor.</p>;
  }
  const clickable = !!onSelectSector;
  const pick = (s: SectorStrength) => {
    if (!onSelectSector) return;
    onSelectSector(selectedSector === s.sector ? null : s.sector);
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-gray-200">Kekuatan sektor</div>
        <div className="text-[10px] text-gray-500">
          Urutan: median return 3 bulan, lalu % saham di atas EMA50
          {clickable && ' · klik sektor untuk menyaring tabel'}
        </div>
      </div>
      {data.refreshing && data.missing > 0 && (
        <div className="flex items-center gap-2 text-[11px] text-sky-300">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Mengambil data sektor {data.missing} saham dari Yahoo… sementara masuk "Lainnya".
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-borderMuted">
        <table className="w-full text-[11px]">
          <thead className="bg-[#090D16] text-gray-400">
            <tr>
              <th className="px-2 py-1.5 text-left font-semibold">#</th>
              <th className="px-2 py-1.5 text-left font-semibold">Sektor</th>
              <th className="px-2 py-1.5 text-right font-semibold">Jumlah saham</th>
              <th className="px-2 py-1.5 text-right font-semibold">Return 1B</th>
              <th className="px-2 py-1.5 text-right font-semibold">Return 3B</th>
              <th className="px-2 py-1.5 text-right font-semibold">% di atas EMA50</th>
              <th className="px-2 py-1.5 text-right font-semibold">LAYAK</th>
            </tr>
          </thead>
          <tbody>
            {data.sectors.map((s) => {
              const selected = selectedSector === s.sector;
              return (
                <tr
                  key={s.sector}
                  onClick={() => pick(s)}
                  {...(clickable
                    ? {
                        role: 'button',
                        tabIndex: 0,
                        'aria-pressed': selected,
                        onKeyDown: (e: React.KeyboardEvent) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            pick(s);
                          }
                        },
                      }
                    : {})}
                  title={s.tickers.slice(0, 12).join(', ') + (s.tickers.length > 12 ? ', …' : '')}
                  className={`border-t border-borderMuted ${clickable ? 'cursor-pointer hover:bg-surfaceHover focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60' : ''} ${
                    selected ? 'bg-sky-500/15' : ''
                  }`}
                >
                  <td className="px-2 py-1.5 font-mono text-gray-400">{s.rank ?? '-'}</td>
                  <td className={`px-2 py-1.5 font-semibold ${selected ? 'text-sky-300' : 'text-gray-100'}`}>{s.sector}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-gray-300">{s.count}</td>
                  <td className={`px-2 py-1.5 text-right font-mono ${retCls(s.median_ret_1m)}`}>{ret(s.median_ret_1m)}</td>
                  <td className={`px-2 py-1.5 text-right font-mono ${retCls(s.median_ret_3m)}`}>{ret(s.median_ret_3m)}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-gray-200">{pct(s.pct_above_ema50)}</td>
                  <td className={`px-2 py-1.5 text-right font-mono ${s.layak > 0 ? 'text-emerald-300' : 'text-gray-500'}`}>
                    {s.layak}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-gray-500">
        Return = median per sektor (1B ≈ 21 hari bursa, 3B ≈ 63 hari bursa). Sumber sektor: Yahoo Finance, dipetakan ke
        klasifikasi IDX-IC.
      </p>
    </div>
  );
};
