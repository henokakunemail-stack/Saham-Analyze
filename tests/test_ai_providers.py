"""AI providers: 9router combo detection, Claude routing, and secret masking (offline)."""
import json
from types import SimpleNamespace

from engine.ai import client as ai
from engine.ai import claude_provider as cp

import pytest


@pytest.fixture(autouse=True)
def _fresh_router_cache():
    ai._router_cache.clear()
    yield
    ai._router_cache.clear()


ROUTER_MODELS = [
    {"id": "GPT", "owned_by": "combo", "context_length": 272000, "capabilities": {"reasoning": True, "vision": True, "tools": True}},
    {"id": "claude", "owned_by": "combo", "context_length": 1000000, "capabilities": {"reasoning": True}},
    {"id": "ag/gemini-3.8-flash-high", "owned_by": "ag"},
    {"id": "ag/gemini-3.8-flash", "owned_by": "ag"},
    {"id": "cc/claude-opus-5-5", "owned_by": "cc"},
    {"id": "all/ag/gemini-3.8-flash", "owned_by": "all"},
    {"id": "All/cc/claude-opus-5-5", "owned_by": "All"},
]


def test_router_combos_come_from_the_server_not_a_hardcoded_list():
    r = ai.parse_router_models(ROUTER_MODELS)
    assert [c["id"] for c in r["combos"]] == ["GPT", "claude"]
    assert r["combos"][0]["context_length"] == 272000 and r["combos"][0]["vision"] is True
    groups = {g["provider"]: [m["id"] for m in g["models"]] for g in r["groups"]}
    assert groups == {"ag": ["ag/gemini-3.8-flash-high", "ag/gemini-3.8-flash"], "cc": ["cc/claude-opus-5-5"]}
    assert r["alias_count"] == 2                       # all/ and All/ aliases hidden
    assert r["models"][:2] == ["GPT", "claude"]        # combos first in the flat list
    assert "apodex" not in r["models"]                 # no invented combos


def test_fetch_models_works_without_key_and_routes_claude(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"object": "list", "data": ROUTER_MODELS}

    def fake_get(url, headers=None, timeout=None):
        seen["url"], seen["headers"] = url, headers
        return Resp()

    monkeypatch.setattr(ai.requests, "get", fake_get)
    r = ai.fetch_ai_models(base_url="http://localhost:20128/v1", api_key="", provider="9router")
    assert r["ok"] and seen["url"] == "http://localhost:20128/v1/models" and seen["headers"] == {}
    assert "2 combo" in r["message"]

    monkeypatch.setattr(cp, "list_models", lambda key, use_login=False: {"ok": True, "models": ["claude-opus-5-5"], "key": key})
    assert ai.fetch_ai_models(api_key="sk-ant-x", provider="anthropic")["key"] == "sk-ant-x"


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(response):
    msgs = FakeMessages(response)
    return SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs)), msgs


VERDICT = {"confidence_score": 40, "verdict": "WAIT_AND_SEE", "bullish_thesis": "x", "bull_trap_risk": "HIGH",
           "bull_trap_analysis": "y", "entry_zone": "2930-3020", "stop_loss": "2790", "target_tp1": "3100",
           "target_tp2": "3400", "key_catalyst": "z"}


def test_claude_validate_uses_structured_output_and_fallback(monkeypatch):
    resp = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                           content=[SimpleNamespace(type="text", text=json.dumps(VERDICT))])
    client, msgs = fake_client(resp)
    monkeypatch.setattr(cp, "_client", lambda key: client)
    out = cp.validate("sys", "user", "sk-ant-x", "claude-opus-5-5")
    assert out["ok"] and out["verdict"] == "WAIT_AND_SEE" and out["model_used"] == "claude-opus-5-5"
    call = msgs.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in call and "temperature" not in call


def test_claude_haiku_has_no_fallback_and_refusal_is_reported(monkeypatch):
    resp = SimpleNamespace(stop_reason="refusal", model="claude-haiku-5-5", content=[],
                           stop_details=SimpleNamespace(category="cyber"))
    client, msgs = fake_client(resp)
    monkeypatch.setattr(cp, "_client", lambda key: client)
    out = cp.validate("sys", "user", "sk-ant-x", "claude-haiku-5-5")
    assert out["ok"] is False and "cyber" in out["error"]
    assert "fallbacks" not in msgs.calls[0]


def test_claude_requires_key():
    assert cp.validate("s", "u", "", None)["ok"] is False
    assert cp.test_connection("")["ok"] is False


def test_masked_secret_is_never_saved_back(client):
    client.post("/api/settings", json={"provider": "anthropic", "anthropic_api_key": "sk-ant-REALSECRET123"})
    masked = client.get("/api/settings").json()["masked_anthropic_key"]
    assert masked == "sk-a...T123"
    client.post("/api/settings", json={"provider": "anthropic", "anthropic_api_key": masked})
    from engine.db import get_setting
    assert get_setting("anthropic_api_key", "") == "sk-ant-REALSECRET123"


