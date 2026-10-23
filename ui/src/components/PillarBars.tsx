import React from 'react';

const PILLAR_LABELS: Record<string, string> = {
  pullback: 'Pullback dalam uptrend',
  trend: 'Arah tren',
  money_flow: 'Aliran dana',
  momentum: 'Momentum',
  setup: 'Setup',
  fundamental: 'Fundamental',
  sentiment: 'Sentimen berita',
};

const PILLAR_ORDER = ['pullback', 'trend', 'money_flow', 'momentum', 'setup', 'fundamental', 'sentiment'];

interface Props {
  /** Pillar values in −1..+1 (composite.pillar_values); missing pillars are skipped. */
  values?: Record<string, number> | null;
  /** Pillar weights (0..1), shown as a percentage next to the label. */
  weights?: Record<string, number> | null;
}

/** One horizontal bar per score pillar, centred at 0: right/green = supports, left/red = against. */
export const PillarBars: React.FC<Props> = ({ values, weights }) => {
  if (!values) return null;
  const keys = [
    ...PILLAR_ORDER.filter((k) => k in values),
    ...Object.keys(values).filter((k) => !PILLAR_ORDER.includes(k)),
  ];
  if (keys.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {keys.map((key) => {
        const raw = Number(values[key]);
        const v = Number.isFinite(raw) ? Math.max(-1, Math.min(1, raw)) : 0;
        const width = `${Math.abs(v) * 50}%`;
        const w = weights?.[key];
        const label = PILLAR_LABELS[key] ?? key;
        return (
          <li key={key} className="grid grid-cols-[minmax(0,10rem)_1fr_3rem] items-center gap-2 text-[11px]">
            <span className="text-gray-300 truncate" title={label}>
              {label}
              {w !== undefined && w !== null && <span className="text-gray-500"> · {Math.round(w * 100)}%</span>}
            </span>
            <div
              className="relative h-2 rounded-full bg-slate-800"
              role="meter"
              aria-label={label}
              aria-valuemin={-1}
              aria-valuemax={1}
              aria-valuenow={v}
            >
              <div className="absolute inset-y-0 left-1/2 w-px bg-slate-600" aria-hidden="true" />
              <div
                className={`absolute inset-y-0 rounded-full ${v >= 0 ? 'bg-emerald-400/80' : 'bg-rose-400/80'}`}
                style={v >= 0 ? { left: '50%', width } : { right: '50%', width }}
              />
            </div>
            <span className={`font-mono text-right ${v > 0 ? 'text-emerald-300' : v < 0 ? 'text-rose-300' : 'text-gray-400'}`}>
              {v > 0 ? '+' : ''}
              {v.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </li>
        );
      })}
    </ul>
  );
};
