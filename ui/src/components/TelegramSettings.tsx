import React, { useCallback, useEffect, useState } from 'react';
import { Activity, CheckCircle2, ExternalLink, RefreshCw, Send } from 'lucide-react';
import { requestJson, TIMEOUT } from '../api/feedback';
import { API_BASE } from '../api/base';
import { aiAccountsApi } from '../api/aiAccounts';

type SendKind = 'daily_plan' | 'midday' | 'alerts' | 'weekly';

interface TelegramView {
  config: {
    enabled: boolean;
    chat_id: number | null;
    chat_title: string | null;
    markets: ('IDX' | 'US')[];
    send: Record<SendKind, boolean>;
    commands: boolean;
  };
  token_set: boolean;
  masked_token: string;
  status: {
    running: boolean;
    bot_username: string | null;
    last_ok_at: number | null;
    last_error: string | null;
    recent: { at: string; kind: string; ok: boolean; detail: string }[];
  };
  chats: { id: number; title: string; type: string; seen: number }[];
}

const SEND_OPTIONS: { key: SendKind; label: string; desc: string }[] = [
  { key: 'daily_plan', label: 'Rencana untuk besok', desc: 'Setelah penutupan final (±16:50 WIB): Top 10 + zona beli, TP, cut loss' },
  { key: 'midday', label: 'Cek tengah hari', desc: 'Saat jeda siang: posisi harga vs rencana' },
  { key: 'alerts', label: 'Peringatan langsung', desc: 'Masuk zona beli, sentuh TP1, sentuh cut loss (sekali per hari per saham)' },
  { key: 'weekly', label: 'Rekam jejak mingguan', desc: 'Jumat setelah penutupan' },
];

const api = {
  get: () => requestJson<TelegramView>(`${API_BASE}/telegram`, { timeout: TIMEOUT.short }),
  save: (body: Record<string, unknown>) =>
    requestJson<TelegramView>(`${API_BASE}/telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      op: 'telegram.save',
      title: 'Gagal menyimpan pengaturan Telegram',
    }),
  test: (token: string) =>
    requestJson<{ ok: boolean; message: string }>(`${API_BASE}/telegram/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      timeout: TIMEOUT.slow,
    }),
  sendNow: (kind: string) =>
    requestJson<{ ok: boolean; message: string }>(`${API_BASE}/telegram/send/${kind}`, { method: 'POST', timeout: TIMEOUT.slow }),
};

