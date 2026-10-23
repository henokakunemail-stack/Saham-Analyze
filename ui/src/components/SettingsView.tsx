import React, { useState, useEffect } from 'react';
import {
  Server,
  Sliders,
  Key,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  Sparkles,
  Activity,
  Bot,
  Zap,
  ShieldCheck,
  Cpu,
  Building2,
  ExternalLink
} from 'lucide-react';
import { api } from '../api/client';
import { API_BASE } from '../api/base';
import { AiModelsResponse } from '../types/stock';
import { GATE_LABELS, getTerm } from '../lib/glossary';

const CLAUDE_DEFAULT_MODEL = 'claude-opus-5-5';
const LOCAL_ROUTER_URL = 'http://localhost:20128/v1';
/** Providers reached through 9router but shown on their own (account signed in inside 9router). */
const GATEWAY_PROVIDERS: Record<string, { label: string; prefix: string }> = {
  antigravity: { label: 'Antigravity', prefix: 'ag' },
  codex: { label: 'Codex', prefix: 'cx' },
};
import { UniverseSettings } from './UniverseSettings';
import { TelegramSettings } from './TelegramSettings';
import { ClaudeLoginPanel, RouterAccountsPanel } from './AiLoginPanels';

/** Host the UI talks to (the engine runs wherever SAHAM is installed: this PC or a server). */
const ENGINE_HOST = (() => {
  try {
    return new URL(API_BASE).host;
  } catch {
    return '';
  }
})();

/** Confluence gates in engine order (engine/screener/scoring.py), described by the glossary. */
const CONFLUENCE_GATES = [
  'gate_smart_money',
  'gate_volume_expansion',
  'gate_trend_alignment',
  'gate_resistance_breakout',
  'gate_risk_reward',
  'gate_financial_health',
];

/** Score pillar weights (engine/screener/scoring.py PILLAR_WEIGHTS). */
const PILLAR_WEIGHTS: { label: string; pct: number; color: string }[] = [
  { label: 'Setup Pullback', pct: 35, color: 'text-emerald-400' },
  { label: 'Arah Tren', pct: 20, color: 'text-blue-400' },
  { label: 'Fundamental', pct: 12, color: 'text-cyan-400' },
  { label: 'Aliran Dana', pct: 10, color: 'text-emerald-300' },
  { label: 'Momentum', pct: 10, color: 'text-amber-400' },
  { label: 'Sentimen Berita', pct: 8, color: 'text-purple-400' },
  { label: 'Pola Setup', pct: 5, color: 'text-gray-300' },
];

interface Props {
  isEngineOnline: boolean;
}

