"""Settings API, 5-gate confluence, screener cache round-trip, AI test-connection (temp DB, offline)."""
import pytest

from engine.db import get_screener_results, save_screener_result
from engine.screener.scoring import evaluate_confluence_breakout


def test_settings_roundtrip(client):
    # conftest points SAHAM_DB_PATH at a temp DB, so this never touches the user's real AI settings
    res = client.post("/api/settings", json={
        "provider": "9router",
        "base_url": "https://api.9router.com/v1",
        "model": "deepseek-chat",
        "api_key": "test-antigravity-key-12345"
    })
    assert res.status_code == 200, res.text
    data = client.get("/api/settings").json()
    assert data["provider"] == "9router"
    assert data["base_url"] == "https://api.9router.com/v1"
    assert data["is_api_key_set"] is True
    assert data["masked_api_key"].startswith("test")


TECH = {
    "price": 10500, "high_20d": 10400, "low_20d": 9800, "ema20": 10200, "ema50": 9900,
    "ema200": 9200, "vol_ratio": 2.1, "is_breakout": True,
    # Structure for the trade plan: tight ATR, recent swing low just under entry, resistance 11200.
    # SL = max(min(10300, 10290 - 1.2*100, 10500 - 100), 10500*0.92) = 10170 -> risk 330
    # TP1 = max(11200, 10500 + 1.8*100) = 11200 -> reward 700 -> R:R 2.12
    "atr14": 100, "recent_low_5d": 10300, "prev_20d_high": 11200,
}
FLOW = {"cmf20": 0.12, "vol_ratio": 2.1, "money_flow_status": "STRONG_INFLOW"}


def test_confluence_breakout_confirmed_with_good_rr():
    c = evaluate_confluence_breakout(TECH, FLOW)
    assert c["is_confirmed_breakout"] is True
    assert c["confluence_score"] >= 4
    assert c["confluence_gates"]["gate_risk_reward"] is True
    assert c["stop_loss"] == pytest.approx(10170)
    assert c["target_tp1"] == pytest.approx(11200)
    assert c["risk_reward_ratio"] == pytest.approx(2.12)


def test_confluence_wide_stop_gives_poor_rr():
    # Default ATR (2% of price) and a 5% swing low: risk 525 vs reward 500 -> R:R < 1, gate fails
    tech = {k: v for k, v in TECH.items() if k not in ("atr14", "recent_low_5d")}
    tech["prev_20d_high"] = 11000
    c = evaluate_confluence_breakout(tech, FLOW)
    assert c["risk_reward_ratio"] == pytest.approx(0.95)
    assert c["confluence_gates"]["gate_risk_reward"] is False


def test_screener_cache_roundtrip():
    save_screener_result({
        "ticker": "TEST.JK", "market": "IDX", "price": 5000, "change_pct": 2.5, "volume": 1000000,
        "rsi14": 55.0, "cmf20": 0.15, "vol_ratio": 1.8, "money_flow_status": "STRONG_INFLOW",
        "sentiment_label": "BULLISH", "catalyst": "Ekspansi bisnis baru", "score": 88,
        "verdict": "STRONG_BUY", "badge_text": "AKUMULASI BESAR",
        "reasons": ["Smart money inflow CMF +0.15", "Breakout resistance 20 hari"],
        "is_confirmed_breakout": True, "confluence_score": 5
    })
    found = next((x for x in get_screener_results("IDX") if x["ticker"] == "TEST.JK"), None)
    assert found is not None
    assert found["reasons"] == ["Smart money inflow CMF +0.15", "Breakout resistance 20 hari"]
    assert found["is_confirmed_breakout"] is True
    assert found["confluence_score"] == 5


def test_ai_test_connection_structured_on_failure(client):
    res = client.post("/api/ai/test-connection", json={
        "base_url": "https://api.9router.com/v1", "api_key": "invalid-dummy-key", "model": "deepseek-chat"
    })
    assert res.status_code == 200
    assert res.json()["ok"] is False
