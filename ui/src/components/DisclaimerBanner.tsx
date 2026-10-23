import React, { useState } from 'react';
import { Info, X } from 'lucide-react';
import { GlossaryHost } from './help/GlossaryDrawer';
import { openGlossary } from './help/glossaryBus';

const STORAGE_KEY = 'saham.disclaimer.dismissed';

const readDismissed = () => {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
};

/**
 * Understanding: "bukan nasihat investasi" disclaimer (mounted in App).
 * Bisa ditutup per sesi. Juga memasang GlossaryHost (pendengar global glosarium).
 */
export const DisclaimerBanner: React.FC = () => {
  const [dismissed, setDismissed] = useState<boolean>(readDismissed);

  const dismiss = () => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* storage tidak tersedia — cukup sembunyikan untuk render ini */
    }
  };

  return (
    <>
      <GlossaryHost />
      {!dismissed && (
        <div
          role="note"
          aria-label="Penafian"
          className="mt-6 flex items-start gap-2 px-3 py-2 rounded-lg border border-borderMuted bg-surface/60 text-[11px] text-gray-400 leading-relaxed"
        >
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-500" aria-hidden="true" />
          <p className="flex-1">
            SAHAM adalah alat bantu analisis, <span className="text-gray-200 font-semibold">bukan nasihat investasi</span>.
            Sinyal dan skor dihitung dari data masa lalu dan akurasi historisnya terbatas — keputusan dan risiko
            sepenuhnya milik Anda.{' '}
            <button
              type="button"
              onClick={() => openGlossary()}
              className="text-cyan-300 hover:text-cyan-200 underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
            >
              Pelajari istilah
            </button>
          </p>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Tutup penafian untuk sesi ini"
            title="Sembunyikan untuk sesi ini"
            className="p-1 rounded text-gray-500 hover:text-white hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </>
  );
};