export const SettingsView: React.FC<Props> = ({ isEngineOnline }) => {
  const [provider, setProvider] = useState<string>('9router');
  const [baseUrl, setBaseUrl] = useState<string>('https://api.9router.com/v1');
  const [apiKey, setApiKey] = useState<string>('');
  const [model, setModel] = useState<string>('deepseek-chat');
  const [showKey, setShowKey] = useState<boolean>(false);

  const [sectorsApiKey, setSectorsApiKey] = useState<string>('');
  const [showSectorsKey, setShowSectorsKey] = useState<boolean>(false);
  const [testingBroker, setTestingBroker] = useState<boolean>(false);
  const [brokerTestResult, setBrokerTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const [saving, setSaving] = useState<boolean>(false);
  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);
  // Saving is only allowed once the real settings were loaded, so defaults never overwrite them
  const [loaded, setLoaded] = useState<boolean>(false);

  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string; latency_ms?: number } | null>(null);

  // Claude (Anthropic) keeps its own key & model so switching providers never loses the 9router key
  const [anthropicKey, setAnthropicKey] = useState<string>('');
  const [anthropicModel, setAnthropicModel] = useState<string>(CLAUDE_DEFAULT_MODEL);
  const [anthropicAuthMode, setAnthropicAuthMode] = useState<'api_key' | 'login'>('api_key');
  const isClaude = provider === 'anthropic';
  const claudeLogin = isClaude && anthropicAuthMode === 'login';
  const gateway = GATEWAY_PROVIDERS[provider];
  const viaRouter = provider === '9router' || !!gateway;
  const activeKey = isClaude ? anthropicKey : apiKey;
  const activeModel = isClaude ? anthropicModel : model;
  const setActiveModel = isClaude ? setAnthropicModel : setModel;

  const [detectingModels, setDetectingModels] = useState<boolean>(false);
  const [detected, setDetected] = useState<AiModelsResponse | null>(null);
  // Only the latest detection may update the UI: a slow reply for a previously selected
  // provider (9router's /models can take ~10 s) must not overwrite the current one.
  const detectSeq = React.useRef(0);

  const handleAutoDetectModels = async (opts?: {
    provider?: string;
    baseUrl?: string;
    key?: string;
    keepModel?: boolean;
    authMode?: 'api_key' | 'login';
    refresh?: boolean;
  }) => {
    const prov = opts?.provider ?? provider;
    const seq = ++detectSeq.current;
    setDetectingModels(true);
    const res = await api.fetchAiModels({
      provider: prov,
      base_url: opts?.baseUrl ?? baseUrl,
      api_key: opts?.key ?? (prov === 'anthropic' ? anthropicKey : apiKey),
      auth_mode: prov === 'anthropic' ? opts?.authMode ?? anthropicAuthMode : undefined,
      refresh: opts?.refresh,
    });
    if (seq !== detectSeq.current) return; // superseded by a newer detection
    setDetected(res);
    // Keep the user's current choice when it still exists; otherwise suggest the first combo/model
    if (res.ok && !opts?.keepModel && res.models.length > 0) {
      const current = prov === 'anthropic' ? anthropicModel : model;
      if (!res.models.includes(current)) {
        (prov === 'anthropic' ? setAnthropicModel : setModel)(res.models[0]);
      }
    }
    setDetectingModels(false);
  };

  // (Re)load when the engine is (back) online and nothing was loaded yet
  useEffect(() => {
    if (!isEngineOnline || loaded) return;
    let cancelled = false;
    api.getSettings().then((settings) => {
      if (cancelled) return;
      if (settings) {
        setLoaded(true);
        if (settings.provider) setProvider(settings.provider);
        if (settings.base_url) setBaseUrl(settings.base_url);
        if (settings.api_key) {
          setApiKey(settings.api_key);
        } else if (settings.masked_api_key) {
          setApiKey(settings.masked_api_key);
        }
        if (settings.model) setModel(settings.model);
        if (settings.sectors_api_key) {
          setSectorsApiKey(settings.sectors_api_key);
        } else if (settings.masked_sectors_key) {
          setSectorsApiKey(settings.masked_sectors_key);
        }
        if (settings.masked_anthropic_key) setAnthropicKey(settings.masked_anthropic_key);
        if (settings.anthropic_model) setAnthropicModel(settings.anthropic_model);
        const mode = settings.anthropic_auth_mode === 'login' ? 'login' : 'api_key';
        setAnthropicAuthMode(mode);
        // Auto-detect on open: combos/models come from the gateway itself, never a fixed list
        if (settings.provider === 'anthropic' ? settings.is_anthropic_key_set || mode === 'login' : true) {
          handleAutoDetectModels({ provider: settings.provider, baseUrl: settings.base_url, keepModel: true, authMode: mode,
            key: settings.provider === 'anthropic' ? settings.masked_anthropic_key : settings.masked_api_key });
        }
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEngineOnline, loaded]);

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    setDetected(null);
    detectSeq.current++; // any detection still in flight belongs to the previous provider
    setTestResult(null);
    if (newProvider === '9router' || GATEWAY_PROVIDERS[newProvider]) {
      // Antigravity / Codex / 9router all go through the local 9router gateway
      const url = /localhost|127\.0\.0\.1/.test(baseUrl) ? baseUrl : LOCAL_ROUTER_URL;
      setBaseUrl(url);
      handleAutoDetectModels({ provider: newProvider, baseUrl: url });
    } else if (newProvider === 'openai') {
      setBaseUrl('https://api.openai.com/v1');
      setModel('gpt-4o-mini');
    } else if (newProvider === 'anthropic' && (anthropicKey || anthropicAuthMode === 'login')) {
      handleAutoDetectModels({ provider: 'anthropic', keepModel: true });
    }
  };

  const handleSave = async () => {
    if (!loaded) return;
    setSaving(true);
    const ok = await api.updateSettings({
      provider,
      base_url: baseUrl,
      api_key: apiKey,
      model,
      sectors_api_key: sectorsApiKey,
      anthropic_api_key: anthropicKey,
      anthropic_model: anthropicModel,
      anthropic_auth_mode: anthropicAuthMode,
    });
    setSaving(false);
    if (ok) {
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2500);
    }
  };

  const handleTestBrokerConnection = async () => {
    setTestingBroker(true);
    setBrokerTestResult(null);
    const res = await api.testBrokerApiKey('sectors', sectorsApiKey);
    setBrokerTestResult(res);
    setTestingBroker(false);
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    const res = await api.testAiConnection({
      provider,
      base_url: baseUrl,
      api_key: claudeLogin ? '' : activeKey,
      model: activeModel,
      auth_mode: isClaude ? anthropicAuthMode : undefined,
    });
    setTestResult(res);
    if (res.ok && res.model && res.model !== activeModel && !isClaude) {
      setModel(res.model);
    }
    setTesting(false);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-base font-bold text-white">Pengaturan Sistem & Engine</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Kelola cakupan scan, notifikasi Telegram, koneksi engine, integrasi AI (Claude, Antigravity, Codex, 9router), dan lihat
          parameter scoring kuantitatif.
        </p>
      </div>
      <UniverseSettings isEngineOnline={isEngineOnline} />
      <TelegramSettings isEngineOnline={isEngineOnline} />

      {/* Engine Status Card */}
      <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Server className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-bold text-white">Status Python Engine Sidecar</span>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold ${
              isEngineOnline
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
            }`}
          >
            {isEngineOnline ? `ONLINE${ENGINE_HOST ? ` (${ENGINE_HOST})` : ''}` : 'OFFLINE'}
          </span>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">
          Engine berjalan di mesin tempat SAHAM dipasang (PC Anda atau server), memproses kalkulasi teknikal, aliran dana CMF,
          volume spike VSA, dan menyimpan cache SQLite di mesin tersebut. Data harga &amp; berita tetap diambil dari sumber
          data pasar daring.
        </p>
      </div>

      {/* AI provider configuration (Claude via official SDK, or OpenAI-compatible gateways) */}
      <div className="p-4 rounded-xl bg-surface border border-purple-500/30 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Bot className="w-4 h-4 text-purple-400" />
            <span className="text-xs font-bold text-white">Integrasi AI (Claude / 9router / OpenAI)</span>
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
            {isClaude ? 'Anthropic SDK' : 'OpenAI-Compatible'}
          </span>
        </div>

        <p className="text-xs text-gray-400 leading-relaxed">
          AI dipakai untuk <strong>Validasi Sinyal</strong> dan <strong>Deteksi Bull-Trap</strong> di detail saham. Pilih penyedia,
          lalu daftar model/combo yang tersedia dideteksi otomatis dari penyedia tersebut.
        </p>

        {/* Provider Selector */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Penyedia AI (Provider)</label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {[
              { id: 'anthropic', label: 'Claude (Anthropic)' },
              { id: 'antigravity', label: 'Antigravity' },
              { id: 'codex', label: 'Codex (ChatGPT)' },
              { id: '9router', label: '9router' },
              { id: 'openai', label: 'OpenAI Resmi' },
              { id: 'custom', label: 'Custom Proxy' },
            ].map((p) => (
              <button
                key={p.id}
                type="button"
                aria-pressed={provider === p.id}
                onClick={() => handleProviderChange(p.id)}
                className={`py-2 px-3 rounded-lg text-xs font-semibold border transition-all text-center ${
                  provider === p.id
                    ? 'bg-purple-600/20 border-purple-500 text-purple-200 font-bold shadow-sm'
                    : 'bg-[#090D16] border-borderMuted text-gray-400 hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Base URL (not used by Claude: the SDK talks to api.anthropic.com) */}
        {isClaude ? (
          <div className="space-y-2">
            <p className="text-[11px] text-gray-400">
              Terhubung langsung ke <code className="text-purple-300 font-mono">api.anthropic.com</code> memakai SDK resmi Anthropic.
            </p>
            <div className="space-y-1">
              <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Cara Masuk</label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: 'login' as const, label: 'Login Akun Anthropic' },
                  { id: 'api_key' as const, label: 'API Key' },
                ].map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    aria-pressed={anthropicAuthMode === m.id}
                    onClick={() => {
                      setAnthropicAuthMode(m.id);
                      setDetected(null);
                      setTestResult(null);
                    }}
                    className={`py-1.5 px-3 rounded-lg text-xs font-semibold border ${
                      anthropicAuthMode === m.id
                        ? 'bg-purple-600/20 border-purple-500 text-purple-200 font-bold'
                        : 'bg-[#090D16] border-borderMuted text-gray-400 hover:text-white'
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            {claudeLogin && (
              <ClaudeLoginPanel onLoggedIn={() => handleAutoDetectModels({ provider: 'anthropic', authMode: 'login', keepModel: true })} />
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Base URL API</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              onBlur={() => viaRouter && handleAutoDetectModels({ keepModel: true })}
              placeholder="http://localhost:20128/v1"
              className="w-full bg-[#090D16] border border-borderMuted rounded-xl px-3 py-2 text-xs text-white placeholder-gray-500 font-mono focus:outline-none focus:border-purple-500"
            />
          </div>
        )}

        {gateway && (
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Akun <strong>{gateway.label}</strong> di-login-kan di dashboard 9router (lihat kartu <em>Akun AI</em> di bawah). SAHAM
            memakai model <code className="text-purple-300 font-mono">{gateway.prefix}/…</code> dari 9router tersebut.
          </p>
        )}

        {/* API Key (not needed when signed in to Anthropic) */}
        {!claudeLogin && <div className="space-y-1.5">
          <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">
            {isClaude ? 'API Key Anthropic' : viaRouter ? 'API Key 9router (opsional untuk 9router lokal)' : 'API Key'}
          </label>
          <div className="relative flex items-center">
            <input
              type={showKey ? 'text' : 'password'}
              value={activeKey}
              onChange={(e) => (isClaude ? setAnthropicKey : setApiKey)(e.target.value)}
              placeholder={isClaude ? 'sk-ant-...' : 'Masukkan API Key...'}
              autoComplete="off"
              className="w-full bg-[#090D16] border border-borderMuted rounded-xl pl-3 pr-10 py-2 text-xs text-white placeholder-gray-500 font-mono focus:outline-none focus:border-purple-500"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              aria-label={showKey ? 'Sembunyikan API key' : 'Tampilkan API key'}
              className="absolute right-3 text-gray-400 hover:text-white"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>}

        {/* Model / combo */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              {isClaude ? 'Model Claude' : gateway ? `Model ${gateway.label}` : 'Model / Combo'}
            </label>
            <button
              type="button"
              onClick={() => handleAutoDetectModels({ refresh: true })}
              disabled={detectingModels || (isClaude && !claudeLogin && !anthropicKey)}
              className="text-[11px] font-bold text-purple-400 hover:text-purple-300 flex items-center gap-1 transition-colors disabled:opacity-50"
            >
              {detectingModels ? <Activity className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              <span>{isClaude ? 'Deteksi Model Claude' : gateway ? `Deteksi Model ${gateway.label}` : 'Deteksi Ulang Combo / Model'}</span>
            </button>
          </div>

          {/* 9router combos as chips: detected from the gateway, with their capabilities */}
          {!isClaude && detected?.ok && detected.combos.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider text-gray-500 font-bold">
                Combo tersedia di gateway ({detected.combos.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {detected.combos.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={model === c.id}
                    onClick={() => setModel(c.id)}
                    title={`Konteks ${c.context_length?.toLocaleString('id-ID') ?? '-'} token${c.reasoning ? ' · reasoning' : ''}${c.vision ? ' · vision' : ''}${c.tools ? ' · tools' : ''}`}
                    className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono inline-flex items-center gap-1 ${
                      model === c.id
                        ? 'bg-purple-600/25 border-purple-500 text-purple-100'
                        : 'bg-[#090D16] border-borderMuted text-gray-300 hover:text-white'
                    }`}
                  >
                    {c.id}
                    {c.context_length ? (
                      <span className="text-[9px] text-gray-500">
                        {c.context_length >= 1_000_000 ? `${Math.round(c.context_length / 1_000_000)}M` : `${Math.round(c.context_length / 1000)}K`}
                      </span>
                    ) : null}
                    {c.reasoning && <span className="text-[9px]" title="reasoning">🧠</span>}
                    {c.vision && <span className="text-[9px]" title="vision">👁</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <input
              type="text"
              value={activeModel}
              onChange={(e) => setActiveModel(e.target.value)}
              placeholder={isClaude ? CLAUDE_DEFAULT_MODEL : 'Nama combo atau ID model'}
              className="flex-1 bg-[#090D16] border border-borderMuted rounded-xl px-3 py-2 text-xs text-white placeholder-gray-500 font-mono focus:outline-none focus:border-purple-500"
            />
            <select
              onChange={(e) => {
                if (e.target.value) setActiveModel(e.target.value);
              }}
              aria-label="Pilih model atau combo yang terdeteksi"
              className="bg-[#090D16] border border-borderMuted rounded-xl px-3 py-2 text-xs text-gray-300 font-mono focus:outline-none focus:border-purple-500 max-w-[220px]"
              value={detected?.models.includes(activeModel) ? activeModel : ''}
            >
              <option value="" disabled>
                {detected?.ok ? 'Pilih dari daftar...' : 'Belum dideteksi'}
              </option>
              {detected?.combos.length ? (
                <optgroup label={`Combo (${detected.combos.length})`}>
                  {detected.combos.map((c) => (
                    <option key={c.id} value={c.id}>{c.id}</option>
                  ))}
                </optgroup>
              ) : null}
              {detected?.groups.map((g) => (
                <optgroup key={g.provider} label={`${g.label} (${g.models.length})`}>
                  {g.models.map((m) => (
                    <option key={m.id} value={m.id}>{m.label && m.label !== m.id ? `${m.label} — ${m.id}` : m.id}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {detected && (
            <p className={`text-[10px] ${detected.ok ? 'text-gray-400' : 'text-amber-300'}`}>{detected.message}</p>
          )}
          {isClaude && (
            <p className="text-[10px] text-gray-500">
              Default <code className="text-purple-300 font-mono">{CLAUDE_DEFAULT_MODEL}</code> (Claude Opus 5.5). Jawaban dipaksa berformat
              JSON terstruktur; bila Claude menolak karena aturan keamanan, permintaan otomatis dialihkan ke model cadangan yang
              direkomendasikan Anthropic.
            </p>
          )}
        </div>

        {/* Action Buttons: Test Connection & Save */}
        <div className="pt-2 flex items-center justify-between border-t border-borderMuted">
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing || (isClaude && !claudeLogin && !anthropicKey)}
            className="px-4 py-2 rounded-xl bg-surface border border-purple-500/40 hover:border-purple-400 text-purple-200 text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testing ? (
              <Activity className="w-3.5 h-3.5 animate-spin text-purple-400" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
            )}
            <span>{testing ? 'Menguji Koneksi...' : isClaude ? 'Tes Koneksi Claude' : 'Tes Koneksi'}</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !loaded}
            title={loaded ? undefined : 'Menunggu pengaturan dimuat dari engine…'}
            className="px-5 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-bold transition-all flex items-center gap-1.5 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {savedSuccess ? <CheckCircle2 className="w-4 h-4" /> : null}
            <span>
              {savedSuccess ? 'Pengaturan Tersimpan' : saving ? 'Menyimpan...' : loaded ? 'Simpan Pengaturan' : 'Memuat pengaturan…'}
            </span>
          </button>
        </div>

        {/* Live Test Result Banner */}
        {testResult && (
          <div
            className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 ${
              testResult.ok
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
            }`}
          >
            {testResult.ok ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            ) : (
              <XCircle className="w-4 h-4 shrink-0 text-rose-400" />
            )}
            <div className="flex-1">
              <span className="font-bold">{testResult.ok ? 'Sukses: ' : 'Gagal: '}</span>
              <span>{testResult.message}</span>
              {testResult.latency_ms && (
                <span className="ml-2 font-mono text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  {testResult.latency_ms}ms
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Accounts signed in inside 9router (Antigravity, Codex, Claude Code, ...) */}
      {(viaRouter || provider === 'custom') && (
        <RouterAccountsPanel
          baseUrl={baseUrl}
          highlight={gateway ? [gateway.prefix] : []}
          onChanged={() => handleAutoDetectModels({ keepModel: true })}
        />
      )}

      {/* 🏛️ Pengaturan Broker Summary & Bandarmologi */}
      <div className="p-5 rounded-2xl bg-surface border border-borderMuted space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-borderMuted pb-3">
          <div className="flex items-center gap-2.5">
            <Building2 className="w-5 h-5 text-cyan-400" />
            <div>
              <h2 className="text-sm font-bold text-white">Data Broker Summary & Bandarmologi (BEI)</h2>
              <p className="text-[11px] text-gray-400">
                Melihat sekuritas besar (AK, BK, KZ, CC, YP) yang sedang akumulasi atau distribusi
              </p>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
            EOD DATA
          </span>
        </div>

        <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-200 leading-relaxed space-y-1">
          <p>
            <strong>Tanpa API key (bawaan):</strong> detail saham menampilkan <em>Ringkasan Aliran Dana</em> dari harga &amp; volume
            (CMF, rasio volume hari naik/turun, pola volume). Itu indikasi, bukan data broker — kotak broker tidak ditampilkan.
          </p>
          <p>
            <strong>Opsional — data broker asli:</strong> untuk melihat kode broker BEI (Top Buyer vs Top Seller), masukkan API key
            <strong> Sectors.app</strong> di bawah ini. Kotak broker summary akan muncul otomatis.
          </p>
        </div>

        {/* Sectors.app API Key Input */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-cyan-400" />
              <span>Sectors.app API Key (Rekomendasi Resmi BEI):</span>
            </label>
            <a
              href="https://sectors.app"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
            >
              <span>Daftar / Dapatkan Key Gratis</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <div className="relative">
            <input
              type={showSectorsKey ? 'text' : 'password'}
              value={sectorsApiKey}
              onChange={(e) => setSectorsApiKey(e.target.value)}
              placeholder="Contoh: sec_live_..."
              className="w-full bg-[#090D16] border border-borderMuted rounded-xl px-3 py-2 pr-10 text-xs text-white placeholder-gray-500 font-mono focus:outline-none focus:border-cyan-500"
            />
            <button
              type="button"
              onClick={() => setShowSectorsKey(!showSectorsKey)}
              aria-label={showSectorsKey ? 'Sembunyikan API key Sectors.app' : 'Tampilkan API key Sectors.app'}
              className="absolute right-3 top-2.5 text-gray-400 hover:text-white"
            >
              {showSectorsKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
          <p className="text-[10px] text-gray-500">
            Kunci disimpan di database SQLite engine SAHAM (di mesin tempat SAHAM dipasang) dan hanya dipakai untuk memanggil
            Sectors.app.
          </p>
        </div>

        {/* Actions for Broker Settings */}
        <div className="pt-2 flex items-center justify-between border-t border-borderMuted">
          <button
            type="button"
            onClick={handleTestBrokerConnection}
            disabled={testingBroker || !sectorsApiKey}
            className="px-4 py-2 rounded-xl bg-surface border border-cyan-500/40 hover:border-cyan-400 text-cyan-200 text-xs font-bold transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testingBroker ? (
              <Activity className="w-3.5 h-3.5 animate-spin text-cyan-400" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            )}
            <span>{testingBroker ? 'Menguji API Key...' : 'Uji Koneksi Sectors.app'}</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !loaded}
            title={loaded ? undefined : 'Menunggu pengaturan dimuat dari engine…'}
            className="px-5 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-bold transition-all flex items-center gap-1.5 shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {savedSuccess ? <CheckCircle2 className="w-4 h-4" /> : null}
            <span>{savedSuccess ? 'Tersimpan' : loaded ? 'Simpan Kunci Broker' : 'Memuat pengaturan…'}</span>
          </button>
        </div>

        {/* Broker Test Result Banner */}
        {brokerTestResult && (
          <div
            className={`p-3 rounded-xl border text-xs flex items-center gap-2.5 ${
              brokerTestResult.ok
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
            }`}
          >
            {brokerTestResult.ok ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            ) : (
              <XCircle className="w-4 h-4 shrink-0 text-rose-400" />
            )}
            <div className="flex-1">
              <span className="font-bold">{brokerTestResult.ok ? 'Sukses: ' : 'Gagal: '}</span>
              <span>{brokerTestResult.message}</span>
            </div>
          </div>
        )}
      </div>

      {/* 6 Gerbang Konfluensi (dihitung engine; teks dari glosarium) */}
      <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-3">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-bold text-white">6 Gerbang Konfluensi (Anti Bull-Trap)</span>
        </div>
        <p className="text-xs text-gray-400 leading-relaxed">
          Setiap saham dicek terhadap 6 syarat sekaligus. Setup disebut <strong>terkonfirmasi</strong> bila minimal 4 dari 6
          lolos <em>dan</em> gerbang Searah Tren lolos. Lolos semua gerbang tetap bukan jaminan harga naik.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs pt-1">
          {CONFLUENCE_GATES.map((key, i) => {
            const term = getTerm(key);
            return (
              <div key={key} className="p-2.5 rounded-lg bg-[#090D16] border border-borderMuted flex items-start gap-2">
                <span className="text-emerald-400 font-bold">{i + 1}.</span>
                <div>
                  <span className="font-bold text-gray-200">{GATE_LABELS[key] ?? key}</span>
                  {term && <p className="text-[11px] text-gray-400">{term.what}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bobot pilar skor komposit */}
      <div className="p-4 rounded-xl bg-surface border border-borderMuted space-y-3">
        <div className="flex items-center gap-2.5">
          <Sliders className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-bold text-white">Bobot Pilar Skor Komposit</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-center font-mono">
          {PILLAR_WEIGHTS.map((p) => (
            <div key={p.label} className="p-2.5 rounded-lg bg-[#090D16] border border-borderMuted">
              <div className="text-[10px] text-gray-400">{p.label}</div>
              <div className={`text-sm font-bold mt-1 ${p.color}`}>{p.pct}%</div>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-gray-500">Bobot ini tetap (diatur di engine) dan hanya ditampilkan sebagai informasi.</p>
      </div>
    </div>
  );
};
