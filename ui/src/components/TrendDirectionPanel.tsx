import React from 'react';
import { Compass, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { ScorePillars, TrendDirectionData } from '../types/stock';
import { InfoTip } from './help/InfoTip';
import { DIRECTION_COMPONENT_TERM, pillarTermKey } from '../lib/glossary';
import { fmtNum, fmtPct, fmtPrice, fmtSigned, fmtSignedInt } from './help/format';

const COMPONENT_LABELS: Record<string, string> = {
  ema_structure: 'Struktur EMA',
  adx_dmi: 'ADX / DMI',
  regression: 'Regresi Linear',
  market_structure: 'Struktur Swing',
  momentum: 'Momentum',
  weekly: 'Tren Mingguan',
  relative_strength: 'Kekuatan vs Indeks',
};

const PILLAR_LABELS: Record<string, string> = {
  pullback: 'Pullback (Diskon)',
  trend: 'Arah Tren',
  money_flow: 'Aliran Uang',
  momentum: 'Momentum',
  setup: 'Kualitas Setup',
  fundamental: 'Fundamental',
  sentiment: 'Sentimen',
};

const REGIME_LABELS: Record<string, string> = {
  TRENDING_UP: 'Trending Naik',
  TRENDING_DOWN: 'Trending Turun',
  RANGING: 'Sideways / Ranging',
  SQUEEZE: 'Squeeze (volatilitas sempit)',
  UNKNOWN: '-',
};

const toneFor = (score: number) =>
  score >= 20 ? 'text-emerald-400' : score <= -20 ? 'text-rose-400' : 'text-gray-300';

/** Ikon arah agar arti tidak hanya bergantung pada warna. */
const arrowFor = (v: number, neutralBand = 0) => (v > neutralBand ? '▲' : v < -neutralBand ? '▼' : '■');

/** Compact direction pill used in the screener table. */
export const DirectionBadge: React.FC<{ score?: number; label?: string }> = ({ score, label }) => {
  if (score === undefined || score === null) {
    return <span className="text-gray-500 font-mono">-</span>;
  }
  const Icon = score >= 20 ? TrendingUp : score <= -20 ? TrendingDown : Minus;
  const cls =
    score >= 50
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      : score >= 20
      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
      : score <= -50
      ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
      : score <= -20
      ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
      : 'bg-slate-800 text-gray-300 border-slate-700';
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[11px] font-mono font-semibold whitespace-nowrap ${cls}`}
      title={label}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {fmtSignedInt(score)}
      {label && <span className="sr-only"> ({label})</span>}
    </span>
  );
};

/** Diverging bar for a value in [-1, 1]. */
const DivergingBar: React.FC<{ value: number }> = ({ value }) => {
  const v = Math.max(-1, Math.min(1, value));
  const width = `${Math.abs(v) * 50}%`;
  return (
    <div className="relative h-1.5 w-full rounded-full bg-slate-800 overflow-hidden" aria-hidden="true">
      <div className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
      <div
        className={`absolute top-0 h-full ${v >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}
        style={v >= 0 ? { left: '50%', width } : { right: '50%', width }}
      />
    </div>
  );
};

const SignedRow: React.FC<{ label: string; value: number; term?: string }> = ({ label, value, term }) => (
  <div className="space-y-0.5">
    <div className="flex justify-between items-center text-[11px]">
      <span className="text-gray-400 inline-flex items-center gap-1">
        {label}
        {term && <InfoTip term={term} />}
      </span>
      <span className={`font-mono ${value >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
        <span aria-hidden="true" className="text-[9px] mr-0.5">{arrowFor(value, 0.05)}</span>
        {fmtSigned(value, 2)}
      </span>
    </div>
    <DivergingBar value={value} />
  </div>
);

const Chip: React.FC<{ tone: 'up' | 'down' | 'flat'; term: string; children: React.ReactNode }> = ({ tone, term, children }) => {
  const cls =
    tone === 'up'
      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
      : tone === 'down'
      ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
      : 'bg-slate-800 text-gray-300 border-slate-700';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-semibold ${cls}`}>
      <span aria-hidden="true">{tone === 'up' ? '▲' : tone === 'down' ? '▼' : '■'}</span>
      {children}
      <InfoTip term={term} />
    </span>
  );
};

