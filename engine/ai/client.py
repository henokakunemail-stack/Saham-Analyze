"""AI gateway client for SAHAM Analyzer.

OpenAI-compatible gateways (9router, OpenAI, custom proxies) are called here over HTTP.
The Anthropic Claude provider lives in engine/ai/claude_provider.py (official SDK); calls
are routed there when the provider setting is "anthropic".
"""
import time
import json
import re
import threading
import requests
from typing import Dict, Any, Optional, List
from ..db import get_setting
from . import claude_provider

ANTHROPIC = "anthropic"
# Providers reached through the 9router gateway but shown on their own in SAHAM: their
# accounts are signed in inside 9router, and only their model prefix is listed.
GATEWAY_PROVIDERS = {"antigravity": "ag", "codex": "cx"}
# Hidden from the plain "9router" model list (Antigravity has its own entry).
HIDDEN_IN_9ROUTER = ("ag",)

DEFAULT_BASE_URL = "https://api.9router.com/v1"


def _stored_key_for(b_url: str, cfg: Dict[str, str]) -> str:
    """The saved key is only ever sent to the saved base URL: a request naming another host
    (e.g. a malicious page calling the local API) must not receive it."""
    return cfg["api_key"] if b_url.rstrip("/") == (cfg.get("base_url") or "").rstrip("/") else ""
DEFAULT_MODEL = "deepseek-chat"

# A complete verdict takes ~700-1,200 completion tokens on reasoning models (thinking counts
# toward the limit); 800 cut answers mid-JSON.
VALIDATE_MAX_TOKENS = 2000
# Short thinking: the prompt already carries every number the verdict needs. Measured on the
# 9router "claude" combo: ~8 s with "low" vs ~11 s at the default, same complete JSON.
VALIDATE_REASONING_EFFORT = "low"
VALIDATE_TIMEOUT = 90

