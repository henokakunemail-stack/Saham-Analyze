import React from 'react';
import { MoneyFlowStatus } from '../types/stock';
import { ArrowUpRight, ArrowDownRight, Minus, Flame, AlertTriangle } from 'lucide-react';
import { InfoTip } from './help/InfoTip';
import { getTerm } from '../lib/glossary';
import { fmtSigned } from './help/format';

interface Props {
  status: MoneyFlowStatus;
  cmf?: number;
  showIcon?: boolean;
  /** Tampilkan ikon (i) penjelasan di samping badge. */
  info?: boolean;
}

const STYLES: Record<MoneyFlowStatus, { label: string; cls: string; icon: React.ReactNode }> = {
  STRONG_INFLOW: {
    label: 'Akumulasi kuat',
    cls: 'font-semibold bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    icon: <Flame className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />,
  },
  MILD_INFLOW: {
    label: 'Akumulasi',
    cls: 'font-medium bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
    icon: <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  NEUTRAL: {
    label: 'Netral',
    cls: 'font-medium bg-slate-800 text-slate-300 border-slate-700',
    icon: <Minus className="w-3 h-3 text-slate-400" aria-hidden="true" />,
  },
  MILD_OUTFLOW: {
    label: 'Distribusi',
    cls: 'font-medium bg-amber-500/10 text-amber-300 border-amber-500/20',
    icon: <ArrowDownRight className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  STRONG_OUTFLOW: {
    label: 'Distribusi kuat',
    cls: 'font-semibold bg-rose-500/15 text-rose-400 border-rose-500/30',
    icon: <AlertTriangle className="w-3.5 h-3.5 text-rose-400" aria-hidden="true" />,
  },
};

export const InflowBadge: React.FC<Props> = ({ status, cmf, showIcon = true, info = false }) => {
  const st = STYLES[status] ?? STYLES.NEUTRAL;
  const termKey = `mfs_${STYLES[status] ? status : 'NEUTRAL'}`;
  const entry = getTerm(termKey);

  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border whitespace-nowrap ${st.cls}`}
        title={entry ? `${entry.term}: ${entry.what}` : undefined}
      >
        {showIcon && st.icon}
        <span>{st.label}</span>
        {cmf !== undefined && cmf !== null && (
          <span className="opacity-75 font-mono text-[11px]">
            <span className="sr-only">CMF </span>
            {fmtSigned(cmf, 2)}
          </span>
        )}
      </span>
      {info && <InfoTip term={termKey} label={`Penjelasan status aliran dana ${st.label.toLowerCase()}`} />}
    </span>
  );
};
