import React, { useState, useMemo, useEffect } from 'react';
import { ScreenerItem } from '../types/stock';
import { InflowBadge } from './InflowBadge';
import { DirectionBadge } from './TrendDirectionPanel';
import { Star, BarChart2, ChevronUp, ChevronDown } from 'lucide-react';
import { InfoTip } from './help/InfoTip';
import { GlossaryButton } from './help/GlossaryDrawer';
import { getTerm } from '../lib/glossary';
import { fmtNum, fmtPct, fmtPrice } from './help/format';
import { ScreenerFilters } from './ScreenerFilters';
import { MarketBreadthPanel } from './MarketBreadthPanel';
import { AbnormalDaysChip } from './AbnormalDaysChip';
import { ActionStatusBadge } from './ActionStatusBadge';
import { Criteria, EMPTY_CRITERIA, RANGE_DEFS, matches } from '../lib/screenerCriteria';

interface Props {
  items: ScreenerItem[];
  onSelectTicker: (ticker: string, market?: 'IDX' | 'US') => void;
  onToggleWatchlist: (ticker: string) => void;
  watchlistSet: Set<string>;
  /** Show presets + advanced filters (off for views that pre-filter, e.g. the money-flow radar). */
  enableFilters?: boolean;
  market?: 'IDX' | 'US';
}

type SortField = 'score' | 'price' | 'change_pct' | 'rsi14' | 'cmf20' | 'vol_ratio' | 'direction_score' | 'liq_bn' | 'ret_3m' | 'rs_60d';

const STORAGE_KEY = 'saham.screener.criteria.v1';
const NESTED_SORT = Object.fromEntries(RANGE_DEFS.map((d) => [d.key, d.get]));
const sortValue = (item: ScreenerItem, field: SortField): number => {
  const getter = (NESTED_SORT as Record<string, (i: ScreenerItem) => number | null | undefined>)[field];
  const v = getter ? getter(item) : (item as unknown as Record<string, number>)[field];
  return v === undefined || v === null || Number.isNaN(v) ? -Infinity : v;
};

/** Average daily traded value in the market's own currency: IDX in miliar Rp, US in USD. */
const fmtLiquidity = (value: number, market: 'IDX' | 'US'): string => {
  if (market === 'US') {
    return Math.abs(value) >= 1e9 ? `${fmtNum(value / 1e9, 1)} Mrd USD` : `${fmtNum(value / 1e6, 1)} Jt USD`;
  }
  return `${fmtNum(value / 1e9, 1)} Mrd`;
};

const STANCE_LABEL: Record<string, { text: string; cls: string }> = {
  LAYAK_DIPERTIMBANGKAN: { text: 'Layak dipertimbangkan', cls: 'text-emerald-300' },
  TUNGGU_PEMICU: { text: 'Tunggu pemicu', cls: 'text-sky-300' },
  PANTAU: { text: 'Pantau', cls: 'text-gray-200' },
  TUNGGU_PULLBACK: { text: 'Tunggu pullback', cls: 'text-amber-300' },
  TAHAN: { text: 'Tahan pembelian', cls: 'text-rose-300' },
  HINDARI: { text: 'Hindari', cls: 'text-rose-300' },
  LEWAT: { text: 'Sudah lewat hari ini', cls: 'text-amber-300' },
  BATAL: { text: 'Rencana batal', cls: 'text-rose-300' },
  JANGAN_KEJAR: { text: 'Jangan dikejar', cls: 'text-amber-300' },
  NETRAL: { text: 'Netral', cls: 'text-gray-300' },
};

function loadCriteria(): { criteria: Criteria; preset: string | null } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return { criteria: { ...EMPTY_CRITERIA, ...parsed.criteria }, preset: parsed.preset ?? null };
    }
  } catch {
    // storage unavailable: start empty
  }
  return { criteria: EMPTY_CRITERIA, preset: null };
}

interface SortHeaderProps {
  label: string;
  field: SortField;
  term?: string;
  center?: boolean;
  showIndicator?: boolean;
  sortField: SortField;
  sortAsc: boolean;
  onSort: (field: SortField) => void;
}

