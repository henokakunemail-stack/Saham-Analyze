import React, { useMemo } from 'react';
import { CheckCircle2, AlertTriangle, Hourglass, MessageSquareText } from 'lucide-react';
import { summarizeAnalysis, SummaryInput, SummaryTone } from './summarize';

const TONE_STYLE: Record<SummaryTone, { box: string; chip: string; label: string; icon: string }> = {
  positive: { box: 'border-emerald-500/40', chip: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40', label: 'Kondisi mendukung', icon: '▲' },
  neutral: { box: 'border-slate-600', chip: 'bg-slate-800 text-slate-200 border-slate-600', label: 'Netral / menunggu', icon: '■' },
  cautious: { box: 'border-amber-500/40', chip: 'bg-amber-500/15 text-amber-200 border-amber-500/40', label: 'Hati-hati', icon: '◆' },
  negative: { box: 'border-rose-500/40', chip: 'bg-rose-500/15 text-rose-300 border-rose-500/40', label: 'Belum mendukung', icon: '▼' },
};

const Column: React.FC<{ title: string; items: string[]; icon: React.ReactNode; empty: string; titleClass: string }> = ({
  title,
  items,
  icon,
  empty,
  titleClass,
}) => (
  <div className="p-3 rounded-lg bg-surface border border-borderMuted space-y-1.5">
    <h4 className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${titleClass}`}>
      {icon}
      {title}
    </h4>
    {items.length === 0 ? (
      <p className="text-[11px] text-gray-500 italic">{empty}</p>
    ) : (
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-[12px] text-gray-200 leading-snug flex gap-1.5">
            <span aria-hidden="true" className="text-gray-500">•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    )}
  </div>
);

/** Kartu "Ringkasan Sederhana" di atas detail saham. */
export const PlainSummaryCard: React.FC<{ analysis: SummaryInput }> = ({ analysis }) => {
  const s = useMemo(() => summarizeAnalysis(analysis), [analysis]);
  const st = TONE_STYLE[s.tone];

  return (
    <section aria-labelledby="plain-summary-title" className={`p-4 rounded-xl bg-[#090D16] border ${st.box} space-y-3`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="plain-summary-title" className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-200">
          <MessageSquareText className="w-4 h-4 text-cyan-400" aria-hidden="true" />
          Ringkasan Sederhana
        </h3>
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-bold ${st.chip}`}>
          <span aria-hidden="true">{st.icon}</span>
          {st.label}
        </span>
      </div>
      <div>
        <p className="text-sm font-bold text-white">{s.headline}</p>
        <p className="text-[13px] text-gray-300 leading-relaxed mt-0.5">{s.conclusion}</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <Column
          title="Yang mendukung"
          items={s.supports}
          icon={<CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />}
          empty="Belum ada faktor pendukung yang menonjol."
          titleClass="text-emerald-300"
        />
        <Column
          title="Yang perlu diwaspadai"
          items={s.risks}
          icon={<AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />}
          empty="Tidak ada risiko menonjol dari data ini — risiko pasar tetap ada."
          titleClass="text-amber-300"
        />
        <Column
          title="Yang perlu ditunggu"
          items={s.waitFor}
          icon={<Hourglass className="w-3.5 h-3.5" aria-hidden="true" />}
          empty="-"
          titleClass="text-cyan-300"
        />
      </div>
      <p className="text-[10px] text-gray-500">
        Disusun otomatis dari indikator di bawah dengan aturan tetap. Bukan nasihat investasi.
      </p>
    </section>
  );
};
