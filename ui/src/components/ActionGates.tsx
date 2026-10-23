import React from 'react';
import { ListChecks } from 'lucide-react';
import { ActionStatusBadge, type ActionStatus } from './ActionStatusBadge';

/** Output of engine/screener/actionability.assess (row.action / composite.action). */
export interface ActionInfo {
  status: ActionStatus;
  reasons: string[];
  gates: Record<string, boolean>;
}

const GATE_LABELS: Record<string, string> = {
  market_ok: 'Kondisi pasar',
  signal_ok: 'Sinyal beli',
  risk_ok: 'Risiko ≤ batas',
  vol_ok: 'Volatilitas wajar',
  liquid_ok: 'Cukup likuid',
  data_ok: 'Data harga normal',
};

const GATE_ORDER = ['market_ok', 'signal_ok', 'risk_ok', 'vol_ok', 'liquid_ok', 'data_ok'];

/** Gate checklist (✓/✗) behind the LAYAK / TUNGGU / HINDARI status, with the reasons. */
export const ActionGates: React.FC<{ action?: ActionInfo | null }> = ({ action }) => {
  if (!action) return null;
  const keys = [
    ...GATE_ORDER.filter((k) => k in action.gates),
    ...Object.keys(action.gates).filter((k) => !GATE_ORDER.includes(k)),
  ];
  const passed = keys.filter((k) => action.gates[k]).length;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-gray-400">
          <ListChecks className="w-3.5 h-3.5" aria-hidden="true" />
          <span>
            Syarat eksekusi (layak dibeli): {passed}/{keys.length} lolos
          </span>
        </div>
        <ActionStatusBadge status={action.status} compact />
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {keys.map((key) => {
          const ok = action.gates[key];
          return (
            <li
              key={key}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-semibold ${
                ok
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
              }`}
            >
              <span aria-hidden="true">{ok ? '✓' : '✗'}</span>
              <span className="sr-only">{ok ? 'Lolos:' : 'Belum lolos:'}</span>
              {GATE_LABELS[key] ?? key}
            </li>
          );
        })}
      </ul>
      {action.reasons.length > 0 && (
        <ul className="text-[11px] text-gray-300 space-y-0.5">
          {action.reasons.map((r) => (
            <li key={r} className="flex gap-1.5">
              <span className="text-gray-500" aria-hidden="true">
                •
              </span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
      {action.status === 'LAYAK' && (
        <p className="text-[10px] text-gray-500">Syarat teknis terpenuhi — bukan jaminan harga naik.</p>
      )}
    </div>
  );
};
