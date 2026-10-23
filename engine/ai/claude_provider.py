"""Anthropic Claude provider (official `anthropic` SDK) for SAHAM's AI signal validation.

Kept separate from engine/ai/client.py, which talks to OpenAI-compatible gateways (9router,
OpenAI, custom proxies). This module uses the Messages API directly:
- structured outputs (`output_config.format`) so the verdict is always valid JSON,
- server-side refusal fallbacks (`fallbacks: "default"`) on models that support them,
- the Models API for auto-detecting the models available to the user's key.
"""
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
REQUEST_TIMEOUT = 90.0  # seconds; Claude thinks before answering

# Models that accept the server-side refusal fallback (`fallbacks: "default"`).
# Claude Haiku 5.5 has no server-side fallback, so it is sent without it.
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "confidence_score": {"type": "integer"},
        "verdict": {"type": "string", "enum": ["STRONG_BUY", "SPECULATIVE_BUY", "WAIT_AND_SEE", "AVOID"]},
        "bullish_thesis": {"type": "string"},
        "bull_trap_risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "bull_trap_analysis": {"type": "string"},
        "entry_zone": {"type": "string"},
        "stop_loss": {"type": "string"},
        "target_tp1": {"type": "string"},
        "target_tp2": {"type": "string"},
        "key_catalyst": {"type": "string"},
    },
    "required": ["confidence_score", "verdict", "bullish_thesis", "bull_trap_risk", "bull_trap_analysis",
                 "entry_zone", "stop_loss", "target_tp1", "target_tp2", "key_catalyst"],
    "additionalProperties": False,
}


def _client(api_key: str = "") -> anthropic.Anthropic:
    """With a key: that key. Without one: the SDK resolves the signed-in Anthropic profile
    (`ant auth login`, stored in the Anthropic config folder under APPDATA)."""
    if api_key:
        return anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)
    # Login mode: an exported ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN would silently win over
    # the signed-in profile, so they are hidden while the client resolves its credentials.
    with _env_lock:
        saved = {k: os.environ.pop(k) for k in _SHADOWING_ENV if k in os.environ}
        try:
            return anthropic.Anthropic(timeout=REQUEST_TIMEOUT, max_retries=2)
        finally:
            os.environ.update(saved)


_SHADOWING_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_env_lock = threading.Lock()


_NO_CREDENTIAL_MARKERS = ("Could not resolve authentication method", "Config file not found")


def _missing_credentials(e: Exception) -> bool:
    """No API key and no signed-in profile (raised by the SDK before any request is sent)."""
    return any(m in str(e) for m in _NO_CREDENTIAL_MARKERS)


def probe_login() -> Dict[str, Any]:
    """Is there a usable signed-in profile? (no API key involved)"""
    try:
        n = len(list(_client("").models.list()))
        return {"logged_in": True, "models_count": n, "message": f"Login aktif — {n} model Claude tersedia."}
    except anthropic.AuthenticationError:
        return {"logged_in": False, "login_expired": True, "message": "Sesi login kedaluwarsa — login ulang."}
    except Exception as e:  # noqa: BLE001
        if _missing_credentials(e):
            return {"logged_in": False, "message": "Belum login ke akun Anthropic."}
        return {"logged_in": None, "message": _error_message(e)}


def _error_message(e: Exception) -> str:
    """Map SDK exceptions (most specific first) to an Indonesian message for the UI."""
    if _missing_credentials(e):
        return "Belum login ke akun Anthropic dan API key kosong."
    if isinstance(e, anthropic.AuthenticationError):
        return "API key Anthropic tidak valid."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "API key tidak punya izin untuk model ini."
    if isinstance(e, anthropic.NotFoundError):
        return "Model tidak ditemukan — pilih model dari daftar Auto-Detect."
    if isinstance(e, anthropic.RateLimitError):
        return "Batas pemakaian Anthropic tercapai (rate limit). Coba lagi sebentar."
    if isinstance(e, anthropic.BadRequestError):
        if "credit balance is too low" in str(e).lower():
            # API credits are separate from a claude.ai Pro/Max subscription
            return ("Saldo kredit API Anthropic habis. Langganan Claude Pro/Max (claude.ai) tidak termasuk kredit API — "
                    "isi kredit di console.anthropic.com → Settings → Billing, lalu tes lagi.")
        return f"Permintaan ditolak: {e.message}"
    if isinstance(e, anthropic.APIStatusError):
        return f"Server Anthropic error ({e.status_code}). Coba lagi nanti."
    if isinstance(e, anthropic.APITimeoutError):
        return "Timeout: Claude tidak merespons tepat waktu."
    if isinstance(e, anthropic.APIConnectionError):
        return "Tidak bisa terhubung ke api.anthropic.com — periksa koneksi internet."
    return f"Gagal memanggil Claude: {e}"


