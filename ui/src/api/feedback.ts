/** Speed & Feedback API: API error event bus, fetch helper with timeouts, scan progress. */
import { API_BASE } from './base';
import { ApiErrorEvent, ApiErrorKind, ScanProgress } from '../types/feedback';

type ApiErrorListener = (e: ApiErrorEvent) => void;
const listeners = new Set<ApiErrorListener>();

/** Subscribe to API failures. Returns an unsubscribe function. */
export function onApiError(listener: ApiErrorListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitApiError(e: ApiErrorEvent): void {
  console.error(`[api:${e.op}] ${e.title}: ${e.message}`);
  listeners.forEach((l) => {
    try {
      l(e);
    } catch {
      /* a broken listener must not break the API call */
    }
  });
}

/** Timeouts (ms). A full forced scan can take several minutes. */
export const TIMEOUT = {
  short: 4000,
  normal: 15000,
  slow: 60000,
  ai: 120000,
  scan: 10 * 60 * 1000,
} as const;

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

function describeHttp(status: number, detail?: string): string {
  if (detail) return detail;
  if (status === 404) return 'Data tidak ditemukan.';
  if (status === 429) return 'Terlalu banyak permintaan, coba beberapa saat lagi.';
  if (status >= 500) return `Engine mengalami kesalahan (HTTP ${status}).`;
  return `Permintaan ditolak (HTTP ${status}).`;
}

function toApiError(e: unknown, timeoutMs: number): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof SyntaxError) return new ApiError('http', 'Respons engine tidak valid.');
  const name = (e as { name?: string })?.name;
  if (name === 'TimeoutError' || name === 'AbortError') {
    return new ApiError('timeout', `Engine tidak merespons dalam ${Math.round(timeoutMs / 1000)} detik.`);
  }
  return new ApiError('network', 'Tidak dapat terhubung ke engine analitik.');
}

export interface RequestOptions extends RequestInit {
  timeout?: number;
  /** Event op id + title; omit to fail silently (no event). */
  op?: string;
  title?: string;
}

/** fetch + timeout + JSON. Throws ApiError and (when op/title given) emits an ApiErrorEvent. */
export async function requestJson<T>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { timeout = TIMEOUT.normal, op, title, ...init } = opts;
  try {
    const res = await fetch(url, { ...init, signal: init.signal ?? AbortSignal.timeout(timeout) });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const body = await res.json();
        if (typeof body?.detail === 'string') detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError('http', describeHttp(res.status, detail), res.status);
    }
    const text = await res.text();
    return (text ? JSON.parse(text) : null) as T;
  } catch (e) {
    const err = toApiError(e, timeout);
    if (op && title) emitApiError({ op, title, message: err.message, kind: err.kind, status: err.status });
    throw err;
  }
}

export const feedbackApi = {
  base: API_BASE,

  /** Live scan progress; null when unreachable (connection state is handled by the health check). */
  async getScanProgress(includeResults: boolean = true): Promise<ScanProgress | null> {
    try {
      return await requestJson<ScanProgress>(
        `${API_BASE}/screener/progress?include_results=${includeResults}`,
        { timeout: TIMEOUT.short }
      );
    } catch {
      return null;
    }
  },
};
