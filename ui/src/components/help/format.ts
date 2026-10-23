/** Formatter angka konsisten (locale id-ID: titik = ribuan, koma = desimal). */

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Angka biasa, mis. 1.234,5. */
export const fmtNum = (v?: number | null, maxDigits = 2, minDigits = 0): string =>
  isNum(v) ? v.toLocaleString('id-ID', { maximumFractionDigits: maxDigits, minimumFractionDigits: minDigits }) : '-';

/** Harga: tanpa desimal untuk harga ≥ 1.000, 2 desimal di bawahnya (saham US / IDX murah). */
export const fmtPrice = (v?: number | null): string => {
  if (!isNum(v)) return '-';
  return fmtNum(v, Math.abs(v) >= 1000 ? 0 : 2);
};

/** Angka bertanda, mis. +0,12 / −0,05 (tanda tidak hanya lewat warna). */
export const fmtSigned = (v?: number | null, digits = 2): string => {
  if (!isNum(v)) return '-';
  const s = fmtNum(Math.abs(v), digits, digits);
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
};

/** Persen bertanda, mis. +2,35%. */
export const fmtPct = (v?: number | null, digits = 2): string => (isNum(v) ? `${fmtSigned(v, digits)}%` : '-');

/** Bilangan bulat bertanda, mis. +45 / −20. */
export const fmtSignedInt = (v?: number | null): string => (isNum(v) ? fmtSigned(Math.round(v), 0) : '-');