def test_connection(api_key: str, model: Optional[str] = None, use_login: bool = False) -> Dict[str, Any]:
    if not api_key and not use_login:
        return {"ok": False, "message": "API key Anthropic belum diisi (format sk-ant-...)."}
    mdl = model or DEFAULT_MODEL
    start = time.time()
    try:
        resp = _client("" if use_login else api_key).messages.create(
            model=mdl,
            max_tokens=1024,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Ping test: balas dengan satu kata OK."}],
        )
    except Exception as e:  # noqa: BLE001 - mapped to a user-facing message
        return {"ok": False, "message": _error_message(e)}
    latency = int((time.time() - start) * 1000)
    return {"ok": True, "latency_ms": latency, "model": resp.model,
            "message": f"Koneksi Claude berhasil ({resp.model}) - Latency: {latency}ms"}


def list_models(api_key: str, use_login: bool = False) -> Dict[str, Any]:
    """Models available to this key (or signed-in account), with the default pinned on top."""
    if not api_key and not use_login:
        return {"ok": False, "models": [DEFAULT_MODEL], "groups": [],
                "message": "Isi API key Anthropic (atau login) untuk mendeteksi model yang tersedia."}
    try:
        models = list(_client("" if use_login else api_key).models.list())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "models": [DEFAULT_MODEL], "groups": [], "message": _error_message(e)}
    ids: List[str] = [m.id for m in models]
    if DEFAULT_MODEL in ids:
        ids.remove(DEFAULT_MODEL)
        ids.insert(0, DEFAULT_MODEL)
    details = [{"id": m.id, "label": getattr(m, "display_name", m.id),
                "context_length": getattr(m, "max_input_tokens", None),
                "max_output": getattr(m, "max_tokens", None)} for m in models]
    return {
        "ok": True,
        "models": ids,
        "combos": [],
        "groups": [{"provider": "anthropic", "label": "Claude (Anthropic)", "models": details}],
        "message": f"Berhasil mendeteksi {len(ids)} model Claude untuk API key ini.",
    }


def validate(system_prompt: str, user_prompt: str, api_key: str, model: Optional[str] = None,
             use_login: bool = False) -> Dict[str, Any]:
    """Run the signal-validation prompt on Claude and return the verdict dict (+ ok/model_used)."""
    if not api_key and not use_login:
        return {"ok": False, "error": "API key Anthropic belum diisi (atau login belum dilakukan). Buka menu Pengaturan."}
    mdl = model or DEFAULT_MODEL
    kwargs: Dict[str, Any] = dict(
        model=mdl,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
    )
    try:
        client = _client("" if use_login else api_key)
        if mdl in _FALLBACK_MODELS:
            # Opt-in server-side fallback: a safety decline is re-run on Anthropic's recommended model
            resp = client.beta.messages.create(betas=[_FALLBACK_BETA], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        if _missing_credentials(e):
            return {"ok": False, "error": "Belum login ke akun Anthropic. Buka Pengaturan → Claude → Login."}
        return {"ok": False, "error": _error_message(e)}

    if resp.stop_reason == "refusal":
        category = getattr(getattr(resp, "stop_details", None), "category", None)
        return {"ok": False, "error": f"Claude menolak permintaan ini (kategori: {category or 'tidak disebutkan'})."}
    if resp.stop_reason == "max_tokens":
        return {"ok": False, "error": "Jawaban Claude terpotong (max_tokens). Coba lagi."}

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Format jawaban Claude tidak valid."}
    parsed["ok"] = True
    parsed["model_used"] = resp.model
    return parsed
