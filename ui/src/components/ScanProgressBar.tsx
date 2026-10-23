import React from 'react';
import { ScanProgress } from '../types/feedback';

interface Props {
  market: 'IDX' | 'US';
  /** Live progress polled by App; hidden when idle or null. */
  progress?: ScanProgress | null;
}

export function formatEta(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return 'menghitung sisa waktu…';
  if (sec < 5) return 'hampir selesai';
  if (sec < 60) return `±${Math.round(sec / 5) * 5} detik lagi`;
  const min = Math.floor(sec / 60);
  const rest = Math.round((sec % 60) / 10) * 10;
  return rest > 0 && min < 5 ? `±${min} menit ${rest} detik lagi` : `±${Math.round(sec / 60)} menit lagi`;
}

/** Speed & Feedback: thin live scan progress bar (mounted in App under the Header). */
export const ScanProgressBar: React.FC<Props> = ({ market, progress }) => {
  if (!progress || !progress.active) return null;

  const pct = progress.total > 0 ? Math.min(100, (progress.done / progress.total) * 100) : 0;
  const otherMarket = progress.market && progress.market !== market;

  return (
    <div className="relative z-10 border-b border-borderMuted bg-surface/60" role="progressbar"
      aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
      <div className="h-[3px] w-full bg-slate-800/80 overflow-hidden">
        {progress.done === 0 ? (
          <div className="h-full w-1/3 bg-emerald-500/70 animate-pulse" />
        ) : (
          <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%` }} />
        )}
      </div>
      <div className="px-6 py-1 flex items-center justify-between gap-3 text-[11px] font-mono text-gray-400">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shrink-0" />
          <span className="text-gray-200 truncate">
            {progress.phase === 'analysis' || (!progress.phase && progress.done > 0)
              ? `Menganalisis ${progress.done}/${progress.total} saham · ${formatEta(progress.eta_sec)}`
              : progress.phase_label
              ? `${progress.phase_label}…`
              : `Menyiapkan data pasar & berita · ${progress.total} saham`}
            {otherMarket ? ` (${progress.market})` : ''}
          </span>
          {progress.current_ticker && progress.done > 0 && (
            <span className="hidden md:inline text-gray-500 truncate">terakhir: {progress.current_ticker}</span>
          )}
        </div>
        {progress.failed > 0 && (
          <span className="text-amber-400/90 shrink-0" title={progress.failed_tickers.join(', ')}>
            {progress.failed} gagal
          </span>
        )}
      </div>
    </div>
  );
};
