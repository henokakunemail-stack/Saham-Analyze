import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { X, CheckCircle2, AlertTriangle, Info, XCircle } from 'lucide-react';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

export interface ToastOptions {
  kind?: ToastKind;
  title: string;
  message?: string;
  /** ms before auto-dismiss; 0 keeps it until closed. Default 5000 (errors 8000). */
  duration?: number;
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastOptions {
  id: number;
}

interface ToastApi {
  show: (opts: ToastOptions) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const STYLES: Record<ToastKind, { box: string; Icon: React.FC<{ className?: string }> }> = {
  success: { box: 'border-emerald-500/40 bg-emerald-950/90 text-emerald-100', Icon: CheckCircle2 },
  error: { box: 'border-rose-500/40 bg-rose-950/90 text-rose-100', Icon: XCircle },
  warning: { box: 'border-amber-500/40 bg-amber-950/90 text-amber-100', Icon: AlertTriangle },
  info: { box: 'border-sky-500/40 bg-slate-900/95 text-sky-100', Icon: Info },
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (opts: ToastOptions) => {
      const id = nextId.current++;
      const kind = opts.kind ?? 'info';
      // Collapse identical messages that are already on screen
      setToasts((prev) =>
        prev.some((t) => t.title === opts.title && t.message === opts.message)
          ? prev
          : [...prev.slice(-4), { ...opts, kind, id }]
      );
      const duration = opts.duration ?? (kind === 'error' ? 8000 : 5000);
      if (duration > 0) window.setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss]
  );

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]" role="status" aria-live="polite">
        {toasts.map((t) => {
          const { box, Icon } = STYLES[t.kind ?? 'info'];
          return (
            <div key={t.id} className={`rounded-xl border px-3 py-2.5 shadow-2xl backdrop-blur text-xs flex gap-2 ${box}`}>
              <Icon className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="font-bold">{t.title}</div>
                {t.message && <div className="opacity-80 mt-0.5 break-words">{t.message}</div>}
                {t.action && (
                  <button
                    onClick={() => {
                      t.action!.onClick();
                      dismiss(t.id);
                    }}
                    className="mt-1.5 font-semibold underline underline-offset-2"
                  >
                    {t.action.label}
                  </button>
                )}
              </div>
              <button onClick={() => dismiss(t.id)} className="opacity-60 hover:opacity-100 h-fit" aria-label="Tutup">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastApi => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
};
