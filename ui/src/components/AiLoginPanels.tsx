import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, CheckCircle2, ExternalLink, LogIn, LogOut, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { aiAccountsApi, AnthropicLoginStatus, RouterAccountsResponse } from '../api/aiAccounts';

/** Sign in to Claude with an Anthropic Console account (official CLI, no API key to copy). */
export const ClaudeLoginPanel: React.FC<{ onLoggedIn?: () => void }> = ({ onLoggedIn }) => {
  const [status, setStatus] = useState<AnthropicLoginStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const loginAfterInstall = useRef(false);
  const wasLoggedIn = useRef<boolean | null>(null);

  const refresh = useCallback(async () => {
    const s = await aiAccountsApi.anthropicStatus();
    setStatus(s);
    if (s?.logged_in && wasLoggedIn.current === false) onLoggedIn?.();
    wasLoggedIn.current = s?.logged_in ?? null;
    return s;
  }, [onLoggedIn]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while something is in progress (CLI download or browser sign-in)
  useEffect(() => {
    if (!status || !(status.installing || status.login_in_progress)) return;
    const id = window.setInterval(async () => {
      const s = await refresh();
      if (s && !s.installing && s.cli_installed && loginAfterInstall.current) {
        loginAfterInstall.current = false;
        const r = await aiAccountsApi.anthropicLogin();
        setNote(r.message);
        refresh();
      }
    }, 3000);
    return () => window.clearInterval(id);
  }, [status, refresh]);

  // Coming back from the browser: re-check right away
  useEffect(() => {
    const onFocus = () => refresh();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refresh]);

  const start = async () => {
    setBusy(true);
    setNote(null);
    if (!status?.cli_installed) {
      loginAfterInstall.current = true;
      const r = await aiAccountsApi.installAnthropicCli();
      setNote(r.message);
    } else {
      const r = await aiAccountsApi.anthropicLogin();
      setNote(r.message);
    }
    await refresh();
    setBusy(false);
  };

  const logout = async () => {
    setBusy(true);
    const r = await aiAccountsApi.anthropicLogout();
    setNote(r.message);
    await refresh();
    setBusy(false);
  };

  const loggedIn = status?.logged_in === true;
  return (
    <div className="p-3 rounded-xl bg-[#090D16] border border-borderMuted space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold text-gray-300 inline-flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-purple-400" /> Login Akun Anthropic
        </span>
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
            loggedIn
              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40'
              : status?.login_in_progress || status?.installing
              ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
              : 'bg-slate-800 text-gray-300 border-slate-700'
          }`}
        >
          {loggedIn ? 'Terhubung' : status?.installing ? 'Memasang CLI…' : status?.login_in_progress ? 'Menunggu login…' : 'Belum login'}
        </span>
      </div>

      <p className="text-[11px] text-gray-400 leading-relaxed">
        Login memakai akun <strong>Claude Console</strong> (console.anthropic.com) lewat program resmi Anthropic CLI — tidak perlu
        menyalin API key. Pemakaian ditagih ke kredit API akun tersebut; langganan Claude Pro/Max di claude.ai tidak berlaku di sini.
      </p>

      {status && <p className={`text-[11px] ${loggedIn ? 'text-emerald-300' : 'text-gray-300'}`}>{status.message}</p>}
      {status?.install_error && <p className="text-[11px] text-rose-300">Pemasangan CLI gagal: {status.install_error}</p>}
      {status?.api_key_env_set && (
        <p className="text-[11px] text-amber-300">
          Variabel ANTHROPIC_API_KEY terpasang di Windows; SAHAM mengabaikannya dalam mode login agar akun yang Anda login-kan yang dipakai.
        </p>
      )}
      {note && <p className="text-[11px] text-sky-300">{note}</p>}
      {status?.login_in_progress && status.login_url && (
        <button
          type="button"
          onClick={() => aiAccountsApi.openInBrowser(status.login_url as string)}
          className="text-[11px] text-purple-300 underline inline-flex items-center gap-1"
        >
          Browser tidak terbuka? Buka halaman login <ExternalLink className="w-3 h-3" />
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!loggedIn ? (
          <button
            type="button"
            onClick={start}
            disabled={busy || !!status?.installing}
            className="px-3 py-1.5 rounded-lg bg-purple-600/30 border border-purple-500/50 text-purple-100 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            {busy || status?.installing ? <Activity className="w-3.5 h-3.5 animate-spin" /> : <LogIn className="w-3.5 h-3.5" />}
            {status?.cli_installed ? 'Login dengan Akun Anthropic' : 'Pasang Anthropic CLI & Login'}
          </button>
        ) : (
          <button
            type="button"
            onClick={logout}
            disabled={busy}
            className="px-3 py-1.5 rounded-lg bg-surface border border-borderMuted text-gray-200 text-xs font-semibold inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <LogOut className="w-3.5 h-3.5" /> Logout
          </button>
        )}
        <button
          type="button"
          onClick={() => refresh()}
          className="px-2.5 py-1.5 rounded-lg text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1"
        >
          <RefreshCw className="w-3 h-3" /> Cek status
        </button>
        <button
          type="button"
          onClick={() => aiAccountsApi.openInBrowser('https://console.anthropic.com/settings/billing')}
          className="px-2.5 py-1.5 rounded-lg text-[11px] text-purple-300 hover:text-purple-200 inline-flex items-center gap-1"
          title="Kredit API terpisah dari langganan Claude Pro/Max"
        >
          Cek / isi kredit API <ExternalLink className="w-3 h-3" />
        </button>
      </div>
      {loggedIn && (
        <p className="text-[10px] text-gray-500">
          Status "Terhubung" berarti login berhasil. Untuk menjalankan model, akun Console juga perlu saldo kredit API.
        </p>
      )}
      {!status?.cli_installed && (
        <p className="text-[10px] text-gray-500">
          Pertama kali: SAHAM mengunduh Anthropic CLI v{status?.cli_version ?? '1.44.0'} resmi (~13 MB) dari GitHub Anthropic,
          memeriksa checksum SHA-256-nya, lalu membuka browser untuk login.
        </p>
      )}
    </div>
  );
};

/** AI accounts signed in inside 9router, with a shortcut to its dashboard to log in / manage them. */
export const RouterAccountsPanel: React.FC<{ baseUrl: string; highlight?: string[]; onChanged?: () => void }> = ({
  baseUrl,
  highlight = [],
  onChanged,
}) => {
  const [data, setData] = useState<RouterAccountsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    const r = await aiAccountsApi.routerAccounts(baseUrl);
    setData(r);
    setLoading(false);
  }, [baseUrl]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // After signing in on the 9router dashboard and coming back, refresh accounts and models
  useEffect(() => {
    const onFocus = () => {
      refresh();
      onChanged?.();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refresh, onChanged]);

  const openDashboard = () => data?.dashboard_url && aiAccountsApi.openInBrowser(data.dashboard_url);

  return (
    <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <Users className="w-4 h-4 text-purple-400" />
          <span className="text-xs font-bold text-white">Akun AI (login lewat 9router)</span>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1"
          aria-label="Segarkan status akun"
        >
          {loading ? <Activity className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Segarkan
        </button>
      </div>
      <p className="text-[11px] text-gray-400 leading-relaxed">
        Akun Antigravity, Codex, Claude Code, Gemini CLI, Copilot, dan lainnya di-login-kan di dashboard 9router — aplikasi-aplikasi
        itu tidak menyediakan login untuk aplikasi lain. Klik <strong>Login</strong> untuk membuka halamannya di browser; setelah
        selesai dan kembali ke SAHAM, status & daftar model diperbarui otomatis.
      </p>
      {data && !data.ok && <p className="text-[11px] text-amber-300">{data.message}</p>}
      {data?.ok && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {data.accounts.map((a) => {
            const hl = highlight.includes(a.prefix);
            return (
              <div
                key={a.prefix}
                className={`flex items-center justify-between gap-2 p-2 rounded-lg border text-[11px] ${
                  hl ? 'border-purple-500/50 bg-purple-500/5' : 'border-borderMuted bg-[#090D16]'
                }`}
              >
                <div className="min-w-0">
                  <div className="font-semibold text-gray-200 truncate">{a.name}</div>
                  <div className={a.connected ? 'text-emerald-300' : 'text-gray-500'}>
                    {a.connected ? (
                      <span className="inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Terhubung · {a.models_count} model
                      </span>
                    ) : (
                      'Belum login'
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={openDashboard}
                  className="shrink-0 px-2 py-1 rounded-md border border-purple-500/40 text-purple-200 hover:bg-purple-500/10 inline-flex items-center gap-1"
                >
                  {a.connected ? 'Kelola' : 'Login'} <ExternalLink className="w-3 h-3" />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {data?.dashboard_url && (
        <p className="text-[10px] text-gray-500">
          Dashboard: <code className="font-mono">{data.dashboard_url}</code>
        </p>
      )}
    </div>
  );
};