def test_gateway_providers_show_only_their_models_and_9router_hides_antigravity():
    parsed = ai.parse_router_models(ROUTER_MODELS + [{"id": "cx/gpt-6-sol", "owned_by": "cx"}])
    ag = ai._shape_for_provider("antigravity", parsed)
    assert ag["ok"] and ag["models"] == ["ag/gemini-3.8-flash-high", "ag/gemini-3.8-flash"] and ag["combos"] == []
    cx = ai._shape_for_provider("codex", parsed)
    assert cx["models"] == ["cx/gpt-6-sol"]
    router = ai._shape_for_provider("9router", parsed)
    assert not any(m.startswith("ag/") for m in router["models"])
    assert router["models"][:2] == ["GPT", "claude"]
    empty = ai._shape_for_provider("codex", ai.parse_router_models(ROUTER_MODELS))
    assert empty["ok"] is False and "Login Codex" in empty["message"]


def test_router_accounts_and_dashboard_url(monkeypatch):
    class Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": ROUTER_MODELS}
    monkeypatch.setattr(ai.requests, "get", lambda url, headers=None, timeout=None: Resp())
    r = ai.list_router_accounts(base_url="http://localhost:20128/v1", api_key="")
    by = {a["prefix"]: a for a in r["accounts"]}
    assert by["ag"]["connected"] and by["cc"]["connected"] and not by["cx"]["connected"]
    assert r["dashboard_url"] == "http://localhost:20128/dashboard/providers"


