import React, { useEffect, useRef } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  ColorType,
  LineStyle,
  LineWidth,
  SeriesMarker,
  Time,
} from 'lightweight-charts';
import { ChartData } from '../types/stock';

/** Plan levels drawn on the chart (subset of TradeLevels; integrator aligns ui/src/types later). */
export interface ChartLadderLevel {
  price: number;
  label: string;
}

export interface ChartLevels {
  entry_low: number;
  entry_high: number;
  recommended_entry?: number | null;
  stop_loss: number;
  target_tp1: number;
  target_tp2: number;
  ladder?: { supports: ChartLadderLevel[]; resistances: ChartLadderLevel[] } | null;
}

/** Abnormal daily bar (ARB/ARA/suspension…): time is 'YYYY-MM-DD'. */
export interface ChartMarker {
  time: string;
  kind: string;
  label: string;
}

interface Props {
  data: ChartData;
  height?: number;
  levels?: ChartLevels | null;
  /** Entry zone, cut loss, TP1/TP2 lines (default true). */
  showPlan?: boolean;
  /** Nearest support/resistance lines (default false). */
  showLadder?: boolean;
  markers?: ChartMarker[] | null;
}

const LADDER_MAX = 3;

const isPrice = (v: unknown): v is number => typeof v === 'number' && isFinite(v) && v > 0;

interface LineSpec {
  price: number;
  color: string;
  lineWidth: LineWidth;
  lineStyle: LineStyle;
  title: string;
}

const planLines = (lv: ChartLevels): LineSpec[] => {
  const out: LineSpec[] = [];
  const zone = { color: '#22C55E', lineWidth: 2 as LineWidth, lineStyle: LineStyle.Dashed, title: 'Zona beli' };
  if (isPrice(lv.entry_high)) out.push({ ...zone, price: lv.entry_high });
  if (isPrice(lv.entry_low)) out.push({ ...zone, price: lv.entry_low });
  if (isPrice(lv.recommended_entry)) {
    out.push({ price: lv.recommended_entry, color: 'rgba(134, 239, 172, 0.7)', lineWidth: 1, lineStyle: LineStyle.SparseDotted, title: 'Entry' });
  }
  if (isPrice(lv.stop_loss)) out.push({ price: lv.stop_loss, color: '#EF4444', lineWidth: 2, lineStyle: LineStyle.Solid, title: 'Cut loss' });
  if (isPrice(lv.target_tp1)) out.push({ price: lv.target_tp1, color: '#10B981', lineWidth: 1, lineStyle: LineStyle.Solid, title: 'TP1' });
  if (isPrice(lv.target_tp2)) out.push({ price: lv.target_tp2, color: '#14B8A6', lineWidth: 1, lineStyle: LineStyle.Solid, title: 'TP2' });
  return out;
};

const ladderLines = (lv: ChartLevels, skip: number[]): LineSpec[] => {
  const ladder = lv.ladder;
  if (!ladder) return [];
  // Don't stack a grey line on top of a plan line at the same price
  const clash = (p: number) => skip.some((s) => Math.abs(s - p) <= Math.abs(p) * 1e-4);
  const side = (items: ChartLadderLevel[] | undefined) =>
    (items || [])
      .filter((l) => l && isPrice(l.price) && !clash(l.price))
      .slice(0, LADDER_MAX)
      .map<LineSpec>((l) => ({
        price: l.price,
        color: 'rgba(148, 163, 184, 0.55)',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        title: l.label || '',
      }));
  return [...side(ladder.supports), ...side(ladder.resistances)];
};

const markerStyle = (kind: string): Pick<SeriesMarker<Time>, 'position' | 'color' | 'shape'> => {
  const k = (kind || '').toUpperCase();
  if (k.endsWith('_DOWN')) return { position: 'aboveBar', color: '#EF4444', shape: 'arrowDown' };
  if (k.endsWith('_UP')) return { position: 'belowBar', color: '#10B981', shape: 'arrowUp' };
  return { position: 'aboveBar', color: '#F59E0B', shape: 'circle' };
};