interface Props {
  direction: TrendDirectionData;
  marketRegime?: TrendDirectionData | null;
  pillars?: ScorePillars;
}

export const TrendDirectionPanel: React.FC<Props> = ({ direction, marketRegime, pillars }) => {
  const score = direction.direction_score;
  const markerLeft = `${((score + 100) / 200) * 100}%`;
  const bos = direction.break_of_structure;
  const weekly = direction.weekly_trend;
  const div = direction.rsi_divergence;
  const rs20 = direction.rs_20d_pct;

  return (
    <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-400">
          <Compass className="w-4 h-4" aria-hidden="true" />
          <span>Mesin Arah Tren (Multi-Faktor)</span>
          <InfoTip term="direction_score" />
        </div>
        {marketRegime && (
          <span className="text-[11px] text-gray-400 font-mono inline-flex items-center gap-1">
            Kondisi Indeks:{' '}
            <span className={`font-bold ${toneFor(marketRegime.direction_score)}`}>
              {arrowFor(marketRegime.direction_score, 19)} {marketRegime.direction_label} (
              {fmtSignedInt(marketRegime.direction_score)})
            </span>
            <InfoTip term="market_regime" />
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Headline */}
        <div className="space-y-3">
          <div>
            <div className={`text-2xl font-extrabold font-mono ${toneFor(score)}`}>
              <span aria-hidden="true" className="text-base mr-1">{arrowFor(score, 19)}</span>
              {fmtSignedInt(score)}
              <span className="text-xs text-gray-500 font-sans font-normal"> / 100</span>
            </div>
            <div className={`text-sm font-bold ${toneFor(score)}`}>{direction.direction_label}</div>
          </div>

          <div
            className="relative h-2 rounded-full bg-gradient-to-r from-rose-600 via-slate-600 to-emerald-500"
            role="img"
            aria-label={`Skor arah ${fmtSignedInt(score)} dari skala −100 (turun kuat) sampai +100 (naik kuat)`}
          >
            <div
              className="absolute -top-1 h-4 w-1 rounded bg-white shadow"
              style={{ left: markerLeft, transform: 'translateX(-50%)' }}
            />
          </div>
          <div className="flex justify-between text-[9px] text-gray-500 font-mono" aria-hidden="true">
            <span>TURUN KUAT</span>
            <span>NETRAL</span>
            <span>NAIK KUAT</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="p-2 rounded-lg bg-surface border border-borderMuted">
              <div className="text-gray-400 inline-flex items-center gap-1">
                Regime <InfoTip term="regime" />
              </div>
              <div className="font-bold text-white">{REGIME_LABELS[direction.regime] ?? direction.regime}</div>
            </div>
            <div className="p-2 rounded-lg bg-surface border border-borderMuted">
              <div className="text-gray-400 inline-flex items-center gap-1">
                Keyakinan <InfoTip term="confidence" />
              </div>
              <div className="font-bold text-white font-mono">{fmtNum(direction.confidence, 0)}%</div>
            </div>
            <div className="p-2 rounded-lg bg-surface border border-borderMuted">
              <div className="text-gray-400 inline-flex items-center gap-1">
                ADX (+DI / −DI) <InfoTip term="adx" />
              </div>
              <div className="font-bold text-white font-mono">
                {fmtNum(direction.adx, 1)} ({fmtNum(direction.plus_di, 1)} / {fmtNum(direction.minus_di, 1)})
              </div>
            </div>
            <div className="p-2 rounded-lg bg-surface border border-borderMuted">
              <div className="text-gray-400 inline-flex items-center gap-1">
                Swing H / L <InfoTip term="market_structure" />
              </div>
              <div className="font-bold text-white font-mono">
                {fmtPrice(direction.last_swing_high)} / {fmtPrice(direction.last_swing_low)}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {bos && bos !== 'NONE' && (
              <Chip tone={bos === 'BULLISH_BOS' ? 'up' : 'down'} term="break_of_structure">
                {bos === 'BULLISH_BOS' ? 'BOS naik' : 'BOS turun'}
              </Chip>
            )}
            {weekly && weekly !== 'N/A' && (
              <Chip
                tone={weekly.startsWith('UPTREND') ? 'up' : weekly.startsWith('DOWNTREND') ? 'down' : 'flat'}
                term="weekly_trend"
              >
                {weekly.charAt(0) + weekly.slice(1).toLowerCase()}
              </Chip>
            )}
            {div && div !== 'NONE' && (
              <Chip tone={div === 'BULLISH' ? 'up' : 'down'} term="rsi_divergence">
                Divergensi RSI {div === 'BULLISH' ? 'bullish' : 'bearish'}
              </Chip>
            )}
            {direction.pullback && direction.pullback.state !== 'INSUFFICIENT_DATA' && (
              <Chip
                tone={
                  direction.pullback.state === 'PULLBACK_IDEAL' || direction.pullback.state === 'UPTREND_RUNNING'
                    ? 'up'
                    : direction.pullback.state === 'TREND_BROKEN' || direction.pullback.state === 'NO_UPTREND'
                    ? 'down'
                    : 'flat'
                }
                term="pullback"
              >
                {direction.pullback.label}
              </Chip>
            )}
            {typeof direction.pullback?.long_momentum_pct === 'number' && (
              <Chip
                tone={direction.pullback.long_momentum_pct >= 10 ? 'up' : direction.pullback.long_momentum_pct <= -10 ? 'down' : 'flat'}
                term="long_momentum"
              >
                Mom. 6 bln {fmtPct(direction.pullback.long_momentum_pct, 1)}
              </Chip>
            )}
            {typeof direction.pullback?.relative_momentum_pct === 'number' && (
              <Chip
                tone={direction.pullback.relative_momentum_pct >= 5 ? 'up' : direction.pullback.relative_momentum_pct <= -5 ? 'down' : 'flat'}
                term="relative_momentum"
              >
                vs indeks {fmtPct(direction.pullback.relative_momentum_pct, 1)}
              </Chip>
            )}
            {direction.squeeze && (
              <Chip tone="flat" term="squeeze">
                Squeeze
              </Chip>
            )}
            {typeof rs20 === 'number' && (
              <Chip tone={rs20 >= 2 ? 'up' : rs20 <= -2 ? 'down' : 'flat'} term="relative_strength">
                RS 20h {fmtPct(rs20, 1)}
              </Chip>
            )}
          </div>
        </div>

        {/* Components */}
        <div className="space-y-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">Komponen Arah</div>
          {Object.entries(direction.components || {}).map(([key, val]) => (
            <SignedRow key={key} label={COMPONENT_LABELS[key] ?? key} value={val} term={DIRECTION_COMPONENT_TERM[key]} />
          ))}
        </div>

        {/* Pillars + notes */}
        <div className="space-y-3">
          {pillars && Object.keys(pillars).length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold inline-flex items-center gap-1">
                Pilar Skor Komposit <InfoTip term="composite_score" />
              </div>
              {Object.entries(pillars).map(([key, val]) => (
                <SignedRow key={key} label={PILLAR_LABELS[key] ?? key} value={val ?? 0} term={pillarTermKey(key)} />
              ))}
            </div>
          )}

          {direction.notes?.length > 0 && (
            <ul className="space-y-1 text-[11px] text-gray-300">
              {direction.notes.map((n, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-cyan-400" aria-hidden="true">•</span>
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};
