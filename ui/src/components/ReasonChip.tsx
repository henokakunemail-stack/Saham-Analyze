import React from 'react';
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';

/** Older rows have no reason_signs: read the sign from the engine's own prefixes and wording. */
const NEGATIVE = /^(⛔|⚠|🐻|⏳|📰|🔻|🔴|🟠)|Keluar|Rawan|Bearish|Turun|Rusak|Jenuh Beli|Tekanan Jual|Negatif|Spekulatif|Distribusi/i;

export function reasonSign(text: string, sign?: number): number {
  if (sign === 1 || sign === -1 || sign === 0) return sign;
  return NEGATIVE.test(text) ? -1 : 1;
}

/** One engine reason with an icon that matches its direction (never a green check on a warning). */
export const ReasonChip: React.FC<{ text: string; sign?: number }> = ({ text, sign }) => {
  const s = reasonSign(text, sign);
  return (
    <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#090D16] border border-borderMuted text-[11px] text-gray-300">
      {s > 0 ? (
        <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" aria-label="mendukung" />
      ) : s < 0 ? (
        <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" aria-label="perlu diwaspadai" />
      ) : (
        <Info className="w-3 h-3 text-gray-400 shrink-0" aria-label="catatan" />
      )}
      <span>{text}</span>
    </div>
  );
};
