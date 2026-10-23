import React from 'react';
import { Activity } from 'lucide-react';
import type { FlowSummary, TradeLevels } from '../types/stock';

const fmt = (v?: number | null) =>
  v === undefined || v === null ? '-' : v.toLocaleString('id-ID', { maximumFractionDigits: 2 });

const PRESSURE_CLS: Record<string, string> = {
  BELI: 'text-emerald-300',
  JUAL: 'text-rose-300',
  SEIMBANG: 'text-gray-200',
};

/** Shown instead of the broker summary when no broker data source is configured. */
export const FlowSummaryCard: React.FC<{ data?: FlowSummary | null }> = ({ data }) => {
  if (!data || !data.available) return null;
  const big = data.biggest_volume_day;
  return (
    <div className="p-4 rounded-xl bg-[#090D16] border border-borderMuted space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-400">
          <Activity className="w-4 h-4" />
          <span>Ringkasan Aliran Dana (20 Hari)</span>
        </div>
        <span className="text-[10px] text-gray-500">{data.disclaimer}</span>
      </div>
      <p className={`text-sm font-semibold ${PRESSURE_CLS[data.pressure] ?? 'text-gray-200'}`}>{data.pressure_label}</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Rasio volume naik : turun</div>
          <div className="font-mono font-bold text-white">{data.up_down_volume_ratio !== null ? `${fmt(data.up_down_volume_ratio)} : 1` : 'hanya hari naik'}</div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Hari naik / turun</div>
          <div className="font-mono font-bold text-white">
            {data.up_days} / {data.down_days}
          </div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Chaikin Money Flow</div>
          <div className={`font-mono font-bold ${data.cmf20 >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
            {data.cmf20 > 0 ? '+' : ''}
            {fmt(data.cmf20)}
          </div>
        </div>
        <div className="p-2 rounded-lg bg-surface border border-borderMuted">
          <div className="text-gray-400">Volume terbesar</div>
          <div className="font-mono font-bold text-white">
            {big.date} · {big.direction === 'NAIK' ? '▲' : big.direction === 'TURUN' ? '▼' : '•'} {fmt(big.volume_x_avg)}×
          </div>
        </div>
      </div>
      {data.vsa_label && <p className="text-[11px] text-gray-400">Pola volume terakhir: {data.vsa_label}</p>}
      <p className="text-[10px] text-gray-500">
        Data broker (siapa yang membeli/menjual) belum tersedia. Bisa diaktifkan dengan API key Sectors.app di Pengaturan
        (opsional).
      </p>
    </div>
  );
};

const FLAG_TEXT: Record<string, string> = {
  tight_room: 'Ruang naik sempit — resistance dekat (R:R < 1,2)',
  wide_stop: 'Support jauh — cut loss dibatasi 8%',
  market_entry: 'Tidak ada support dekat — entry di harga pasar',
  projected_tp1: 'TP1 proyeksi (belum ada resistance tercatat di atas)',
  too_volatile: 'Terlalu volatil — cut loss 8% masih di dalam gerak harian normal (ATR)',
  narrow_zone: 'Zona beli sangat sempit — harga beli praktis sama dengan harga pasar',
};

const fmtDay = (d: string) => {
  const date = new Date(`${d.slice(0, 10)}T00:00:00`);
  return isNaN(date.getTime())
    ? d
    : date.toLocaleDateString('id-ID', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};

const fmtTime = (iso?: string | null) => {
  const date = iso ? new Date(iso) : null;
  return date && !isNaN(date.getTime()) ? date.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : null;
};

/** Which daily close the levels stand on, and whether that session had already ended. */
export const POSITION_CLS: Record<string, string> = {
  BELOW_STOP: 'text-rose-300',
  TESTING_SUPPORT: 'text-sky-300',
  IN_ZONE: 'text-emerald-300',
  ABOVE_ZONE: 'text-amber-300',
  AT_TP1: 'text-emerald-200',
  AT_TP2: 'text-emerald-200',
};

const PriceBasis: React.FC<{ levels: TradeLevels; compact?: boolean }> = ({ levels, compact }) => {
  if (!levels.as_of) return null;
  const day = fmtDay(levels.as_of);
  if (levels.frozen && levels.live) {
    const live = levels.live;
    return (
      <>
        {!compact && (
          <div className="text-gray-300">
            📌 Rencana, skor & indikator dari penutupan {day} (final) — dikunci selama sesi hari ini; harga dan posisi
            di bawah ini mengikuti pasar (tertunda ±15 menit).
          </div>
        )}
        <div className={`${POSITION_CLS[live.status] ?? 'text-gray-300'} ${compact ? 'font-semibold' : ''}`}>
          Harga sekarang {fmt(live.price)}: {live.label}
          {live.touched_stop && live.status !== 'BELOW_STOP' ? ` · hari ini sempat menyentuh cut loss ${fmt(levels.stop_loss)}` : ''}
          {live.touched_tp1 && live.status !== 'AT_TP1' && live.status !== 'AT_TP2' ? ` · hari ini sempat menyentuh TP1 ${fmt(levels.target_tp1)}` : ''}
        </div>
      </>
    );
  }
  if (levels.bar_final === false) {
    const at = fmtTime(levels.computed_at);
    return (
      <div className="text-sky-300">
        ⏳ Dihitung{at ? ` pukul ${at}` : ''} saat sesi {day} masih berjalan — harga belum final, level bisa berubah.
        Scan ulang setelah bursa tutup.
      </div>
    );
  }
  return (
    <div className="text-gray-300">
      📅 {compact ? `Rencana dari penutupan ${day} — untuk sesi bursa berikutnya.` : `Dasar harga: penutupan ${day} (final) — rencana untuk sesi bursa berikutnya.`}
    </div>
  );
};

/** From where the price is now: how far it must dip to fill the limit, and room left to TP1. */
const FromNow: React.FC<{ levels: TradeLevels }> = ({ levels }) => {
  const now = levels.live?.price ?? levels.price;
  if (!now || !(levels.recommended_entry > 0) || !(levels.target_tp1 > 0)) return null;
  const pct = (v: number) => {
    const p = (v / now - 1) * 100;
    return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toLocaleString('id-ID', { maximumFractionDigits: 1 })}%`;
  };
  const room = levels.target_tp1 / now - 1;
  return (
    <div className="font-mono">
      <span className="text-gray-400 font-sans">Dari harga sekarang {fmt(now)}:</span> harga beli{' '}
      {pct(levels.recommended_entry)} · TP1 <span className={room <= 0 ? 'text-amber-300' : ''}>{pct(levels.target_tp1)}</span>
      {room <= 0 && <span className="font-sans text-amber-300"> — target sudah tercapai di harga sekarang</span>}
    </div>
  );
};

const Flags: React.FC<{ levels: TradeLevels }> = ({ levels }) =>
  levels.flags?.length > 0 ? (
    <ul className="text-amber-300 space-y-0.5">
      {levels.flags.map((f) => (
        <li key={f}>⚠ {FLAG_TEXT[f] ?? f}</li>
      ))}
    </ul>
  ) : null;

/** The few lines a card shows under the plan box: where the price is vs the plan, and warnings. */
export const PlanNow: React.FC<{ levels?: TradeLevels | null }> = ({ levels }) => {
  if (!levels) return null;
  return (
    <div className="text-[11px] text-gray-300 space-y-0.5" onClick={(e) => e.stopPropagation()}>
      <PriceBasis levels={levels} compact />
      <FromNow levels={levels} />
      <Flags levels={levels} />
    </div>
  );
};

/** What to do depending on where the price opens / trades relative to the plan. */
const OpenPlan: React.FC<{ levels: TradeLevels; compact?: boolean }> = ({ levels, compact }) => {
  const { entry_low, entry_high, stop_loss, tick } = levels;
  const rules = [
    {
      cls: 'text-amber-300',
      when: `Di atas ${fmt(entry_high)}`,
      then: 'Jangan dikejar — tunggu turun ke zona beli, atau lewati saham ini.',
    },
    {
      cls: 'text-emerald-300',
      when: `Di zona ${fmt(entry_low)}–${fmt(entry_high)}`,
      then: `Sesuai rencana${levels.recommended_entry > 0 ? ` — order beli limit di ${fmt(levels.recommended_entry)}` : ''}. Pasang cut loss ${fmt(stop_loss)} sejak awal.`,
    },
    // Only when there is real room between the stop and the entry zone
    ...(entry_low - stop_loss > (tick || 0)
      ? [
          {
            cls: 'text-sky-300',
            when: `Antara ${fmt(stop_loss)} dan ${fmt(entry_low)}`,
            then: 'Support sedang diuji — masuk hanya jika harga berbalik naik kembali ke zona beli.',
          },
        ]
      : []),
    {
      cls: 'text-rose-300',
      when: `Di bawah ${fmt(stop_loss)}`,
      then: 'Rencana batal — support sudah jebol. Jika sudah punya posisi, jalankan cut loss.',
    },
  ];
  return (
    <details open={!compact} className="rounded-md border border-borderMuted bg-[#090D16]/60 px-2 py-1 mt-1">
      <summary className="cursor-pointer text-gray-300 font-semibold select-none">
        Panduan saat bursa buka{levels.market !== 'US' ? ' (pagi & sesi 2)' : ''}
      </summary>
      <ul className="mt-1 space-y-0.5">
        {rules.map((r) => (
          <li key={r.when}>
            <span className={`font-mono font-semibold ${r.cls}`}>{r.when}:</span> {r.then}
          </li>
        ))}
      </ul>
      <p className="text-gray-400 mt-1">
        Harga bisa langsung melompat (gap) saat pembukaan — cek harga pembukaan dulu sebelum memasang order.
        {levels.market !== 'US' &&
          ' Begitu juga setelah jeda siang: berita selama istirahat bisa membuat sesi 2 dibuka jauh dari harga akhir sesi 1.'}
      </p>
    </details>
  );
};

/** Where each level comes from, plus risk per lot and warnings. `withNow={false}` when the card
 *  already shows PlanNow above it. */
export const LevelBasis: React.FC<{ levels?: TradeLevels | null; compact?: boolean; withNow?: boolean }> = ({
  levels,
  compact,
  withNow = true,
}) => {
  if (!levels) return null;
  return (
    <div className={`text-[11px] text-gray-400 space-y-0.5 ${compact ? '' : 'pt-1'}`} onClick={(e) => e.stopPropagation()}>
      {withNow && <PriceBasis levels={levels} />}
      {withNow && levels.recommended_entry > 0 && (
        <div className="font-mono text-cyan-300/90">
          Harga beli (limit) {fmt(levels.recommended_entry)}
          <span className="font-sans text-gray-400">
            {' '}· di zona beli {fmt(levels.entry_low)}–{fmt(levels.entry_high)}; uji historis mengasumsikan order beli limit di harga ini
          </span>
        </div>
      )}
      <div>
        <span className="text-gray-400">Dasar harga beli:</span> {levels.entry_basis} ·{' '}
        <span className="text-gray-400">Cut loss:</span> {levels.stop_basis}
      </div>
      <div>
        <span className="text-gray-400">TP1:</span> {levels.tp1_basis} · <span className="text-gray-400">TP2:</span> {levels.tp2_basis}
      </div>
      {withNow && <FromNow levels={levels} />}
      <div className="font-mono">
        Risiko {fmt(levels.risk_pct)}% · Potensi ke TP1 {fmt(levels.reward_pct)}%
        {levels.risk_per_lot ? ` · Risiko per lot (100 lembar) ≈ Rp${fmt(levels.risk_per_lot)}` : ''} · Fraksi harga {fmt(levels.tick)}
      </div>
      {withNow && <Flags levels={levels} />}
      <OpenPlan levels={levels} compact={compact} />
    </div>
  );
};
