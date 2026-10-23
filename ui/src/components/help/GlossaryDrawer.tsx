import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, Search, X } from 'lucide-react';
import { GLOSSARY_CATEGORIES, GlossaryEntry, searchGlossary } from '../../lib/glossary';
import { OPEN_GLOSSARY_EVENT, OpenGlossaryDetail, openGlossary } from './glossaryBus';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Istilah yang disorot & di-scroll saat dibuka. */
  focusTerm?: string;
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

const EntryCard: React.FC<{ e: GlossaryEntry; highlight: boolean }> = ({ e, highlight }) => (
  <article
    id={`glossary-${e.key}`}
    className={`p-3 rounded-lg border text-[12px] leading-relaxed space-y-1 scroll-mt-24 ${
      highlight ? 'border-cyan-400/70 bg-cyan-500/10' : 'border-borderMuted bg-surface'
    }`}
  >
    <h4 className="text-xs font-bold text-white">{e.term}</h4>
    <p className="text-gray-300">{e.what}</p>
    <p className="text-gray-300">
      <span className="text-cyan-300 font-semibold">Cara baca: </span>
      {e.read}
    </p>
    {e.thresholds && (
      <p className="text-gray-300">
        <span className="text-cyan-300 font-semibold">Ambang: </span>
        {e.thresholds}
      </p>
    )}
    {e.caution && (
      <p className="text-amber-200/90">
        <span className="font-semibold">⚠ Perhatian: </span>
        {e.caution}
      </p>
    )}
  </article>
);

/** Panel samping berisi semua istilah, dengan pencarian. */
export const GlossaryDrawer: React.FC<DrawerProps> = ({ open, onClose, focusTerm }) => {
  const [query, setQuery] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  const results = useMemo(() => searchGlossary(query), [query]);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    setQuery('');
    // Esc ditangkap di fase capture agar tidak ikut menutup modal di bawahnya
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      restoreRef.current?.focus?.();
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      if (focusTerm) {
        const el = document.getElementById(`glossary-${focusTerm}`);
        el?.scrollIntoView({ block: 'start' });
      }
      inputRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, focusTerm]);

  if (!open) return null;

  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;
    const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (n) => !n.hasAttribute('disabled')
    );
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[900] flex justify-end" onKeyDown={trapTab}>
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="glossary-title"
        className="relative w-full max-w-md h-full bg-[#0B1220] border-l border-borderMuted shadow-2xl flex flex-col"
      >
        <div className="p-4 border-b border-borderMuted space-y-3">
          <div className="flex items-center justify-between">
            <h2 id="glossary-title" className="flex items-center gap-2 text-sm font-bold text-white">
              <BookOpen className="w-4 h-4 text-cyan-400" aria-hidden="true" />
              Glosarium Istilah
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Tutup glosarium"
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <label className="relative block">
            <span className="sr-only">Cari istilah</span>
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" aria-hidden="true" />
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cari: RSI, CMF, stop loss, gorengan…"
              className="w-full bg-surface border border-borderMuted rounded-lg pl-8 pr-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </label>
          <p className="text-[11px] text-gray-500">
            Penjelasan ini bersifat edukatif. Semua indikator membaca data masa lalu dan tidak menjamin arah harga.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5" aria-live="polite">
          {results.length === 0 && <p className="text-xs text-gray-400">Tidak ada istilah yang cocok dengan "{query}".</p>}
          {GLOSSARY_CATEGORIES.map((cat) => {
            const items = results.filter((r) => r.category === cat);
            if (items.length === 0) return null;
            return (
              <section key={cat} className="space-y-2">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{cat}</h3>
                {items.map((e) => (
                  <EntryCard key={e.key} e={e} highlight={e.key === focusTerm} />
                ))}
              </section>
            );
          })}
        </div>
      </div>
    </div>,
    document.body
  );
};

/**
 * Pendengar global: membuka GlossaryDrawer saat `openGlossary()` dipanggil.
 * Pasang SEKALI di aplikasi (saat ini dipasang oleh DisclaimerBanner).
 */
export const GlossaryHost: React.FC = () => {
  const [state, setState] = useState<{ open: boolean; term?: string }>({ open: false });
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<OpenGlossaryDetail>).detail;
      setState({ open: true, term: detail?.term });
    };
    window.addEventListener(OPEN_GLOSSARY_EVENT, handler);
    return () => window.removeEventListener(OPEN_GLOSSARY_EVENT, handler);
  }, []);
  const close = React.useCallback(() => setState({ open: false }), []);
  return <GlossaryDrawer open={state.open} focusTerm={state.term} onClose={close} />;
};

/** Tombol "Glosarium" kecil. */
export const GlossaryButton: React.FC<{ className?: string; compact?: boolean }> = ({ className = '', compact }) => (
  <button
    type="button"
    onClick={(e) => {
      e.stopPropagation();
      openGlossary();
    }}
    className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-borderMuted bg-surface text-gray-300 hover:text-white hover:border-cyan-500/50 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 ${className}`}
    title="Buka glosarium istilah"
    aria-label="Buka glosarium istilah"
  >
    <BookOpen className="w-3.5 h-3.5 text-cyan-400" aria-hidden="true" />
    {!compact && <span>Glosarium</span>}
  </button>
);
