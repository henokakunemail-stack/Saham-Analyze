import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ColorType } from 'lightweight-charts';
import { CmfPoint } from '../types/stock';
import { InfoTip } from './help/InfoTip';
import { fmtSigned } from './help/format';

interface Props {
  cmfData: CmfPoint[];
  height?: number;
}

export const CmfOscillatorChart: React.FC<Props> = ({ cmfData, height = 150 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || !cmfData || cmfData.length === 0) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = containerRef.current;
    const chart = createChart(container, {
      width: container.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: '#090D16' },
        textColor: '#64748B',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.3)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.3)' },
      },
      rightPriceScale: {
        borderColor: '#1E293B',
      },
      timeScale: {
        borderColor: '#1E293B',
        timeVisible: false,
      },
    });

    chartRef.current = chart;

    // Area series for Chaikin Money Flow
    const areaSeries = chart.addBaselineSeries({
      baseValue: { type: 'price', price: 0 },
      topLineColor: '#10B981',
      topFillColor1: 'rgba(16, 185, 129, 0.28)',
      topFillColor2: 'rgba(16, 185, 129, 0.02)',
      bottomLineColor: '#EF4444',
      bottomFillColor1: 'rgba(239, 68, 68, 0.02)',
      bottomFillColor2: 'rgba(239, 68, 68, 0.28)',
      lineWidth: 2,
    });

    const formattedData = cmfData.map((d) => ({
      time: d.time,
      value: d.value,
    }));

    areaSeries.setData(formattedData as any);
    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      if (chartRef.current && container) {
        chartRef.current.applyOptions({ width: container.clientWidth });
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [cmfData, height]);

  const latestVal = cmfData.length > 0 ? cmfData[cmfData.length - 1].value : 0;
  const isAccumulation = latestVal > 0;

  return (
    <div className="w-full relative rounded-xl overflow-hidden border border-borderMuted bg-[#090D16] mt-2">
      <div ref={containerRef} className="w-full" style={{ height: `${height}px` }} />
      <div className="absolute top-2 left-3 flex items-center gap-3 pointer-events-none text-[10px] font-mono">
        <span className="font-bold text-gray-300 inline-flex items-center gap-1">
          Chaikin Money Flow (CMF 20)
          <span className="pointer-events-auto">
            <InfoTip term="cmf" />
          </span>
        </span>
        <span className={isAccumulation ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
          {isAccumulation ? '▲' : '▼'} {fmtSigned(latestVal, 3)} ({isAccumulation ? 'Uang Masuk / Inflow' : 'Uang Keluar / Outflow'})
        </span>
        <span className="text-gray-500 hidden sm:inline">| 0 = netral · ≥ +0,04 akumulasi · ≥ +0,15 akumulasi kuat</span>
      </div>
    </div>
  );
};
