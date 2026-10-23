import React, { useState } from 'react';
import { SlidersHorizontal, X, RotateCcw } from 'lucide-react';
import {
  Criteria,
  EMPTY_CRITERIA,
  PRESETS,
  RANGE_DEFS,
  RangeKey,
  PULLBACK_STATE_LABELS,
  FLOW_LABELS,
  HEALTH_LABELS,
  activeChips,
  isEmpty,
} from '../lib/screenerCriteria';

interface Props {
  criteria: Criteria;
  onChange: (c: Criteria) => void;
  activePreset: string | null;
  onPreset: (id: string | null) => void;
  matched: number;
  total: number;
}

const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

const ChoiceGroup: React.FC<{
  title: string;
  options: Record<string, string>;
  selected: string[];
  onToggle: (v: string) => void;
}> = ({ title, options, selected, onToggle }) => (
  <div className="space-y-1">
    <div className="text-[10px] uppercase tracking-wider font-bold text-gray-500">{title}</div>
    <div className="flex flex-wrap gap-1">
      {Object.entries(options).map(([value, label]) => {
        const on = selected.includes(value);
        return (
          <button
            key={value}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(value)}
            className={`px-2 py-0.5 rounded border text-[11px] ${
              on ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-200' : 'border-borderMuted text-gray-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  </div>
);

/** Presets + advanced multi-indicator filter panel for the screener. */
export const ScreenerFilters: React.FC<Props> = ({ criteria, onChange, activePreset, onPreset, matched, total }) => {
  const [open, setOpen] = useState(false);
  const chips = activeChips(criteria);
  const groups = Array.from(new Set(RANGE_DEFS.map((d) => d.group)));

  const setRange = (key: RangeKey, side: 'min' | 'max', raw: string) => {
    const ranges = { ...criteria.ranges };
    const cur = { ...(ranges[key] ?? {}) };
    const v = raw.trim() === '' ? undefined : Number(raw.replace(',', '.'));
    if (v === undefined || Number.isNaN(v)) delete cur[side];
    else cur[side] = v;
    if (cur.min === undefined && cur.max === undefined) delete ranges[key];
    else ranges[key] = cur;
    onPreset(null);
    onChange({ ...criteria, ranges });
  };

  const edit = (c: Criteria) => {
    onPreset(null);
    onChange(c);
  };

  const preset = PRESETS.find((p) => p.id === activePreset);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 bg-surface p-1 rounded-xl border border-borderMuted">
        <button
          type="button"
          onClick={() => {
            onPreset(null);
            onChange(EMPTY_CRITERIA);
          }}
          aria-pressed={isEmpty(criteria)}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
            isEmpty(criteria) ? 'bg-emerald-500 text-black font-bold' : 'text-gray-400 hover:text-white hover:bg-surfaceHover'
          }`}
        >
          Semua Saham
        </button>
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            title={p.description}
            aria-pressed={activePreset === p.id}
            onClick={() => {
              onPreset(p.id);
              onChange(p.criteria);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
              activePreset === p.id ? 'bg-emerald-500 text-black font-bold' : 'text-gray-400 hover:text-white hover:bg-surfaceHover'
            }`}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={`ml-auto px-3 py-1.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 ${
            open ? 'bg-slate-700 text-white' : 'text-gray-300 hover:text-white hover:bg-surfaceHover'
          }`}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" /> Filter Lanjutan
        </button>
      </div>

      {preset && <p className="text-[11px] text-gray-400">{preset.description} Filter ini menyaring kondisi, bukan memprediksi harga.</p>}

      {(chips.length > 0 || !isEmpty(criteria)) && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-mono text-gray-300">
            {matched} dari {total} saham lolos
          </span>
          {chips.map((ch) => (
            <button
              key={ch.id}
              type="button"
              onClick={() => edit(ch.clear(criteria))}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-[11px] text-emerald-200 hover:bg-emerald-500/20"
              title="Hapus kriteria ini"
            >
              {ch.label} <X className="w-3 h-3" />
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              onPreset(null);
              onChange(EMPTY_CRITERIA);
            }}
            className="inline-flex items-center gap-1 text-[11px] text-gray-400 hover:text-white"
          >
            <RotateCcw className="w-3 h-3" /> Reset
          </button>
        </div>
      )}

      {open && (
        <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            {groups.map((g) => (
              <div key={g} className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wider font-bold text-gray-500">{g}</div>
                {RANGE_DEFS.filter((d) => d.group === g).map((d) => {
                  const r = criteria.ranges[d.key] ?? {};
                  return (
                    <div key={d.key} className="flex items-center gap-1.5 text-[11px]">
                      <span className="flex-1 text-gray-300 truncate" title={d.label}>
                        {d.label}
                        {d.unit ? <span className="text-gray-500"> ({d.unit})</span> : null}
                      </span>
                      <input
                        type="number"
                        step={d.step}
                        inputMode="decimal"
                        aria-label={`${d.label} minimum`}
                        placeholder="min"
                        value={r.min ?? ''}
                        onChange={(e) => setRange(d.key, 'min', e.target.value)}
                        className="w-16 bg-surface border border-borderMuted rounded px-1.5 py-0.5 text-white font-mono focus:outline-none focus:border-emerald-500"
                      />
                      <input
                        type="number"
                        step={d.step}
                        inputMode="decimal"
                        aria-label={`${d.label} maksimum`}
                        placeholder="max"
                        value={r.max ?? ''}
                        onChange={(e) => setRange(d.key, 'max', e.target.value)}
                        className="w-16 bg-surface border border-borderMuted rounded px-1.5 py-0.5 text-white font-mono focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <ChoiceGroup
              title="Status pullback"
              options={PULLBACK_STATE_LABELS}
              selected={criteria.pullbackStates}
              onToggle={(v) => edit({ ...criteria, pullbackStates: toggle(criteria.pullbackStates, v) })}
            />
            <ChoiceGroup
              title="Aliran dana"
              options={FLOW_LABELS}
              selected={criteria.flowStatuses}
              onToggle={(v) => edit({ ...criteria, flowStatuses: toggle(criteria.flowStatuses, v) })}
            />
            <div className="space-y-2">
              <ChoiceGroup
                title="Fundamental"
                options={HEALTH_LABELS}
                selected={criteria.healthGrades}
                onToggle={(v) => edit({ ...criteria, healthGrades: toggle(criteria.healthGrades, v) })}
              />
              <label className="flex items-center gap-2 text-[11px] text-gray-300">
                <input
                  type="checkbox"
                  checked={criteria.hideSpeculative}
                  onChange={(e) => edit({ ...criteria, hideSpeculative: e.target.checked })}
                />
                Sembunyikan saham spekulatif
              </label>
              <label className="flex items-center gap-2 text-[11px] text-gray-300">
                <input
                  type="checkbox"
                  checked={criteria.hideIlliquid}
                  onChange={(e) => edit({ ...criteria, hideIlliquid: e.target.checked })}
                />
                Hanya saham likuid (≥ Rp1 miliar/hari)
              </label>
            </div>
          </div>
          <p className="text-[10px] text-gray-500">
            Saham tanpa data untuk suatu kriteria (mis. PER kosong) tidak lolos kriteria itu. Semua angka dari scan terakhir.
          </p>
        </div>
      )}
    </div>
  );
};
