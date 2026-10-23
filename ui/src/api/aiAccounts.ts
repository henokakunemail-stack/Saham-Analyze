/** AI account sign-in: Anthropic login (official CLI) and accounts connected in 9router. */
import { API_BASE } from './base';
import { requestJson, TIMEOUT } from './feedback';

export interface AnthropicLoginStatus {
  cli_installed: boolean;
  cli_path: string | null;
  cli_version: string;
  installing: boolean;
  install_error: string | null;
  login_in_progress: boolean;
  login_url: string | null;
  api_key_env_set: boolean;
  logged_in: boolean | null;
  login_expired?: boolean;
  models_count?: number;
  message: string;
}

export interface RouterAccount {
  prefix: string;
  name: string;
  connected: boolean;
  models_count: number;
}

export interface RouterAccountsResponse {
  ok: boolean;
  accounts: RouterAccount[];
  dashboard_url: string;
  message: string;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

export const aiAccountsApi = {
  anthropicStatus(): Promise<AnthropicLoginStatus | null> {
    return safe(() => requestJson<AnthropicLoginStatus>(`${API_BASE}/ai/anthropic/login-status`, { timeout: TIMEOUT.slow }), null);
  },
  installAnthropicCli(): Promise<{ started: boolean; message: string }> {
    return safe(
      () => requestJson(`${API_BASE}/ai/anthropic/install-cli`, { method: 'POST', headers: JSON_HEADERS }),
      { started: false, message: 'Gagal memulai pemasangan Anthropic CLI.' }
    );
  },
  anthropicLogin(): Promise<{ ok: boolean; message: string }> {
    return safe(
      () => requestJson(`${API_BASE}/ai/anthropic/login`, { method: 'POST', headers: JSON_HEADERS }),
      { ok: false, message: 'Gagal memulai login.' }
    );
  },
  anthropicLogout(): Promise<{ ok: boolean; message: string }> {
    return safe(
      () => requestJson(`${API_BASE}/ai/anthropic/logout`, { method: 'POST', headers: JSON_HEADERS, timeout: TIMEOUT.slow }),
      { ok: false, message: 'Gagal logout.' }
    );
  },
  routerAccounts(baseUrl?: string): Promise<RouterAccountsResponse | null> {
    const q = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : '';
    return safe(() => requestJson<RouterAccountsResponse>(`${API_BASE}/ai/accounts${q}`, { timeout: TIMEOUT.slow }), null);
  },
  /** Opens a sign-in page in the default browser (server allows only local 9router / Anthropic Console). */
  openInBrowser(url: string): Promise<boolean> {
    return safe(async () => {
      await requestJson(`${API_BASE}/system/open-url`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ url }) });
      return true;
    }, false);
  },
};