/** Pengaturan → Telegram: bot token, the group, which messages go out, and a send log. */
export const TelegramSettings: React.FC<{ isEngineOnline: boolean }> = ({ isEngineOnline }) => {
  const [view, setView] = useState<TelegramView | null>(null);
  const [token, setToken] = useState('');
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const v = await api.get();
      setView(v);
      setToken((t) => t || v.masked_token);
    } catch {
      /* engine offline: the card shows the offline state */
    }
  }, []);

  useEffect(() => {
    if (!isEngineOnline) return;
    load();
    const id = window.setInterval(load, 15000);
    return () => window.clearInterval(id);
  }, [isEngineOnline, load]);

  const save = async (body: Record<string, unknown>) => {
    try {
      setView(await api.save(body));
    } catch {
      /* toast shown by requestJson */
    }
  };

  const run = async (key: string, fn: () => Promise<{ ok: boolean; message: string }>) => {
    setBusy(key);
    setNote(null);
    try {
      const r = await fn();
      setNote({ ok: r.ok, text: r.message });
    } catch (e) {
      setNote({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
    setBusy(null);
    load();
  };

  if (!view) {
    return (
      <div className="p-4 rounded-xl bg-surface border border-borderMuted text-xs text-gray-400">
        {isEngineOnline ? 'Memuat pengaturan Telegram…' : 'Engine offline.'}
      </div>
    );
  }

  const cfg = view.config;
  const st = view.status;
  const group = view.chats.find((c) => c.id === cfg.chat_id);

  return (
    <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <Send className="w-4 h-4 text-sky-400" /> Bot Telegram
          </h2>
          <p className="text-[11px] text-gray-400 mt-0.5">
            Kirim rencana, cek tengah hari, peringatan dan rekam jejak ke grup Telegram; anggota grup bisa bertanya
            dengan perintah (/top10, /cek BBCA, …).
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-200 shrink-0">
          <input
            type="checkbox"
            checked={cfg.enabled}
            disabled={!view.token_set || !cfg.chat_id}
            onChange={(e) => save({ enabled: e.target.checked })}
          />
          Aktif
        </label>
      </div>

      {/* Step 1: token */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-gray-300">1. Token bot</div>
        <p className="text-[11px] text-gray-500">
          Buat bot di Telegram lewat{' '}
          <button
            type="button"
            className="text-sky-300 underline inline-flex items-center gap-0.5"
            onClick={() => aiAccountsApi.openInBrowser('https://t.me/BotFather')}
          >
            @BotFather <ExternalLink className="w-3 h-3" />
          </button>{' '}
          (perintah /newbot), lalu tempel token yang diberikan. Token disimpan di komputer/server ini saja.
        </p>
        <div className="flex gap-2">
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="123456789:AA..."
            className="flex-1 bg-[#090D16] border border-borderMuted rounded-lg px-3 py-1.5 text-xs text-white font-mono"
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => run('test', async () => {
              const r = await api.test(token);
              if (r.ok && token && token !== view.masked_token) await save({ token });
              return r;
            })}
            disabled={busy !== null || !token}
            className="px-3 py-1.5 rounded-lg bg-sky-600/30 border border-sky-500/50 text-sky-100 text-xs font-bold disabled:opacity-50"
          >
            {busy === 'test' ? 'Mengecek…' : 'Cek & simpan'}
          </button>
        </div>
        {st.bot_username && (
          <p className="text-[11px] text-emerald-300 inline-flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Bot: @{st.bot_username}
          </p>
        )}
      </div>

      {/* Step 2: group */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-gray-300">2. Grup</div>
        <p className="text-[11px] text-gray-500">
          Masukkan bot ke grup Anda, lalu ketik <code className="text-gray-300">/start</code> di grup. Grup akan muncul di
          bawah dalam ±30 detik (bot harus aktif dulu: centang "Aktif" setelah grup dipilih, atau klik Muat ulang).
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={cfg.chat_id ?? ''}
            onChange={(e) => {
              const c = view.chats.find((x) => String(x.id) === e.target.value);
              save({ chat_id: c ? c.id : null, chat_title: c?.title ?? null });
            }}
            className="bg-[#090D16] border border-borderMuted rounded-lg px-2 py-1.5 text-xs text-white min-w-[220px]"
          >
            <option value="">— pilih grup —</option>
            {view.chats.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title || '(tanpa nama)'} · {c.type} · {c.id}
              </option>
            ))}
            {cfg.chat_id && !group && <option value={cfg.chat_id}>{cfg.chat_title || cfg.chat_id}</option>}
          </select>
          <button type="button" onClick={load} className="text-[11px] text-gray-400 hover:text-white inline-flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Muat ulang
          </button>
          {view.chats.length === 0 && view.token_set && !cfg.enabled && (
            <button
              type="button"
              onClick={() => save({ enabled: true })}
              className="text-[11px] text-sky-300 underline"
              title="Bot perlu berjalan untuk mendeteksi grup"
            >
              jalankan bot untuk mendeteksi grup
            </button>
          )}
        </div>
      </div>

      {/* Step 3: what to send */}
      <div className="space-y-1.5">
        <div className="text-[11px] font-semibold text-gray-300">3. Pesan otomatis</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {SEND_OPTIONS.map((o) => (
            <label key={o.key} className="flex items-start gap-2 p-2 rounded-lg border border-borderMuted bg-[#090D16] text-[11px]">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={cfg.send[o.key]}
                onChange={(e) => save({ send: { [o.key]: e.target.checked } })}
              />
              <span>
                <span className="text-gray-200 font-semibold">{o.label}</span>
                <span className="block text-gray-500">{o.desc}</span>
              </span>
            </label>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[11px] text-gray-300">
          <input type="checkbox" checked={cfg.commands} onChange={(e) => save({ commands: e.target.checked })} />
          Anggota grup boleh memakai perintah (/top10, /cek KODE, /rencana, /tengahhari, /pasar, /rekam)
        </label>
        <div className="flex items-center gap-2 text-[11px] text-gray-300">
          Bursa:
          {(['IDX', 'US'] as const).map((m) => (
            <label key={m} className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={cfg.markets.includes(m)}
                onChange={(e) => {
                  const next = e.target.checked ? [...cfg.markets, m] : cfg.markets.filter((x) => x !== m);
                  if (next.length) save({ markets: next });
                }}
              />
              {m}
            </label>
          ))}
        </div>
      </div>

      {/* Manual sends + status */}
      <div className="flex flex-wrap gap-2">
        {[
          ['test', 'Kirim pesan uji'],
          ['daily_plan', 'Kirim rencana sekarang'],
          ['midday', 'Kirim cek harga sekarang'],
          ['weekly', 'Kirim rekam jejak'],
        ].map(([kind, label]) => (
          <button
            key={kind}
            type="button"
            onClick={() => run(kind, () => api.sendNow(kind))}
            disabled={busy !== null || !view.token_set || !cfg.chat_id}
            className="px-2.5 py-1 rounded-lg bg-surfaceHover border border-borderMuted text-gray-200 text-[11px] font-semibold disabled:opacity-50 inline-flex items-center gap-1"
          >
            {busy === kind && <Activity className="w-3 h-3 animate-spin" />} {label}
          </button>
        ))}
      </div>
      {note && <p className={`text-[11px] ${note.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{note.text}</p>}
      {st.last_error && <p className="text-[11px] text-amber-300">Masalah terakhir: {st.last_error}</p>}
      {st.recent.length > 0 && (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-gray-400">Riwayat kirim terakhir</summary>
          <ul className="mt-1 space-y-0.5 text-gray-500 font-mono">
            {st.recent.map((r, i) => (
              <li key={i} className={r.ok ? '' : 'text-rose-300'}>
                {r.at.slice(5, 16).replace('T', ' ')} · {r.kind} · {r.ok ? 'ok' : r.detail}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-[10px] text-gray-500">
        Bot berjalan selama aplikasi/server SAHAM menyala. Aktifkan di satu tempat saja (desktop atau server) — dua
        aplikasi dengan bot yang sama akan saling berebut pesan.
      </p>
    </div>
  );
};
