import React, { useEffect, useState } from 'react';
import { Database, ChevronDown, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import type { DataHealth, DataLag } from '../types/stock';

const LOW_QUALITY = 80;

const fmtDay = (d?: string | null) =>
  d ? new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' }) : '-';

const fmtTime = (iso?: string) => {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? ''
    : d.toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const code = (t: string) => t.replace('.JK', '');

/** One line under a list header: how much of the price data behind it is fresh, with details on click.
 *  `refreshKey` changes when a new scan lands. */
export const DataHealthLine: React.FC<{ market: 'IDX' | 'US'; refreshKey?: string | number }> = ({ market, refreshKey }) => {
  const [data, setData] = useState<DataHealth | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    api.getDataHealth(market).then((r) => alive && setData(r));
    return () => {
      alive = false;
    };
  }, [market, refreshKey]);

  if (!data || data.available === false || !data.text) return null;
  const warn = !data.ok;
  const hasDetail = (data.stale_count ?? 0) + (data.failed_count ?? 0) + (data.low_quality_count ?? 0) > 0;

  return (
    <div className="text-[11px]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`inline-flex items-center gap-1.5 text-left ${warn ? 'text-amber-200' : 'text-gray-400'} hover:text-white`}
      >
        <Database className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span>
          {data.text}
          {data.expected_session && <span className="text-gray-500"> · sesi {fmtDay(data.expected_session)}</span>}
        </span>
        <ChevronDown className={`w-3 h-3 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="mt-2 p-3 rounded-xl border border-borderMuted bg-surfaceHover/40 space-y-2 text-gray-300 max-w-2xl">
          {(data.stale_count ?? 0) > 0 && (
            <p>
              <b className="text-amber-200">Terlambat</b> (harga terakhir lebih lama dari sesi bursa terakhir; statusnya
              ditahan TUNGGU):{' '}
              {data.stale!.map((s) => `${code(s.ticker)} (${s.days} hari, terakhir ${fmtDay(s.last_bar)})`).join(', ')}
            </p>
          )}
          {(data.failed_count ?? 0) > 0 && (
            <p>
              <b className="text-rose-300">Gagal diunduh</b> (tidak ada di daftar scan ini): {data.failed!.map(code).join(', ')}
              {(data.failed_count ?? 0) > (data.failed?.length ?? 0) && ` dan ${data.failed_count! - data.failed!.length} lainnya`}
            </p>
          )}
          {(data.low_quality_count ?? 0) > 0 && (
            <p>
              <b className="text-amber-200">Kualitas data rendah</b> (skor &lt; {LOW_QUALITY}):{' '}
              {data.low_quality!.map((l) => `${code(l.ticker)} ${l.score}${l.issues.length ? ` — ${l.issues.join(', ')}` : ''}`).join('; ')}
            </p>
          )}
          {!hasDetail && <p>Semua saham yang di-scan punya harga sesi terakhir dan tidak ada masalah kualitas berarti.</p>}
          <p className="text-[10px] text-gray-500 leading-relaxed">
            Sumber: {data.source}. {data.scanned_at && `Diperiksa ${fmtTime(data.scanned_at)}. `}
            Situs resmi BEI menolak akses otomatis dan tidak ada sumber gratis lain yang andal, jadi aplikasi tidak bisa
            memperbaiki data yang salah dari sumbernya — hanya mendeteksi dan menahan statusnya.
          </p>
        </div>
      )}
    </div>
  );
};

/** Card chip: late data or a low data-quality score. Renders nothing when the data is fine. */
export const DataWarnChip: React.FC<{ lag?: DataLag | null; score?: number | null }> = ({ lag, score }) => {
  const late = lag && lag.days > 0;
  const low = score !== null && score !== undefined && score < LOW_QUALITY;
  if (!late && !low) return null;
  const text = late ? `Data terlambat ${lag!.days} hari` : `Data kurang baik (${score})`;
  const title = late
    ? `Harga terakhir ${fmtDay(lag!.last_bar)}, sesi bursa terakhir ${fmtDay(lag!.expected)}. Rencana dari data lama — status ditahan TUNGGU.`
    : `Skor kualitas data ${score}/100 (ada tanggal bolong, lompatan harga, atau volume nol). Periksa grafik sebelum memakai rencananya.`;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap bg-amber-500/15 text-amber-200 border-amber-500/30"
      title={title}
      aria-label={title}
    >
      <AlertTriangle className="w-3 h-3" aria-hidden="true" />
      {text}
    </span>
  );
};