export const ChartView: React.FC<Props> = ({
  data,
  height = 480,
  levels = null,
  showPlan = true,
  showLadder = false,
  markers = null,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  // Ticker + interval last fitted: a refresh of the same view keeps the user's zoom/pan
  const fittedKeyRef = useRef<string | null>(null);
  // Price lines currently drawn, with the series they belong to (a recreated chart drops them all)
  const priceLinesRef = useRef<{ series: ISeriesApi<'Candlestick'> | null; lines: IPriceLine[] }>({ series: null, lines: [] });

  const isIntraday = !!data && !!data.candles && data.candles.length > 0 && typeof data.candles[0].time === 'number';

  // 1. Chart + series, created once per height (data is applied by the next effect)
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const container = chartContainerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: '#090D16' },
        textColor: '#94A3B8',
        fontSize: 11,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.5)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.5)' },
      },
      crosshair: {
        vertLine: { color: '#38BDF8', width: 1, style: 3 },
        horzLine: { color: '#38BDF8', width: 1, style: 3 },
      },
      rightPriceScale: {
        borderColor: '#1E293B',
      },
      timeScale: {
        borderColor: '#1E293B',
        secondsVisible: false,
      },
    });

    chartInstanceRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10B981',
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });
    candleSeriesRef.current = candleSeries;

    // Volume series
    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // overlay
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8, // volume sits in bottom 20%
        bottom: 0,
      },
    });
    volumeSeriesRef.current = volumeSeries;

    // Resize listener
    const handleResize = () => {
      if (chartInstanceRef.current && container) {
        chartInstanceRef.current.applyOptions({ width: container.clientWidth });
      }
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      fittedKeyRef.current = null;
    };
  }, [height]);

  // 2. Series data: refreshed in place; only a new ticker/interval re-fits the view
  useEffect(() => {
    const chart = chartInstanceRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries || !data || !data.candles || data.candles.length === 0) return;

    chart.applyOptions({ timeScale: { timeVisible: isIntraday } });
    candleSeries.setData(
      data.candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })) as any
    );
    volumeSeries.setData((data.volume || []).map((v) => ({ time: v.time, value: v.value, color: v.color })) as any);

    const key = `${data.ticker}|${data.interval ?? ''}|${isIntraday ? 'i' : 'd'}`;
    if (fittedKeyRef.current !== key) {
      chart.timeScale().fitContent();
      fittedKeyRef.current = key;
    }
  }, [data, height, isIntraday]);

  // 3. Plan + support/resistance price lines (redrawn on prop changes, chart stays)
  useEffect(() => {
    const series = candleSeriesRef.current;
    const drawn = priceLinesRef.current;
    if (drawn.series && drawn.series === series) {
      drawn.lines.forEach((l) => {
        try {
          series.removePriceLine(l);
        } catch {
          /* line already gone */
        }
      });
    }
    priceLinesRef.current = { series, lines: [] };
    if (!series || !levels) return;

    const plan = showPlan ? planLines(levels) : [];
    const ladder = showLadder ? ladderLines(levels, plan.map((p) => p.price)) : [];
    const lines: IPriceLine[] = [];
    [...plan, ...ladder].forEach((spec) => {
      try {
        lines.push(series.createPriceLine({ ...spec, axisLabelVisible: true }));
      } catch {
        /* skip a bad level, keep the chart */
      }
    });
    priceLinesRef.current = { series, lines };
  }, [height, levels, showPlan, showLadder]);

  // 4. Abnormal-day markers (daily chart only; intraday times are numbers)
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    if (isIntraday || !markers || markers.length === 0) {
      try {
        series.setMarkers([]);
      } catch {
        /* chart disposed */
      }
      return;
    }
    const times = new Set(data.candles.map((c) => String(c.time)));
    const list: SeriesMarker<Time>[] = markers
      .filter((m) => m && typeof m.time === 'string' && times.has(m.time.slice(0, 10)))
      .map((m) => ({ time: m.time.slice(0, 10) as Time, text: m.label, ...markerStyle(m.kind) }))
      .sort((a, b) => (String(a.time) < String(b.time) ? -1 : String(a.time) > String(b.time) ? 1 : 0));
    try {
      series.setMarkers(list);
    } catch {
      /* ignore bad marker data */
    }
  }, [data, height, markers, isIntraday]);

  const planVisible = !!levels && showPlan;
  const ladderVisible = !!levels && showLadder && !!levels.ladder &&
    ((levels.ladder.supports?.length ?? 0) + (levels.ladder.resistances?.length ?? 0) > 0);

  return (
    <div className="w-full relative rounded-xl overflow-hidden border border-borderMuted bg-[#090D16]">
      <div ref={chartContainerRef} className="w-full" style={{ height: `${height}px` }} />
      <div className="absolute top-2 left-3 flex items-center gap-2 pointer-events-none text-[11px] font-mono text-gray-400">
        <span className="text-white font-bold">{data.ticker}</span>
        {data.interval && (
          <span className="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400 font-bold text-[10px]">
            {data.interval.toUpperCase()}
          </span>
        )}
        <span className="text-emerald-400">● Candlestick</span>
        <span className="text-gray-500">● Volume</span>
        {planVisible && (
          <>
            <span className="text-green-400">┄ Zona beli</span>
            <span className="text-rose-400">— Cut loss</span>
            <span className="text-teal-400">— TP</span>
          </>
        )}
        {ladderVisible && <span className="text-slate-400">··· S/R</span>}
      </div>
      <div className="absolute top-2 right-3 flex items-center gap-2 pointer-events-none">
        <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-sans">
          Yahoo Finance (Delay ~15m)
        </span>
      </div>
      {isIntraday && (planVisible || ladderVisible) && (
        <div className="absolute bottom-7 left-3 pointer-events-none text-[10px] font-sans text-gray-500">
          Garis level dari grafik harian
        </div>
      )}
    </div>
  );
};