def test_open_url_allow_list(client, monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    assert client.post("/api/system/open-url", json={"url": "http://localhost:20128/dashboard/providers"}).status_code == 200
    assert client.post("/api/system/open-url", json={"url": "https://evil.example.com/login"}).status_code == 400
    assert client.post("/api/system/open-url", json={"url": "file:///C:/Windows/System32/calc.exe"}).status_code == 400
    assert opened == ["http://localhost:20128/dashboard/providers"]


def _zip_with_ant(payload=b"MZ-fake-ant"):
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ant.exe", payload)
    return buf.getvalue()


def test_ant_install_accepts_only_the_pinned_checksum(tmp_path, monkeypatch):
    import hashlib
    import pytest
    from engine.ai import anthropic_login as al
    good = _zip_with_ant()
    monkeypatch.setattr(al, "install_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(al, "_arch", lambda: "amd64")
    monkeypatch.setitem(al.ANT_SHA256, "amd64", hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(al, "_download", lambda url: good)
    out = al.install_ant()
    assert (tmp_path / "bin" / "ant.exe").read_bytes() == b"MZ-fake-ant" and out["version"] == al.ANT_VERSION
    (tmp_path / "bin" / "ant.exe").unlink()
    monkeypatch.setattr(al, "_download", lambda url: _zip_with_ant(b"tampered"))
    with pytest.raises(RuntimeError, match="Checksum"):
        al.install_ant()
    assert not (tmp_path / "bin" / "ant.exe").exists()


def test_ant_download_url_and_real_digests_are_pinned():
    from engine.ai import anthropic_login as al
    assert al.ANT_VERSION == "1.44.0"
    assert all(len(v) == 64 for v in al.ANT_SHA256.values())
    assert al._RELEASE.startswith("https://github.com/anthropics/anthropic-cli/releases/download/v1.44.0")


def test_login_probe_without_credentials(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", "C:/nonexistent-saham-test-dir")
    r = cp.probe_login()
    assert r["logged_in"] is False


def test_claude_login_mode_sends_no_key(monkeypatch):
    seen = {}
    resp = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                           content=[SimpleNamespace(type="text", text=json.dumps(VERDICT))])
    client, msgs = fake_client(resp)
    monkeypatch.setattr(cp, "_client", lambda key: seen.setdefault("key", key) or client)
    out = cp.validate("s", "u", "", "claude-opus-5-5", use_login=True)
    assert out["ok"] and seen["key"] == ""


def test_router_models_are_cached_and_concurrent_calls_coalesce(monkeypatch):
    import threading, time as _t
    calls = []

    class Resp:
        status_code = 200
        def json(self): return {"data": ROUTER_MODELS}

    def slow_get(url, headers=None, timeout=None):
        calls.append(url)
        _t.sleep(0.2)
        return Resp()

    monkeypatch.setattr(ai.requests, "get", slow_get)
    results = []
    threads = [threading.Thread(target=lambda: results.append(ai.fetch_ai_models(base_url="http://localhost:20128/v1", api_key="", provider=p)))
               for p in ("9router", "antigravity", "codex")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1 and all(r["combos"] is not None for r in results)
    ai.fetch_ai_models(base_url="http://localhost:20128/v1", api_key="", provider="9router", refresh=True)
    assert len(calls) == 2  # explicit refresh bypasses the cache


def test_zero_credit_balance_gets_a_clear_message():
    import anthropic
    import httpx2
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.BadRequestError(
        "Error code: 400 - Your credit balance is too low to access the Anthropic API.",
        response=httpx2.Response(400, request=req), body=None)
    msg = cp._error_message(err)
    assert "Saldo kredit API Anthropic habis" in msg and "Pro/Max" in msg and "Billing" in msg


class _ChatResp:
    def __init__(self, status=200, content="", finish="stop", text=""):
        self.status_code, self.text = status, text
        self._j = {"model": "claude-sonnet-5-5",
                   "choices": [{"finish_reason": finish, "message": {"content": content}}]}

    def json(self):
        return self._j


def _router_cfg(monkeypatch):
    monkeypatch.setattr(ai, "get_ai_config", lambda: {
        "provider": "9router", "base_url": "http://localhost:20128/v1", "api_key": "", "model": "claude",
        "anthropic_api_key": "", "anthropic_model": "", "anthropic_auth_mode": "api_key"})


def _validate():
    return ai.validate_signal_with_ai("PTBA.JK", "IDX", {"price": 3110}, {}, {"score": 70})


def test_router_validation_asks_for_enough_tokens_and_short_thinking(monkeypatch):
    _router_cfg(monkeypatch)
    sent = []
    monkeypatch.setattr(ai.requests, "post", lambda url, json=None, headers=None, timeout=None:
                        sent.append(json) or _ChatResp(content=__import__("json").dumps(VERDICT)))
    out = _validate()
    assert out["ok"] and out["model_used"] == "claude-sonnet-5-5" and "elapsed_ms" in out
    assert sent[0]["max_tokens"] >= 2000 and sent[0]["reasoning_effort"] == "low"


def test_truncated_or_broken_answer_is_reported_not_faked(monkeypatch):
    _router_cfg(monkeypatch)
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: _ChatResp(content='{"verdict": "WAIT', finish="length"))
    out = _validate()
    assert out["ok"] is False and "terpotong" in out["error"]
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: _ChatResp(content="Saya rasa saham ini bagus"))
    out = _validate()
    assert out["ok"] is False and "bukan JSON" in out["error"]


def test_model_without_reasoning_effort_is_asked_again_without_it(monkeypatch):
    _router_cfg(monkeypatch)
    sent = []

    def post(url, json=None, headers=None, timeout=None):
        sent.append(dict(json))
        if "reasoning_effort" in json:
            return _ChatResp(status=400, text="Unknown parameter: reasoning_effort")
        return _ChatResp(content=__import__("json").dumps(VERDICT))

    monkeypatch.setattr(ai.requests, "post", post)
    assert _validate()["ok"] and len(sent) == 2 and "reasoning_effort" not in sent[1]


def test_bare_code_resolves_to_the_exchange_that_has_data(client, monkeypatch):
    import pandas as pd
    from engine import main
    have = {"MSFT", "BBCA.JK"}
    monkeypatch.setattr(main, "fetch_stock_ohlcv", lambda t, period="1y", **k:
                        pd.DataFrame({"close": [1.0]}) if t in have else pd.DataFrame())
    assert client.get("/api/stock/MSFT/resolve?market=IDX").json() == {"ticker": "MSFT", "market": "US"}
    assert client.get("/api/stock/BBCA/resolve?market=IDX").json() == {"ticker": "BBCA.JK", "market": "IDX"}
    assert client.get("/api/stock/BBCA/resolve?market=US").json() == {"ticker": "BBCA.JK", "market": "IDX"}
    assert client.get("/api/stock/ZZZZ/resolve?market=IDX").status_code == 404


def test_validation_prompt_tells_the_ai_when_todays_plan_is_over(monkeypatch):
    _router_cfg(monkeypatch)
    sent = []
    monkeypatch.setattr(ai.requests, "post", lambda url, json=None, headers=None, timeout=None:
                        sent.append(json) or _ChatResp(content=__import__("json").dumps(VERDICT)))
    comp = {"score": 70, "levels": {"frozen": True, "as_of": "2026-10-22", "live": {
        "status": "AT_TP1", "label": "Sudah di TP1 — jangan dikejar", "buyable_today": False}}}
    assert ai.validate_signal_with_ai("BDMN.JK", "IDX", {"price": 4940}, {}, comp)["ok"]
    prompt = sent[0]["messages"][1]["content"]
    assert "POSISI HARGA HARI INI vs RENCANA" in prompt and "TIDAK bisa dijalankan hari ini" in prompt
    sent.clear()
    assert ai.validate_signal_with_ai("BDMN.JK", "IDX", {"price": 4940}, {}, {"score": 70})["ok"]
    assert "POSISI HARGA HARI INI" not in sent[0]["messages"][1]["content"]   # after the close: no live line