/** Header kolom yang bisa diurutkan (klik / Enter) + ikon penjelasan istilah. */
const SortHeader: React.FC<SortHeaderProps> = ({ label, field, term, center, showIndicator = true, sortField, sortAsc, onSort }) => {
  const active = showIndicator && sortField === field;
  return (
    <th
      scope="col"
      className={`py-3 px-4 ${center ? 'text-center' : ''}`}
      aria-sort={active ? (sortAsc ? 'ascending' : 'descending') : undefined}
    >
      <div className={`flex items-center gap-1 ${center ? 'justify-center' : ''}`}>
        <button
          type="button"
          onClick={() => onSort(field)}
          className="inline-flex items-center gap-1 uppercase tracking-wider hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/70 rounded"
          title={`Urutkan berdasarkan ${label}`}
        >
          <span>{label}</span>
          {active && (sortAsc ? <ChevronUp className="w-3 h-3 text-emerald-400" aria-hidden="true" /> : <ChevronDown className="w-3 h-3 text-emerald-400" aria-hidden="true" />)}
        </button>
        {term && <InfoTip term={term} />}
      </div>
    </th>
  );
};

export const ScreenerTable: React.FC<Props> = ({
  items,
  onSelectTicker,
  onToggleWatchlist,
  watchlistSet,
  enableFilters = true,
  market = 'IDX',
}) => {
  const [initial] = useState(loadCriteria);
  const [criteria, setCriteria] = useState<Criteria>(initial.criteria);
  const [activePreset, setActivePreset] = useState<string | null>(initial.preset);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ criteria, preset: activePreset }));
    } catch {
      // ignore
    }
  }, [criteria, activePreset]);
  const [sortField, setSortField] = useState<SortField>('score');
  const [sortAsc, setSortAsc] = useState<boolean>(false);
  const [filterText, setFilterText] = useState<string>('');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false); // default descending for financial metrics
    }
  };

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      // Search filter
      if (filterText) {
        const query = filterText.toUpperCase();
        const cat = (item.catalyst || '').toUpperCase();
        if (!item.ticker.includes(query) && !cat.includes(query)) {
          return false;
        }
      }

      return enableFilters ? matches(item, criteria) : true;
    });
  }, [items, criteria, filterText, enableFilters]);

  const sortProps = { sortField, sortAsc, onSort: handleSort };

  const sortedItems = useMemo(() => {
    return [...filteredItems].sort((a, b) => {
      const valA = sortValue(a, sortField);
      const valB = sortValue(b, sortField);
      if (valA < valB) return sortAsc ? -1 : 1;
      if (valA > valB) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [filteredItems, sortField, sortAsc]);

  return (
    <div className="space-y-4">
      {/* Market breadth & sector strength; clicking a sector filters the table */}
      {enableFilters && (
        <MarketBreadthPanel
          market={market}
          selectedSector={criteria.sectors?.[0] ?? null}
          onSelectSector={(sector) => setCriteria({ ...criteria, sectors: sector ? [sector] : [] })}
        />
      )}

      {/* Presets + advanced multi-indicator filters */}
      {enableFilters && <ScreenerFilters
        criteria={criteria}
        onChange={setCriteria}
        activePreset={activePreset}
        onPreset={setActivePreset}
        matched={filteredItems.length}
        total={items.length}
      />}

      {/* Search */}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <div className="flex items-center gap-2">
          <GlossaryButton />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter ticker / katalis..."
            aria-label="Filter ticker atau katalis"
            className="bg-surface border border-borderMuted rounded-xl px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 font-mono w-48"
          />
        </div>
      </div>
      <p className="text-[11px] text-gray-500 -mt-1">
        Skor dan label adalah ringkasan kondisi teknikal hari ini, bukan prediksi harga. Arahkan kursor / tekan ikon{' '}
        <span aria-hidden="true">ⓘ</span> di judul kolom untuk penjelasan.
      </p>

      {/* Table Container */}
      <div className="rounded-xl border border-borderMuted bg-surface overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#090D16]/90 border-b border-borderMuted text-gray-400 font-semibold uppercase text-[10px] tracking-wider select-none">
              <tr>
                <th scope="col" className="py-3 px-3 w-10 text-center">Pin</th>
                <th scope="col" className="py-3 px-4">Ticker</th>
                <SortHeader label="Harga" field="price" {...sortProps} />
                <SortHeader label="Chg %" field="change_pct" {...sortProps} />
                <SortHeader label="Arah Tren" field="direction_score" term="direction_score" {...sortProps} />
                <SortHeader label="Status Aliran Dana (CMF)" field="cmf20" term="money_flow_status" {...sortProps} />
                <SortHeader label="RSI (14)" field="rsi14" term="rsi" {...sortProps} />
                <SortHeader label="Vol Ratio" field="vol_ratio" term="vol_ratio" {...sortProps} />
                <SortHeader label="Likuiditas" field="liq_bn" {...sortProps} />
                <SortHeader label="Ret 3 Bln" field="ret_3m" {...sortProps} />
                <SortHeader label="vs Indeks 60H" field="rs_60d" {...sortProps} />
                <th scope="col" className="py-3 px-4">Status</th>
                <th scope="col" className="py-3 px-4">Katalis Berita</th>
                <SortHeader label="Skor Potensi" field="score" term="composite_score" center {...sortProps} />
                <th scope="col" className="py-3 px-4 text-center">Chart</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-borderMuted">
              {sortedItems.length === 0 ? (
                <tr>
                  <td colSpan={15} className="py-8 text-center text-gray-500 font-medium">
                    Tidak ada saham yang cocok dengan filter saat ini.
                  </td>
                </tr>
              ) : (
                sortedItems.map((item) => {
                  const isPos = item.change_pct >= 0;
                  const isPinned = watchlistSet.has(item.ticker);

                  return (
                    <tr
                      key={item.ticker}
                      className="hover:bg-surfaceHover/80 transition-colors group cursor-pointer"
                      onClick={() => onSelectTicker(item.ticker, item.market)}
                    >
                      {/* Watchlist toggle */}
                      <td className="py-3 px-3 text-center" onClick={(e) => { e.stopPropagation(); onToggleWatchlist(item.ticker); }}>
                        <button className="text-gray-500 hover:text-amber-400 transition-colors" aria-label={isPinned ? `Hapus ${item.ticker} dari watchlist` : `Tambah ${item.ticker} ke watchlist`} aria-pressed={isPinned}>
                          <Star className={`w-3.5 h-3.5 ${isPinned ? 'fill-amber-400 text-amber-400' : ''}`} />
                        </button>
                      </td>

                      {/* Ticker */}
                      <td className="py-3 px-4 font-mono font-bold text-white group-hover:text-emerald-400 transition-colors">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span>{item.ticker}</span>
                          {item.is_confirmed_breakout && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30" title="Breakout terkonfirmasi: ≥4 dari 6 gerbang konfluensi lolos dan searah tren">
                              ✅ KONFLUENSI
                            </span>
                          )}
                          {item.is_speculative ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30" title={getTerm('speculative')?.read}>
                              ⚠️ Spekulatif
                            </span>
                          ) : item.health_grade === 'HEALTHY' ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-sans font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30" title="Kondisi keuangan emiten sehat (grade HEALTHY)">
                              🛡️ Sehat
                            </span>
                          ) : null}
                          <AbnormalDaysChip items={item.abnormal_recent} compact />
                          {item.vsa_signal && item.vsa_signal !== 'NORMAL' && (
                            <span className="px-1 py-0.2 rounded text-[8px] font-sans bg-purple-500/10 text-purple-300 border border-purple-500/20" title={`VSA: ${getTerm(`vsa_${item.vsa_signal}`)?.read ?? item.vsa_desc ?? ''}`}>
                              {item.vsa_signal}
                            </span>
                          )}
                        </div>
                        {item.sector && <div className="text-[10px] font-sans font-normal text-gray-500 mt-0.5">{item.sector}</div>}
                      </td>

                      {/* Price */}
                      <td className="py-3 px-4 font-mono font-semibold text-gray-200">
                        {fmtPrice(item.price)}
                      </td>

                      {/* Change % */}
                      <td className={`py-3 px-4 font-mono font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                        <span aria-hidden="true" className="text-[9px] mr-0.5">{isPos ? '▲' : '▼'}</span>
                        {fmtPct(item.change_pct ?? 0)}
                      </td>

                      {/* Trend Direction */}
                      <td className="py-3 px-4">
                        <DirectionBadge score={item.direction_score} label={item.direction_label} />
                      </td>

                      {/* Money Flow Badge */}
                      <td className="py-3 px-4">
                        <InflowBadge status={item.money_flow_status} cmf={item.cmf20} />
                      </td>

                      {/* RSI 14 */}
                      <td className="py-3 px-4 font-mono">
                        <span className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ${
                          item.rsi14 > 70
                            ? 'bg-rose-500/10 text-rose-400'
                            : 'text-gray-300'
                        }`}>
                          {fmtNum(item.rsi14, 1)}
                          {item.rsi14 > 70 && <span className="ml-0.5" title="Jenuh beli (overbought)">⚠<span className="sr-only"> jenuh beli</span></span>}
                          {item.rsi14 < 30 && <span className="ml-0.5" title="Jenuh jual (oversold)">↓<span className="sr-only"> jenuh jual</span></span>}
                        </span>
                      </td>

                      {/* Volume Ratio */}
                      <td className="py-3 px-4 font-mono">
                        <span className={`font-semibold ${item.vol_ratio >= 1.5 ? 'text-amber-400 font-bold' : 'text-gray-300'}`}>
                          {fmtNum(item.vol_ratio, 2)}x
                          {item.vol_ratio >= 1.5 && <span className="ml-0.5" title="Lonjakan volume (≥1,5x rata-rata)">▲<span className="sr-only"> lonjakan volume</span></span>}
                        </span>
                      </td>

                      {/* Liquidity: average daily traded value (20 days) */}
                      <td className="py-3 px-4 font-mono text-[11px]">
                        {item.screen?.avg_value_20d ? (
                          <span
                            className={item.screen.illiquid ? 'text-amber-400' : 'text-gray-300'}
                            title={`Rata-rata nilai transaksi harian 20 hari (${(item.market ?? market) === 'US' ? 'USD' : 'Mrd = miliar Rp'})`}
                          >
                            {fmtLiquidity(item.screen.avg_value_20d, item.market ?? market)}
                            {item.screen.illiquid && <span className="ml-0.5" title="Likuiditas rendah">⚠</span>}
                          </span>
                        ) : (
                          '-'
                        )}
                      </td>

                      {/* 3-month return */}
                      <td className={`py-3 px-4 font-mono text-[11px] ${(item.screen?.ret_3m ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {item.screen?.ret_3m !== undefined && item.screen?.ret_3m !== null ? fmtPct(item.screen.ret_3m) : '-'}
                      </td>

                      {/* Relative strength vs index, 60 days */}
                      <td className={`py-3 px-4 font-mono text-[11px] ${(item.screen?.rs_60d ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {item.screen?.rs_60d !== undefined && item.screen?.rs_60d !== null ? fmtPct(item.screen.rs_60d) : '-'}
                      </td>

                      {/* Action status (Fase 1), else the algorithm stance */}
                      <td className="py-3 px-4 text-[11px] whitespace-nowrap" title={item.action?.reasons?.join(' · ')}>
                        {item.action ? (
                          <ActionStatusBadge status={item.action.status} compact />
                        ) : item.reading ? (
                          <span className={STANCE_LABEL[item.reading.stance]?.cls ?? 'text-gray-300'} title={item.reading.headline}>
                            {STANCE_LABEL[item.reading.stance]?.text ?? item.reading.stance}
                          </span>
                        ) : (
                          '-'
                        )}
                      </td>

                      {/* Catalyst */}
                      <td className="py-3 px-4 text-gray-300 max-w-[200px] truncate text-[11px]" title={item.catalyst}>
                        {item.catalyst || 'Kondisi Normal'}
                      </td>

                      {/* Final Score */}
                      <td className="py-3 px-4 text-center">
                        <span className={`inline-flex items-center justify-center px-2.5 py-1 rounded-full text-xs font-mono font-bold ${
                          item.score >= 80
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : item.score >= 65
                            ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                            : item.score >= 45
                            ? 'bg-slate-800 text-slate-300 border border-slate-700'
                            : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                        }`} title={item.badge_text}>
                          {item.score}
                          <span className="sr-only"> dari 100, {item.badge_text}</span>
                        </span>
                      </td>

                      {/* Chart button */}
                      <td className="py-3 px-4 text-center" onClick={(e) => { e.stopPropagation(); onSelectTicker(item.ticker, item.market); }}>
                        <button className="p-1 rounded-md hover:bg-slate-700 text-gray-400 hover:text-emerald-400 transition-colors" aria-label={`Buka detail ${item.ticker}`}>
                          <BarChart2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