def get_ai_config() -> Dict[str, str]:
    return {
        "provider": get_setting("ai_provider", "9router"),
        "base_url": get_setting("ai_base_url", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": get_setting("ai_api_key", ""),
        "model": get_setting("ai_model", DEFAULT_MODEL),
        "anthropic_api_key": get_setting("anthropic_api_key", ""),
        "anthropic_model": get_setting("anthropic_model", claude_provider.DEFAULT_MODEL),
        "anthropic_auth_mode": get_setting("anthropic_auth_mode", "api_key"),
    }

def test_ai_connection(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    auth_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Test ping to the configured provider (Claude via SDK, others via OpenAI-compatible HTTP)."""
    cfg = get_ai_config()
    if (provider or cfg["provider"]) == ANTHROPIC:
        use_login = (auth_mode or cfg["anthropic_auth_mode"]) == "login"
        key = "" if use_login else (api_key if api_key else cfg["anthropic_api_key"])
        return claude_provider.test_connection(key, model or cfg["anthropic_model"], use_login=use_login)
    b_url = (base_url or cfg["base_url"]).rstrip("/")
    key = api_key if api_key is not None else _stored_key_for(b_url, cfg)
    mdl = model or cfg["model"]
    if not mdl:
        return {"ok": False, "message": "Pilih model atau combo terlebih dahulu (gunakan Deteksi)."}

    endpoint = f"{b_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:  # a local 9router does not need a key
        headers["Authorization"] = f"Bearer {key}"

    def _send(model_name: str, timeout_sec: int = 25):
        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "Ping test: respond with OK"}
            ],
            "max_tokens": 10,
            "temperature": 0.1,
            "stream": False
        }
        return requests.post(endpoint, json=payload, headers=headers, timeout=timeout_sec)

    start = time.time()
    tested_models = [mdl]  # test exactly the chosen model: no silent switch to another provider

    last_err = ""
    for current_model in tested_models:
        try:
            resp = _send(current_model, timeout_sec=25)
            if resp.status_code == 200:
                latency = int((time.time() - start) * 1000)
                notice = f" (auto-fallback dari {mdl})" if current_model != mdl else ""
                return {
                    "ok": True,
                    "latency_ms": latency,
                    "model": current_model,
                    # Not a network ping: a full answer from the model behind the gateway
                    "message": f"Koneksi berhasil ({current_model}{notice}) - Waktu respons model: {latency}ms"
                }
            elif resp.status_code == 400 and "ambiguous" in resp.text.lower():
                last_err = f"Model ID ambiguous ({current_model})"
                continue
            elif resp.status_code in (404, 503):
                last_err = f"Model {current_model} tidak aktif (HTTP {resp.status_code})"
                continue
            else:
                try:
                    err_body = resp.json()
                    msg = err_body.get("error", {}).get("message", resp.text)
                except Exception:
                    msg = resp.text[:200]
                last_err = f"HTTP {resp.status_code}: {msg}"
        except requests.exceptions.Timeout:
            last_err = f"Timeout ({current_model}) server tidak merespons dalam 25 detik"
            continue
        except requests.exceptions.RequestException as e:
            return {"ok": False, "message": f"Koneksi jaringan gagal: {str(e)}"}

    return {"ok": False, "message": f"Gagal terhubung: {last_err}"}

def validate_signal_with_ai(
    ticker: str,
    market: str,
    technical: Dict[str, Any],
    money_flow: Dict[str, Any],
    composite: Dict[str, Any],
    news_headlines: Optional[List[str]] = None,
    direction: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Query 9router LLM for deep quant synthesis, bull-trap detection,
    and high-probability trade confirmation.
    """
    cfg = get_ai_config()
    use_claude = cfg["provider"] == ANTHROPIC
    claude_login = use_claude and cfg["anthropic_auth_mode"] == "login"
    key = cfg["anthropic_api_key"] if use_claude else cfg["api_key"]
    if use_claude and not key and not claude_login:
        return {"ok": False, "error": "API key Anthropic belum dikonfigurasi (atau pilih Login). Buka menu Pengaturan."}

    b_url = cfg["base_url"]
    mdl = cfg["model"]
    endpoint = f"{b_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    price = technical.get("price", 0)
    change_pct = technical.get("change_pct", 0)
    rsi = technical.get("rsi14", 50)
    ema20 = technical.get("ema20", 0)
    ema50 = technical.get("ema50", 0)
    ema200 = technical.get("ema200", 0)
    vol_ratio = technical.get("vol_ratio", 1.0)
    is_breakout = technical.get("is_breakout", False)

    cmf = money_flow.get("cmf20", 0.0)
    obv_div = money_flow.get("obv_divergence", "NONE")
    flow_status = money_flow.get("money_flow_status", "NEUTRAL")
    vsa = money_flow.get("vsa_signal", "NORMAL")

    score = composite.get("score", 50)
    confluence_score = composite.get("confluence_score", 0)
    is_confirmed = composite.get("is_confirmed_breakout", False)

    d = direction or {}
    direction_str = (
        f"Skor Arah: {d.get('direction_score', 0):+d}/100 ({d.get('direction_label', '-')}, regime {d.get('regime', '-')}, "
        f"keyakinan {d.get('confidence', 0)}%)\n"
        f"ADX: {d.get('adx', 0)} (+DI {d.get('plus_di', 0)} / -DI {d.get('minus_di', 0)})\n"
        f"Struktur Pasar: {d.get('market_structure', '-')} | BOS: {d.get('break_of_structure', '-')}\n"
        f"Tren Mingguan: {d.get('weekly_trend', '-')} | Divergence RSI: {d.get('rsi_divergence', '-')}\n"
        f"Relative Strength vs Indeks (20h/60h): {d.get('rs_20d_pct', 'N/A')}% / {d.get('rs_60d_pct', 'N/A')}%"
    ) if d else "Tidak tersedia."

    news_str = "\n".join(f"- {n}" for n in (news_headlines or [])[:5]) or "Tidak ada berita spesifik terbaru."

    def _live_line(comp: Dict[str, Any]) -> str:
        lv = comp.get("levels") or {}
        live = lv.get("live") if isinstance(lv, dict) and lv.get("frozen") else None
        if not isinstance(live, dict):
            return ""
        note = ""
        if live.get("buyable_today") is False:
            note = " → rencana ini TIDAK bisa dijalankan hari ini; jangan menyarankan masuk sekarang, nilai untuk rencana berikutnya."
        elif live.get("far_above"):
            note = " → harga sudah jauh di atas zona; masuk sekarang = mengejar, bukan sesuai rencana."
        return (f"POSISI HARGA HARI INI vs RENCANA (rencana dari penutupan {lv.get('as_of', '-')}, harga live): "
                f"{live.get('label', '-')}{note}\n")

    system_prompt = (
        "Anda adalah Kepala Analis Kuantitatif & Ahli Bandarmologi Pasar Modal berpengalaman. "
        "Tugas Anda adalah memvalidasi secara objektif dan ketat apakah sebuah saham memiliki probabilitas tinggi untuk NAIK, "
        "serta mendeteksi potensi JEBAKAN (Bull Trap / Fakeout / Distribusi Terselubung).\n\n"
        "Jawab HANYA dalam format JSON murni tanpa markdown pembungkus tambahan."
    )

    user_prompt = f"""
Analisa data emiten berikut:
TICKER: {ticker} (Pasar: {market})
HARGA SEKARANG: {price} ({change_pct:+}%)
EMA 20: {ema20} | EMA 50: {ema50} | EMA 200: {ema200}
RSI 14: {rsi}
VOLUME RATIO: {vol_ratio}x rata-rata 20 hari
BREAKOUT RESISTANCE 20D: {'YA' if is_breakout else 'TIDAK'}

ARAH TREN (MULTI-FAKTOR):
{direction_str}

ALIRAN DANA & BANDARMOLOGI:
Chaikin Money Flow (CMF 20): {cmf:+.4f} (Status: {flow_status})
OBV Divergence: {obv_div}
VSA Spread: {vsa}
Konfluensi 6-Gate: {confluence_score}/6 ({'CONFIRMED BREAKOUT' if is_confirmed else 'NORMAL'})
STATUS ENGINE (teruji backtest): {(composite.get("action") or {}).get("status", "-")}{" — " + "; ".join((composite.get("action") or {}).get("reasons") or []) if (composite.get("action") or {}).get("reasons") else ""}
Skor Komposit Algoritma: {score}/100
MODE PASAR (kondisi indeks + berita sistemik): {composite.get("market_mode", "NORMAL")} | Status Pullback: {composite.get("pullback_label") or "-"}
(CRASH = indeks turun ≥20% dari puncak 60 hari; BEARISH = indeks downtrend. Dalam mode CRASH/BEARISH jangan memberi STRONG_BUY.)
LEVEL TEKNIS ENGINE (sudah sesuai fraksi harga bursa & support/resistance nyata):
Entry {composite.get("entry_low", "-")}-{composite.get("entry_high", "-")} | Cut Loss {composite.get("stop_loss", "-")} | TP1 {composite.get("target_tp1", "-")} | TP2 {composite.get("target_tp2", "-")} | R:R {composite.get("risk_reward_ratio", "-")}
Gunakan level ini sebagai acuan; jika mengusulkan level lain, harus berada pada fraksi harga BEI yang valid dan dekat struktur support/resistance.
{_live_line(composite)}
BERITA TERBARU:
{news_str}

Berikan output JSON dengan struktur PERSIS berikut:
{{
  "confidence_score": 85,
  "verdict": "STRONG_BUY / SPECULATIVE_BUY / WAIT_AND_SEE / AVOID",
  "bullish_thesis": "Penjelasan ringkas 2-3 kalimat mengapa harga berpotensi naik.",
  "bull_trap_risk": "LOW / MEDIUM / HIGH",
  "bull_trap_analysis": "Analisa apakah kenaikan ini murni akumulasi atau sekadar pancingan ritel.",
  "entry_zone": "Rentang harga ideal untuk masuk",
  "stop_loss": "Level harga cut loss mutlak jika analisis salah",
  "target_tp1": "Target harga realistis terdekat",
  "target_tp2": "Target harga lanjutan",
  "key_catalyst": "Pendorong utama (katalis/volume/trend)"
}}
"""

    if use_claude:
        # Claude returns schema-validated JSON (structured outputs), no fence-stripping needed
        return claude_provider.validate(system_prompt, user_prompt, "" if claude_login else key,
                                        cfg["anthropic_model"], use_login=claude_login)

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": VALIDATE_MAX_TOKENS,
        "reasoning_effort": VALIDATE_REASONING_EFFORT,
        "stream": False
    }

    started = time.time()
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=VALIDATE_TIMEOUT)
        if resp.status_code == 400 and "reasoning" in resp.text.lower():
            # A model behind the gateway that does not accept reasoning_effort: ask again without it
            payload.pop("reasoning_effort")
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=VALIDATE_TIMEOUT)
        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"Error dari gateway AI ({resp.status_code}) untuk model {mdl}: {resp.text[:250]}"
            }

        data = resp.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") in ("length", "max_tokens"):
            return {"ok": False, "error": f"Jawaban model {mdl} terpotong (batas {VALIDATE_MAX_TOKENS} token). "
                                          "Coba lagi atau pilih model lain."}
        content = (choice["message"].get("content") or "").strip()

        # Clean markdown code fences if model returned ```json ... ```
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        parsed = json.loads(content)
        parsed["ok"] = True
        parsed["model_used"] = data.get("model") or mdl
        parsed["elapsed_ms"] = int((time.time() - started) * 1000)
        return parsed

    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"Timeout: model {mdl} tidak merespons dalam {VALIDATE_TIMEOUT} detik."}

    except json.JSONDecodeError:
        # Never dress engine heuristics up as the model's verdict
        return {"ok": False, "error": f"Jawaban model {mdl} bukan JSON yang valid. Coba lagi atau pilih model lain."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Gagal menghubungi 9router: {str(e)}"}

PROVIDER_LABELS = {
    "ag": "Antigravity (ag/)", "cc": "Claude Code (cc/)", "cx": "Codex (cx/)", "gemini": "Gemini (gemini/)",
    "gc": "Gemini CLI (gc/)", "gh": "GitHub Copilot (gh/)", "th": "th/", "openrouter": "OpenRouter",
    "nvidia": "NVIDIA", "ollama": "Ollama",
}
# 'all/' and 'All/' are 9router's cross-provider aliases (~1.500 duplicates of the per-provider
# models); they are counted but not listed so the picker stays usable.
ALIAS_PREFIXES = ("all", "All")


def parse_router_models(models_list: List[Any]) -> Dict[str, Any]:
    """Split an OpenAI-style /models list into 9router combos and per-provider groups."""
    combos, groups, alias_count = [], {}, 0
    for m in models_list:
        mid = m.get("id") if isinstance(m, dict) else (m if isinstance(m, str) else None)
        if not mid:
            continue
        info = m if isinstance(m, dict) else {}
        cap = info.get("capabilities") or {}
        entry = {
            "id": mid,
            "context_length": info.get("context_length") or cap.get("contextWindow"),
            "max_output": info.get("max_completion_tokens") or cap.get("maxOutput"),
            "reasoning": cap.get("reasoning"),
            "vision": cap.get("vision"),
            "tools": cap.get("tools"),
        }
        owner = info.get("owned_by")
        if owner == "combo":
            combos.append(entry)
            continue
        prefix = mid.split("/", 1)[0] if "/" in mid else (owner or "lainnya")
        if prefix in ALIAS_PREFIXES:
            alias_count += 1
            continue
        groups.setdefault(prefix, []).append(entry)
    ordered = sorted(groups.items(), key=lambda kv: (kv[0] not in PROVIDER_LABELS, -len(kv[1]), kv[0]))
    group_list = [{"provider": k, "label": PROVIDER_LABELS.get(k, f"{k}/"), "models": v} for k, v in ordered]
    flat = [c["id"] for c in combos] + [m["id"] for g in group_list for m in g["models"]]
    return {"combos": combos, "groups": group_list, "models": flat, "alias_count": alias_count}


# 9router's /models is ~700 KB and takes 8-15 s; the list only changes when an account is
# connected, and "Deteksi" / the accounts card's refresh bypass the cache.
ROUTER_CACHE_TTL = 600
_router_cache: Dict[str, Any] = {}
_router_locks: Dict[str, threading.Lock] = {}
_router_locks_guard = threading.Lock()


class RouterError(Exception):
    """Raised with a user-facing message when the gateway's /models cannot be read."""


def get_router_models(b_url: str, key: str, force: bool = False) -> List[Any]:
    """The gateway's raw /models list, cached briefly and fetched once even when several
    requests (provider switch + accounts card) arrive together."""
    cache_key = f"{b_url}|{key}"
    with _router_locks_guard:
        lock = _router_locks.setdefault(cache_key, threading.Lock())
    with lock:
        hit = _router_cache.get(cache_key)
        if hit and not force and time.time() - hit[0] < ROUTER_CACHE_TTL:
            return hit[1]
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            resp = requests.get(f"{b_url}/models", headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            raise RouterError(f"Tidak bisa menghubungi {b_url}: {e}")
        if resp.status_code in (401, 403):
            raise RouterError("Server meminta API key yang valid untuk daftar model.")
        if resp.status_code != 200:
            raise RouterError(f"Endpoint {b_url}/models merespons HTTP {resp.status_code}.")
        try:
            data = resp.json()
        except ValueError:
            raise RouterError("Respons /models bukan JSON.")
        models = data.get("data", []) if isinstance(data, dict) else data
        _router_cache[cache_key] = (time.time(), models)
        return models


def fetch_ai_models(base_url: Optional[str] = None, api_key: Optional[str] = None,
                    provider: Optional[str] = None, auth_mode: Optional[str] = None,
                    refresh: bool = False) -> Dict[str, Any]:
    """Detect what the configured provider really offers.

    9router / OpenAI-compatible: GET {base_url}/models. 9router marks its combos with
    owned_by == "combo"; nothing is hard-coded, so new or renamed combos show up as they are.
    A key is sent only when one is set (a local 9router does not require it).
    Claude: the Anthropic Models API for the given key.
    """
    cfg = get_ai_config()
    prov = provider or cfg["provider"]
    if prov == ANTHROPIC:
        use_login = (auth_mode or cfg["anthropic_auth_mode"]) == "login"
        return claude_provider.list_models("" if use_login else (api_key if api_key else cfg["anthropic_api_key"]),
                                           use_login=use_login)

    b_url = (base_url or cfg["base_url"]).rstrip("/")
    key = api_key if api_key is not None else _stored_key_for(b_url, cfg)
    try:
        models = get_router_models(b_url, key, force=refresh)
    except RouterError as e:
        return {"ok": False, "models": [], "combos": [], "groups": [], "message": str(e)}
    return _shape_for_provider(prov, parse_router_models(models))


def _shape_for_provider(prov: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Antigravity/Codex: only their own models. 9router: combos + everything except hidden prefixes."""
    if prov in GATEWAY_PROVIDERS:
        prefix = GATEWAY_PROVIDERS[prov]
        groups = [g for g in parsed["groups"] if g["provider"] == prefix]
        models = [m["id"] for g in groups for m in g["models"]]
        label = "Antigravity" if prov == "antigravity" else "Codex"
        return {"ok": bool(models), "combos": [], "groups": groups, "models": models,
                "message": (f"Akun {label} terhubung di 9router — {len(models)} model tersedia." if models else
                            f"Belum ada akun {label} yang terhubung di 9router. Klik Login {label} untuk menghubungkan.")}
    groups = [g for g in parsed["groups"] if g["provider"] not in HIDDEN_IN_9ROUTER]
    models = [c["id"] for c in parsed["combos"]] + [m["id"] for g in groups for m in g["models"]]
    n_models = sum(len(g["models"]) for g in groups)
    return {
        "ok": True, "combos": parsed["combos"], "groups": groups, "models": models, "alias_count": parsed["alias_count"],
        "message": f"Terdeteksi {len(parsed['combos'])} combo dan {n_models} model dari {len(groups)} penyedia"
                   + (f" (+{parsed['alias_count']} alias all/ disembunyikan)." if parsed["alias_count"] else "."),
    }


# Accounts that can be signed in inside 9router (prefix → display name)
ROUTER_ACCOUNTS = [
    ("ag", "Antigravity"), ("cx", "Codex (ChatGPT)"), ("cc", "Claude Code"), ("gc", "Gemini CLI"),
    ("gh", "GitHub Copilot"), ("gemini", "Gemini API"), ("openrouter", "OpenRouter"), ("nvidia", "NVIDIA"),
    ("ollama", "Ollama"), ("th", "th"),
]


def router_dashboard_url(base_url: str) -> str:
    root = re.sub(r"/v\d+/?$", "", base_url.rstrip("/"))
    return f"{root}/dashboard/providers"


def list_router_accounts(base_url: Optional[str] = None, api_key: Optional[str] = None,
                         refresh: bool = False) -> Dict[str, Any]:
    """Which AI accounts are connected in 9router (inferred from the models it exposes)."""
    cfg = get_ai_config()
    b_url = (base_url or cfg["base_url"]).rstrip("/")
    key = api_key if api_key is not None else _stored_key_for(b_url, cfg)
    try:
        models = get_router_models(b_url, key, force=refresh)
    except RouterError as e:
        return {"ok": False, "accounts": [], "dashboard_url": router_dashboard_url(b_url), "message": str(e)}
    parsed = parse_router_models(models)
    counts = {g["provider"]: len(g["models"]) for g in parsed["groups"]}
    accounts = [{"prefix": p, "name": n, "connected": counts.get(p, 0) > 0, "models_count": counts.get(p, 0)}
                for p, n in ROUTER_ACCOUNTS]
    return {"ok": True, "accounts": accounts, "dashboard_url": router_dashboard_url(b_url),
            "message": f"{sum(a['connected'] for a in accounts)} akun AI terhubung di 9router."}
