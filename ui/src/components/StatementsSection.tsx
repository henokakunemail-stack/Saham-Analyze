import React, { useEffect, useState } from 'react';
import { FileText, AlertTriangle, Info, OctagonAlert } from 'lucide-react';
import { api } from '../api/client';
import type { FinancialStatements } from '../types/stock';

const LEVEL: Record<string, { cls: string; Icon: React.FC<{ className?: string }> }> = {
  danger: { cls: 'text-rose-300', Icon: OctagonAlert },
  warning: { cls: 'text-amber-300', Icon: AlertTriangle },
  info: { cls: 'text-gray-300', Icon: Info },
};

/** Amounts in the currency the company reports in: IDR as T (triliun) / M (miliar) / jt; USD as US$ … M / B. */
const money = (v: number | null | undefined, currency: string) => {
  if (v === null || v === undefined) return '-';
  const a = Math.abs(v);
  const sign = v < 0 ? '−' : '';
  const f = (x: number) => x.toLocaleString('id-ID', { maximumFractionDigits: 1 });
  if (currency === 'IDR') return a >= 1e12 ? `${sign}${f(a / 1e12)} T` : a >= 1e9 ? `${sign}${f(a / 1e9)} M` : `${sign}${f(a / 1e6)} jt`;
  const sym = currency === 'USD' ? 'US$' : `${currency} `;
  return a >= 1e9 ? `${sign}${sym}${f(a / 1e9)} miliar` : `${sign}${sym}${f(a / 1e6)} juta`;
};
const pct = (v?: number | null) =>
  v === null || v === undefined ? '-' : `${v > 0 ? '+' : ''}${v.toLocaleString('id-ID', { maximumFractionDigits: 1 })}%`;
const num = (v?: number | null, d = 1) => (v === null || v === undefined ? '-' : v.toLocaleString('id-ID', { maximumFractionDigits: d }));

/**
 * Laporan keuangan dalam bahasa awam: tren 4–5 tahun, kualitas laba, neraca, bendera merah, dan
 * valuasi dibanding sektor. Informasi saja — tidak mengubah skor atau status (diuji: bendera merah
 * tidak konsisten memperburuk hasil trading 10 hari, kecuali utang tinggi secara umum).
 */
export const StatementsSection: React.FC<{ ticker: string; market: 'IDX' | 'US' }> = ({ ticker, market }) => {
  const [data, setData] = useState<FinancialStatements | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getStatements(ticker, market).then((r) => {
      if (alive) {
        setData(r);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [ticker, market]);

  if (loading) {
    return <div className="p-4 rounded-xl bg-surface border border-borderMuted text-xs text-gray-400">Memuat laporan keuangan…</div>;
  }
  if (!data || !data.available) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-borderMuted text-xs text-gray-400">
        Laporan keuangan belum tersedia dari sumber data (Yahoo Finance) untuk saham ini.
      </div>
    );
  }
  const v = data.valuation;
  const ccy = data.currency || (market === 'IDX' ? 'IDR' : 'USD');
  const cmp = (mine?: number | null, sector?: number | null) =>
    mine && sector ? (mine > sector * 1.2 ? 'lebih mahal dari sektor' : mine < sector * 0.8 ? 'lebih murah dari sektor' : 'setara sektor') : null;

  return (
    <section className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3" aria-label="Laporan keuangan">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-gray-200">
          <FileText className="w-4 h-4 text-sky-300" />
          Laporan keuangan {data.last_year ? `(tahun buku ${data.last_year})` : ''}
          {ccy !== 'IDR' && market === 'IDX' && (
            <span className="normal-case font-normal text-amber-300">· dilaporkan dalam {ccy}</span>
          )}
        </div>
        <span className="text-[11px] text-gray-400">Informasi saja — tidak mengubah skor atau status</span>
      </div>

      {data.flags.length > 0 ? (
        <ul className="space-y-1">
          {data.flags.map((f) => {
            const st = LEVEL[f.level] ?? LEVEL.info;
            return (
              <li key={f.code} className={`flex items-start gap-1.5 text-xs ${st.cls}`}>
                <st.Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                  {f.text}
                  {f.code === 'HIGH_DEBT' && (
                    <span className="text-gray-400"> Di uji historis, saham berutang tinggi rata-rata hasil tradingnya lebih buruk.</span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-emerald-300">Tidak ada bendera merah pada laporan tahunan terakhir.</p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Pendapatan (setahun)</div>
          <div className="font-mono text-gray-100">{pct(data.revenue_growth_pct)}</div>
          <div className="text-gray-500">3 thn: {pct(data.revenue_cagr_3y_pct)}/thn</div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Laba bersih (setahun)</div>
          <div className="font-mono text-gray-100">{pct(data.net_income_growth_pct)}</div>
          <div className="text-gray-500">margin {pct(data.net_margin_pct)}</div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Kas operasi ÷ laba</div>
          <div className="font-mono text-gray-100">{num(data.ocf_to_net_income, 2)}×</div>
          <div className="text-gray-500">≥ 1 = laba jadi uang tunai</div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">{data.financial ? 'ROE' : 'Utang ÷ ekuitas'}</div>
          <div className="font-mono text-gray-100">
            {data.financial ? pct(data.roe_pct) : `${num(data.debt_to_equity, 2)}×`}
          </div>
          <div className="text-gray-500">{data.financial ? 'bank: utang tidak dinilai' : `ROE ${pct(data.roe_pct)}`}</div>
        </div>
      </div>

      {v && (v.pe || v.pbv) ? (
        <p className="text-[11px] text-gray-300">
          Valuasi: PER {num(v.pe)}× {v.sector_pe ? `(median sektor ${num(v.sector_pe)}×${cmp(v.pe, v.sector_pe) ? ` — ${cmp(v.pe, v.sector_pe)}` : ''})` : ''}
          {' · '}PBV {num(v.pbv, 2)}× {v.sector_pbv ? `(median sektor ${num(v.sector_pbv, 2)}×)` : ''}
          {v.peers < 3 && <span className="text-gray-500"> · pembanding sektor terlalu sedikit</span>}
        </p>
      ) : null}

      {data.years.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr className="text-gray-400 text-left">
                <th className="py-1 pr-3 font-sans font-semibold">Tahun</th>
                <th className="py-1 pr-3 font-sans font-semibold text-right">Pendapatan</th>
                <th className="py-1 pr-3 font-sans font-semibold text-right">Laba bersih</th>
                <th className="py-1 font-sans font-semibold text-right">Kas operasi</th>
              </tr>
            </thead>
            <tbody>
              {data.years.map((y) => (
                <tr key={y.period} className="border-t border-borderMuted/60">
                  <td className="py-1 pr-3 text-gray-300">{y.period.slice(0, 4)}</td>
                  <td className="py-1 pr-3 text-right text-gray-200">{money(y.revenue, ccy)}</td>
                  <td className={`py-1 pr-3 text-right ${(y.net_income ?? 0) < 0 ? 'text-rose-300' : 'text-gray-200'}`}>
                    {money(y.net_income, ccy)}
                  </td>
                  <td className={`py-1 text-right ${(y.ocf ?? 0) < 0 ? 'text-rose-300' : 'text-gray-200'}`}>{money(y.ocf, ccy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[10px] text-gray-500">
        Sumber: Yahoo Finance (laporan tahunan & kuartalan). Data bisa terlambat atau tidak lengkap — cek laporan resmi di idx.co.id
        sebelum mengambil keputusan.
      </p>
    </section>
  );
};
