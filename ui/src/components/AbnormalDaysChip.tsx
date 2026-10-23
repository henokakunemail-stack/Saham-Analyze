import React from 'react';
import { AlertTriangle } from 'lucide-react';

export interface AbnormalDay {
  date: string;
  kind: string;
  label: string;
}

const SHORT: Record<string, string> = {
  LOCK_DOWN: 'ARB',
  LOCK_UP: 'ARA',
  LIMIT_DOWN: 'Batas ARB',
  LIMIT_UP: 'Batas ARA',
  SUSPENSION_GAP: 'Suspensi',
  CORP_ACTION: 'Aksi korporasi',
};

const DOWN_KINDS = new Set(['LOCK_DOWN', 'LIMIT_DOWN', 'SUSPENSION_GAP']);

const parseDay = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`);

/** "19 Okt" (short Indonesian date); the raw string when it cannot be parsed. */
const fmtShort = (d: string) => {
  const date = parseDay(d);
  return isNaN(date.getTime()) ? d : date.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' });
};

const fmtLong = (d: string) => {
  const date = parseDay(d);
  return isNaN(date.getTime())
    ? d
    : date.toLocaleDateString('id-ID', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};

/** Warning chip for the latest abnormal trading day (ARB/ARA lock, limit move, halt, corporate action);
 *  the tooltip lists every abnormal day in the window. Renders nothing when there are none. */
export const AbnormalDaysChip: React.FC<{ items?: AbnormalDay[] | null; compact?: boolean }> = ({
  items,
  compact = false,
}) => {
  if (!items || items.length === 0) return null;
  const sorted = [...items].sort((a, b) => a.date.localeCompare(b.date));
  const last = sorted[sorted.length - 1];
  const tone = DOWN_KINDS.has(last.kind)
    ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    : 'bg-amber-500/15 text-amber-300 border-amber-500/30';
  const title = [
    'Hari perdagangan tidak normal (20 hari terakhir):',
    ...[...sorted].reverse().map((it) => `• ${fmtLong(it.date)} — ${it.label}`),
  ].join('\n');
  const text = `${SHORT[last.kind] ?? last.label} ${fmtShort(last.date)}`;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-semibold whitespace-nowrap ${tone} ${
        compact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-[11px]'
      }`}
      title={title}
      aria-label={`${last.label}, ${fmtLong(last.date)}${sorted.length > 1 ? `, dan ${sorted.length - 1} hari lain` : ''}`}
    >
      <AlertTriangle className={compact ? 'w-3 h-3' : 'w-3.5 h-3.5'} aria-hidden="true" />
      <span>{text}</span>
      {sorted.length > 1 && <span className="opacity-70">+{sorted.length - 1}</span>}
    </span>
  );
};
