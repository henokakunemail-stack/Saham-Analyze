import React from 'react';
import { CheckCircle2, Clock, Ban } from 'lucide-react';

export type ActionStatus = 'LAYAK' | 'TUNGGU' | 'HINDARI';

const STYLES: Record<ActionStatus, { label: string; title: string; cls: string; icon: React.ReactNode }> = {
  LAYAK: {
    label: 'LAYAK',
    title: 'Semua syarat teknis terpenuhi — bukan jaminan naik',
    cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    icon: <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  TUNGGU: {
    label: 'TUNGGU',
    title: 'Ada syarat yang belum terpenuhi — pantau dulu',
    cls: 'bg-slate-800 text-amber-200 border-amber-500/30',
    icon: <Clock className="w-3.5 h-3.5" aria-hidden="true" />,
  },
  HINDARI: {
    label: 'HINDARI',
    title: 'Sinyal jual, harga di bawah cut loss, atau terkunci ARB',
    cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    icon: <Ban className="w-3.5 h-3.5" aria-hidden="true" />,
  },
};

/** Action status of a plan: icon + text, so it never relies on colour alone. */
export const ActionStatusBadge: React.FC<{ status?: ActionStatus | string | null; compact?: boolean }> = ({
  status,
  compact = false,
}) => {
  const st = STYLES[(status ?? '') as ActionStatus];
  if (!st) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-semibold ${st.cls} ${
        compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs'
      }`}
      title={st.title}
    >
      {st.icon}
      <span>{st.label}</span>
    </span>
  );
};
