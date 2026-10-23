import React from 'react';
import { ActionStatusBadge } from './ActionStatusBadge';
import { ActionGates, type ActionInfo } from './ActionGates';
import { PlanNow } from './FlowSummaryCard';
import { InfoTip } from './help/InfoTip';
import { fmtNum, fmtPct, fmtPrice } from './help/format';
import type { StockReadingPlan, TradeLevels } from '../types/stock';

interface Props {
  action?: ActionInfo | null;
  reading?: StockReadingPlan | null;
  levels?: TradeLevels | null;
  /** Fallbacks when `levels` is missing (older engines). */
  buy?: number | null;
  stop?: number | null;
  tp1?: number | null;
  tp2?: number | null;
  rr?: number | null;
}

const BORDER: Record<string, string> = {
  LAYAK: 'border-emerald-500/40 from-emerald-950/40',
  TUNGGU: 'border-amber-500/30 from-amber-950/20',
  HINDARI: 'border-rose-500/40 from-rose-950/30',
};

/**
 * The first thing on the stock page: what to do today — status, the reason in one sentence, and
 * the order to place (buy limit, cut loss, targets). Everything else on the page explains it.
 */
export const DecisionStrip: React.FC<Props> = ({ action, reading, levels, buy, stop, tp1, tp2, rr }) => {
  const b = levels?.recommended_entry || buy || null;
  const sl = levels?.stop_loss || stop || null;
  const t1 = levels?.target_tp1 || tp1 || null;
  const t2 = levels?.target_tp2 || tp2 || null;
  const ratio = levels?.risk_reward_ratio ?? rr ?? null;
  const pct = (v: number | null) => (b && v ? fmtPct(((v - b) / b) * 100, 1) : '-');
  const status = action?.status ?? '';
  const headline = reading?.headline ?? action?.reasons?.[0] ?? '';

  return (
    <section
      aria-label="Keputusan hari ini"
      className={`p-4 rounded-xl border bg-gradient-to-r to-[#090D16] space-y-3 ${BORDER[status] ?? 'border-borderMuted from-surface'}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-300">Keputusan hari ini</h3>
        {action && <ActionStatusBadge status={action.status} />}
        <InfoTip term="action_status" />
        {b && ratio ? (
          <span className="ml-auto text-[11px] text-gray-400 font-mono flex items-center gap-1">
            Rugi : Untung (ke Target 1)
            <span className={ratio >= 2 ? 'text-emerald-300' : ratio < 1.2 ? 'text-amber-300' : 'text-gray-100'}>
              1 : {fmtNum(ratio, 2)}
            </span>
            <InfoTip term="risk_reward" />
          </span>
        ) : null}
      </div>
      {headline && <p className="text-sm text-gray-100 leading-snug">{headline}</p>}

      {b ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 font-mono">
          <div className="p-2.5 rounded-lg bg-cyan-500/5 border border-cyan-500/30">
            <div className="text-[11px] font-sans font-semibold text-cyan-300 flex items-center gap-1">
              Harga beli (limit) <InfoTip term="buy_limit" />
            </div>
            <div className="text-lg font-bold text-cyan-200">{fmtPrice(b)}</div>
            {levels?.entry_low && levels?.entry_high ? (
              <div className="text-[11px] text-gray-400">
                zona {fmtPrice(levels.entry_low)}–{fmtPrice(levels.entry_high)}
              </div>
            ) : null}
          </div>
          <div className="p-2.5 rounded-lg bg-rose-500/5 border border-rose-500/30">
            <div className="text-[11px] font-sans font-semibold text-rose-300 flex items-center gap-1">
              Cut loss <InfoTip term="stop_loss" />
            </div>
            <div className="text-lg font-bold text-rose-200">{fmtPrice(sl)}</div>
            <div className="text-[11px] text-gray-400">{pct(sl)} dari harga beli</div>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/30">
            <div className="text-[11px] font-sans font-semibold text-emerald-300 flex items-center gap-1">
              Target 1 <InfoTip term="take_profit" />
            </div>
            <div className="text-lg font-bold text-emerald-200">{fmtPrice(t1)}</div>
            <div className="text-[11px] text-gray-400">{pct(t1)} · jual separuh di sini</div>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
            <div className="text-[11px] font-sans font-semibold text-emerald-300/90">Target 2</div>
            <div className="text-lg font-bold text-emerald-200/90">{fmtPrice(t2)}</div>
            <div className="text-[11px] text-gray-400">{pct(t2)} · sisa posisi</div>
          </div>
        </div>
      ) : null}

      <PlanNow levels={levels} />

      {action && (
        <details className="rounded-lg border border-borderMuted/70 bg-[#090D16]/50 px-3 py-1.5">
          <summary className="cursor-pointer select-none text-[11px] font-semibold text-gray-300 hover:text-white">
            Kenapa {action.status}? Lihat syarat eksekusi
          </summary>
          <div className="pt-2">
            <ActionGates action={action} />
          </div>
        </details>
      )}
    </section>
  );
};
