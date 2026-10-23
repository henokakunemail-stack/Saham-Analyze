import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import { getTerm } from '../../lib/glossary';
import { openGlossary } from './glossaryBus';

interface Props {
  /** Key di lib/glossary.ts. */
  term?: string;
  /** Konten kustom (dipakai bila tidak ada `term`, atau ditambahkan di bawahnya). */
  children?: React.ReactNode;
  /** Label aksesibel tombol; default "Penjelasan <istilah>". */
  label?: string;
  className?: string;
  iconClassName?: string;
}

const TIP_WIDTH = 288;
const GAP = 6;

/**
 * Ikon (i) kecil yang menampilkan penjelasan istilah.
 * - Hover (mouse), fokus keyboard, dan klik/tap (touch) membuka tooltip.
 * - Esc menutup. Klik di luar menutup.
 * - Dirender lewat portal + posisi fixed, jadi tidak terpotong container overflow.
 */
export const InfoTip: React.FC<Props> = ({ term, children, label, className = '', iconClassName = 'w-3 h-3' }) => {
  const entry = term ? getTerm(term) : undefined;
  const id = useId();
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; placement: 'top' | 'bottom' }>({
    top: -9999,
    left: -9999,
    placement: 'bottom',
  });

  const place = useCallback(() => {
    const btn = btnRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const tipH = tipRef.current?.offsetHeight ?? 160;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = Math.min(TIP_WIDTH, vw - 16);
    let left = r.left + r.width / 2 - width / 2;
    left = Math.max(8, Math.min(left, vw - width - 8));
    const below = r.bottom + GAP;
    const fitsBelow = below + tipH <= vh - 8;
    const placement = fitsBelow || r.top < tipH + GAP ? 'bottom' : 'top';
    const top = placement === 'bottom' ? below : r.top - GAP - tipH;
    setPos({ top: Math.max(8, top), left, placement });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => place();
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || tipRef.current?.contains(t)) return;
      setOpen(false);
      setPinned(false);
    };
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    document.addEventListener('pointerdown', onDown);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
      document.removeEventListener('pointerdown', onDown);
    };
  }, [open, place]);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  if (!entry && !children) return null;

  const show = () => {
    window.clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleHide = () => {
    if (pinned) return;
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  };
  const close = () => {
    setOpen(false);
    setPinned(false);
  };

  const ariaLabel = label ?? `Penjelasan ${entry?.term ?? 'istilah'}`;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        className={`inline-flex items-center justify-center align-middle rounded-full text-gray-500 hover:text-cyan-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 focus-visible:text-cyan-300 transition-colors ${className}`}
        onPointerEnter={(e) => e.pointerType === 'mouse' && show()}
        onPointerLeave={(e) => e.pointerType === 'mouse' && scheduleHide()}
        onFocus={show}
        onBlur={(e) => {
          if (tipRef.current?.contains(e.relatedTarget as Node)) return;
          scheduleHide();
        }}
        onClick={(e) => {
          // Jangan memicu sort header / klik baris tabel
          e.stopPropagation();
          e.preventDefault();
          if (pinned) close();
          else {
            setPinned(true);
            show();
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && open) {
            e.stopPropagation();
            close();
          }
        }}
      >
        <Info className={iconClassName} aria-hidden="true" />
      </button>
      {open &&
        createPortal(
          <div
            ref={tipRef}
            id={id}
            role="tooltip"
            onPointerEnter={show}
            onPointerLeave={scheduleHide}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation();
                close();
                btnRef.current?.focus();
              }
            }}
            style={{ position: 'fixed', top: pos.top, left: pos.left, width: Math.min(TIP_WIDTH, window.innerWidth - 16), zIndex: 1000 }}
            className="rounded-lg border border-slate-600 bg-[#0B1220] shadow-2xl p-3 text-[11px] leading-relaxed text-gray-300 normal-case tracking-normal font-sans font-normal text-left"
          >
            {entry && (
              <div className="space-y-1.5">
                <div className="text-xs font-bold text-white">{entry.term}</div>
                <p>{entry.what}</p>
                <p>
                  <span className="text-cyan-300 font-semibold">Cara baca: </span>
                  {entry.read}
                </p>
                {entry.thresholds && (
                  <p>
                    <span className="text-cyan-300 font-semibold">Ambang: </span>
                    {entry.thresholds}
                  </p>
                )}
                {entry.caution && (
                  <p className="text-amber-200/90">
                    <span className="font-semibold">⚠ Perhatian: </span>
                    {entry.caution}
                  </p>
                )}
              </div>
            )}
            {children && <div className={entry ? 'mt-2 pt-2 border-t border-slate-700' : ''}>{children}</div>}
            {entry && (
              <button
                type="button"
                className="mt-2 text-[11px] font-semibold text-cyan-300 hover:text-cyan-200 underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
                onClick={(e) => {
                  e.stopPropagation();
                  close();
                  openGlossary(entry.key);
                }}
              >
                Buka di glosarium →
              </button>
            )}
          </div>,
          document.body
        )}
    </>
  );
};
