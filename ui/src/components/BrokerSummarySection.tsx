import React from 'react';
import { BrokerSummaryData, BrokerItem } from '../types/stock';
import type { BrokerSummaryTrust } from '../types/signals';
import { fmtNum, fmtPct, fmtPrice } from './help/format';
import { Building2, ArrowDownRight, ArrowUpRight, ShieldCheck, Users, HelpCircle, ExternalLink } from 'lucide-react';

interface Props {
  data?: BrokerSummaryData;
  currentPrice: number;
  onOpenSettings?: () => void;
}

export const BrokerSummarySection: React.FC<Props> = ({
  data,
  currentPrice,
  onOpenSettings,
}) => {
  if (!data) return null;

  const trust = data as BrokerSummaryTrust;
  const noRealData =
    trust.data_available === false ||
    data.is_simulated ||
    data.source === 'PROXY' ||
    data.source === 'NO_DATA' ||
    data.bandar_status === 'NO_DATA';

  if (noRealData) {
    const isUS = trust.no_data_reason === 'NOT_IDX';
    return (
      <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-3">
        <div className="flex items-center gap-2.5">
          <Building2 className="w-4 h-4 text-gray-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">Broker Summary (Bandarmologi)</h3>
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-gray-300 border border-slate-700">
            Data tidak tersedia
          </span>
        </div>
        <div className="flex items-start gap-2.5 text-xs text-gray-300">
          <HelpCircle className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />
          <div className="space-y-1.5">
            <p>
              {trust.no_data_message ||
                'Data broker summary asli belum tersedia. Masukkan API key Sectors.app di Pengaturan untuk melihat transaksi broker sebenarnya.'}
            </p>
            {!isUS && (
              <p className="text-[11px] text-gray-500">
                Aplikasi tidak menampilkan daftar broker tiruan, dan status akumulasi/distribusi bandar tidak dihitung
                tanpa data transaksi broker yang asli.
              </p>
            )}
          </div>
        </div>
        {!isUS && onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold transition-colors"
          >
            Buka Pengaturan
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
      </div>
    );
  }

  const formatIDR = (val?: number) => {
    if (!val || isNaN(val)) return '-';
    // Nilai transaksi (Rp): T = triliun, M = miliar, Jt = juta
    if (Math.abs(val) >= 1e12) return `Rp ${fmtNum(val / 1e12, 2, 2)} T`;
    if (Math.abs(val) >= 1e9) return `Rp ${fmtNum(val / 1e9, 2, 2)} M`;
    if (Math.abs(val) >= 1e6) return `Rp ${fmtNum(val / 1e6, 1, 1)} Jt`;
    return `Rp ${fmtNum(val, 0)}`;
  };

  const formatPrice = (val?: number) => {
    if (!val || isNaN(val)) return '-';
    return fmtPrice(val);
  };

  const renderBrokerBadge = (type: string) => {
    if (type === 'FOREIGN') {
      return (
        <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center gap-1" title="Institusi Asing (Smart Money)">
          <span>🏛️</span>
          <span>Asing</span>
        </span>
      );
    }
    if (type === 'DOMESTIC_INSTITUTION') {
      return (
        <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30 flex items-center gap-1" title="Institusi Domestik / BUMN / Dana Pensiun">
          <span>🏢</span>
          <span>Institusi</span>
        </span>
      );
    }
    return (
      <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1" title="Broker Ritel / Follower">
        <span>👤</span>
        <span>Ritel</span>
      </span>
    );
  };

  const isAccum = data.bandar_status.includes('ACCUM');
  const isDist = data.bandar_status.includes('DIST');

  return (
    <div className="p-4 rounded-xl bg-gradient-to-r from-[#0C1220] via-[#090D16] to-[#0C1220] border border-cyan-500/30 shadow-xl space-y-4">
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <Building2 className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">
            Broker Summary (Bandarmologi) · Transaksi Sekuritas Terbesar
          </h3>
          <span className="text-[10px] text-gray-500 font-mono">
            {data.trade_date}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {data.is_simulated ? (
            <span
              onClick={onOpenSettings}
              className="cursor-pointer px-2 py-0.5 rounded text-[10px] font-sans font-semibold bg-slate-800 text-gray-300 border border-slate-700 hover:text-cyan-300 transition-colors flex items-center gap-1"
              title="Menggunakan proxy algoritma VSA & CMF. Klik untuk menghubungkan API Key resmi Sectors.app di Settings."
            >
              <span>⚡ Proxy Algoritma</span>
              <ExternalLink className="w-2.5 h-2.5 text-cyan-400" />
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
              🟢 Live Sectors.app
            </span>
          )}

          <span
            className={`px-2.5 py-1 rounded-full text-xs font-mono font-extrabold border ${
              isAccum
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : isDist
                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                : 'bg-slate-800 text-slate-300 border-slate-700'
            }`}
          >
            {data.bandar_status_label}
          </span>
        </div>
      </div>

      {/* Bandar KPI Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 text-xs font-mono">
        {/* Metric 1: Bandar Average Price */}
        <div className="p-2.5 rounded-lg bg-surface border border-borderMuted">
          <span className="text-[10px] text-gray-400 uppercase block font-sans">Bandar Avg Price:</span>
          <span className="text-sm font-bold text-cyan-300 mt-0.5 block">
            {formatPrice(data.bandar_avg_price)}
          </span>
          <span className="text-[10px] text-gray-400 block mt-0.5 truncate">
            {data.bandar_avg_price > 0 && currentPrice > 0
              ? currentPrice >= data.bandar_avg_price
                ? `Pasar ${fmtPct(((currentPrice - data.bandar_avg_price) / data.bandar_avg_price) * 100, 1)} di atas`
                : `Pasar ${fmtPct(((currentPrice - data.bandar_avg_price) / data.bandar_avg_price) * 100, 1)} di bawah (diskon)`
              : 'Estimasi Modal'}
          </span>
        </div>

        {/* Metric 2: Concentration Ratio */}
        <div className="p-2.5 rounded-lg bg-surface border border-borderMuted">
          <span className="text-[10px] text-gray-400 uppercase block font-sans">Rasio Top 3 Buyer/Seller:</span>
          <span className={`text-sm font-bold mt-0.5 block ${data.top3_ratio >= 1.3 ? 'text-emerald-400' : data.top3_ratio <= 0.8 ? 'text-rose-400' : 'text-gray-200'}`}>
            {data.top3_ratio}x
          </span>
          <span className="text-[10px] text-gray-400 block mt-0.5">
            {data.top3_ratio >= 1.5 ? 'Dominasi Pembeli Kuat' : data.top3_ratio <= 0.7 ? 'Dominasi Penjual Kuat' : 'Volume Seimbang'}
          </span>
        </div>

        {/* Metric 3: Net Foreign Flow */}
        <div className="p-2.5 rounded-lg bg-surface border border-borderMuted">
          <span className="text-[10px] text-gray-400 uppercase block font-sans">Arus Dana Asing (Net):</span>
          <span className={`text-sm font-bold mt-0.5 block ${data.net_foreign_val >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {data.net_foreign_val >= 0 ? '+' : ''}{formatIDR(data.net_foreign_val)}
          </span>
          <span className="text-[10px] text-gray-400 block mt-0.5">
            {data.net_foreign_val >= 0 ? 'Net Buy Asing' : 'Net Sell Asing'}
          </span>
        </div>

        {/* Metric 4: Evaluasi Aksi */}
        <div className="p-2.5 rounded-lg bg-surface border border-borderMuted">
          <span className="text-[10px] text-gray-400 uppercase block font-sans">Aksi Bandar / Institusi:</span>
          <span className="text-sm font-bold text-white mt-0.5 block truncate">
            {data.bandar_status === 'BIG_ACCUM' ? 'Akumulasi Agresif' : data.bandar_status === 'BIG_DIST' ? 'Distribusi Agresif' : isAccum ? 'Akumulasi Ringan' : isDist ? 'Distribusi Ringan' : 'Netral'}
          </span>
          <span className="text-[10px] text-gray-400 block mt-0.5">
            {isAccum ? 'Koleksi Barang' : isDist ? 'Pelepasan Barang' : 'Fase Konsolidasi'}
          </span>
        </div>
      </div>

      {/* Two Column Table: Top 5 Buyers vs Top 5 Sellers */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* Left: Top 5 Buyers */}
        <div className="rounded-xl border border-emerald-500/20 bg-[#070B14] p-3 space-y-2">
          <div className="flex items-center justify-between border-b border-emerald-500/20 pb-1.5 text-emerald-400 font-bold">
            <div className="flex items-center gap-1.5">
              <ArrowDownRight className="w-4 h-4 text-emerald-400" />
              <span>Top 5 Pembeli (Buyers)</span>
            </div>
            <span className="text-[10px] font-mono text-gray-400">Total Beli</span>
          </div>

          <div className="divide-y divide-slate-800 font-mono">
            {data.top_buyers.slice(0, 5).map((b, idx) => (
              <div key={idx} className="py-1.5 flex items-center justify-between text-[11px] gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="font-bold text-white px-1.5 py-0.5 rounded bg-surface border border-borderMuted text-xs">
                    {b.broker}
                  </span>
                  <div className="min-w-0">
                    <span className="text-gray-300 truncate block text-[11px]">{b.name}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {renderBrokerBadge(b.type)}
                  <span className="font-bold text-emerald-400 min-w-[70px] text-right">
                    {formatIDR(b.bval)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Top 5 Sellers */}
        <div className="rounded-xl border border-rose-500/20 bg-[#070B14] p-3 space-y-2">
          <div className="flex items-center justify-between border-b border-rose-500/20 pb-1.5 text-rose-400 font-bold">
            <div className="flex items-center gap-1.5">
              <ArrowUpRight className="w-4 h-4 text-rose-400" />
              <span>Top 5 Penjual (Sellers)</span>
            </div>
            <span className="text-[10px] font-mono text-gray-400">Total Jual</span>
          </div>

          <div className="divide-y divide-slate-800 font-mono">
            {data.top_sellers.slice(0, 5).map((s, idx) => (
              <div key={idx} className="py-1.5 flex items-center justify-between text-[11px] gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="font-bold text-white px-1.5 py-0.5 rounded bg-surface border border-borderMuted text-xs">
                    {s.broker}
                  </span>
                  <div className="min-w-0">
                    <span className="text-gray-300 truncate block text-[11px]">{s.name}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {renderBrokerBadge(s.type)}
                  <span className="font-bold text-rose-400 min-w-[70px] text-right">
                    {formatIDR(s.sval)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Summary Notes */}
      {data.summary_notes && data.summary_notes.length > 0 && (
        <div className="p-3 rounded-lg bg-black/30 border border-slate-800 space-y-1.5 text-xs">
          <div className="text-[11px] font-bold text-gray-400 uppercase flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
            <span>Kesimpulan Bandarmologi & Analisa Aliran Sekuritas:</span>
          </div>
          <div className="space-y-1">
            {data.summary_notes.map((note, i) => (
              <p key={i} className="text-gray-300 text-[11px] leading-relaxed flex items-start gap-1.5">
                <span className="text-cyan-400 font-bold">•</span>
                <span>{note}</span>
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
