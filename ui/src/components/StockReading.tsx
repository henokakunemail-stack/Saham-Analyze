import React from 'react';
import { CheckCircle2, Circle, Newspaper, ExternalLink, ShieldAlert, Flag } from 'lucide-react';
import type { NewsHeadline, StockReadingPlan } from '../types/stock';

const STANCE_STYLE: Record<string, { label: string; cls: string }> = {
  LAYAK_DIPERTIMBANGKAN: { label: 'Layak Dipertimbangkan', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  TUNGGU_PEMICU: { label: 'Tunggu Pemicu', cls: 'bg-sky-500/15 text-sky-300 border-sky-500/40' },
  PANTAU: { label: 'Pantau', cls: 'bg-slate-700/40 text-slate-200 border-slate-600' },
  TUNGGU_PULLBACK: { label: 'Tunggu Pullback', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  TAHAN: { label: 'Tahan Pembelian', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/40' },
  HINDARI: { label: 'Hindari', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/40' },
  LEWAT: { label: 'Sudah Lewat Hari Ini', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  BATAL: { label: 'Rencana Batal', cls: 'bg-rose-500/15 text-rose-300 border-rose-500/40' },
  JANGAN_KEJAR: { label: 'Jangan Dikejar', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  NETRAL: { label: 'Netral', cls: 'bg-slate-700/40 text-slate-200 border-slate-600' },
};

/** Algorithm's explicit plan for one stock: stance, triggers (met or not), invalidation, target. */
export const ReadingPlan: React.FC<{ reading?: StockReadingPlan | null }> = ({ reading }) => {
  if (!reading) return null;
  const st = STANCE_STYLE[reading.stance] ?? STANCE_STYLE.NETRAL;
  return (
    <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted space-y-2 mb-3" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider font-bold text-gray-400">Bacaan Algoritma</span>
        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${st.cls}`}>{st.label}</span>
      </div>
      <p className="text-[11px] text-gray-200 leading-snug">{reading.headline}</p>
      <ul className="space-y-0.5">
        {reading.triggers.map((t) => (
          <li key={t.label} className={`flex items-center gap-1.5 text-[11px] ${t.met ? 'text-emerald-300' : 'text-gray-400'}`}>
            {t.met ? <CheckCircle2 className="w-3 h-3 shrink-0" /> : <Circle className="w-3 h-3 shrink-0" />}
            <span>
              {t.label}
              <span className="sr-only">{t.met ? ' (terpenuhi)' : ' (belum)'}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] font-mono">
        {reading.invalidation && (
          <span className="inline-flex items-center gap-1 text-rose-300">
            <ShieldAlert className="w-3 h-3" />
            {reading.invalidation}
          </span>
        )}
        {reading.target && (
          <span className="inline-flex items-center gap-1 text-emerald-300">
            <Flag className="w-3 h-3" />
            {reading.target}
          </span>
        )}
      </div>
      {reading.news_note && <p className="text-[10px] text-cyan-300">{reading.news_note}</p>}
    </div>
  );
};

const relTime = (hours?: number | null) => {
  if (hours === undefined || hours === null) return '';
  if (hours < 1) return 'baru saja';
  if (hours < 24) return `${Math.round(hours)} jam lalu`;
  return `${Math.round(hours / 24)} hari lalu`;
};

const DOT: Record<string, string> = { POSITIVE: 'bg-emerald-400', NEGATIVE: 'bg-rose-400', NEUTRAL: 'bg-slate-500' };
const DOT_LABEL: Record<string, string> = { POSITIVE: 'positif', NEGATIVE: 'negatif', NEUTRAL: 'netral' };

/** Latest per-stock headlines (newest first) with source, age and sentiment tag. */
export const LatestNews: React.FC<{ headlines?: NewsHeadline[]; checkedAt?: string | null; max?: number }> = ({
  headlines,
  checkedAt,
  max = 3,
}) => {
  const list = (headlines ?? []).slice(0, max);
  return (
    <div className="space-y-1" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider font-bold text-gray-400">
        <span className="inline-flex items-center gap-1">
          <Newspaper className="w-3 h-3 text-cyan-400" /> Berita Terbaru (7 hari)
        </span>
        {checkedAt && (
          <span className="normal-case font-normal text-gray-500">
            dicek {new Date(checkedAt).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>
      {list.length === 0 ? (
        <p className="text-[11px] text-gray-500">Tidak ada berita spesifik tentang saham ini dalam 7 hari terakhir.</p>
      ) : (
        list.map((h, i) => (
          <a
            key={`${h.title}-${i}`}
            href={h.link || undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-1.5 text-[11px] text-gray-200 hover:text-cyan-300 group/news"
          >
            <span
              className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${DOT[h.sentiment ?? 'NEUTRAL'] ?? DOT.NEUTRAL}`}
              title={`Sentimen ${DOT_LABEL[h.sentiment ?? 'NEUTRAL'] ?? 'netral'}`}
            />
            <span className="leading-snug">
              {h.title}
              <span className="text-gray-500">
                {' '}
                · {h.source}
                {h.age_hours !== undefined && h.age_hours !== null ? ` · ${relTime(h.age_hours)}` : ''}
                <span className="sr-only"> (sentimen {DOT_LABEL[h.sentiment ?? 'NEUTRAL']})</span>
              </span>
              {h.link && <ExternalLink className="inline w-2.5 h-2.5 ml-1 opacity-0 group-hover/news:opacity-100" />}
            </span>
          </a>
        ))
      )}
    </div>
  );
};
