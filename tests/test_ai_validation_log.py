"""AI validation track record: recording, outcome measurement and grouping (offline)."""
import numpy as np
import pandas as pd

from engine.ai import validation_log as vl


def _df(closes, start="2026-10-01", lows=None, highs=None):
    dates = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"date": dates, "open": c, "close": c,
                         "high": np.asarray(highs, float) if highs is not None else c * 1.01,
                         "low": np.asarray(lows, float) if lows is not None else c * 0.99, "volume": 1e6})


AI_OK = {"ok": True, "verdict": "speculative_buy", "confidence_score": 70, "model_used": "claude-sonnet-5-5",
         "bull_trap_risk": "LOW", "entry_zone": "2930-3020", "stop_loss": "2790", "target_tp1": "3150",
         "target_tp2": "3400"}
COMP = {"score": 72, "verdict": "MILD_BULLISH", "market_mode": "NORMAL", "entry_low": 2930, "entry_high": 3020,
        "stop_loss": 2790, "target_tp1": 3150}


def test_only_successful_validations_are_recorded():
    assert vl.record("PTBA.JK", "IDX", {"ok": False, "error": "x"}, COMP, 3000, "9router", "2026-10-01") is None
    rid = vl.record("PTBA.JK", "IDX", AI_OK, COMP, 3000, "9router", "2026-10-01")
    row = next(r for r in vl._rows("IDX") if r["id"] == rid)
    assert row["ai_verdict"] == "SPECULATIVE_BUY" and row["engine_verdict"] == "MILD_BULLISH" and row["stop_loss"] == 2790


def test_measure_return_excess_and_first_hit():
    row = {"trade_date": "2026-10-01", "price": 3000, "stop_loss": 2790, "target_tp1": 3150}
    closes = [3000] + [3000 + 20 * i for i in range(1, 12)]
    out = vl.measure(row, _df(closes), _df([100] * 12), horizon=10)
    assert out["final"] and out["days"] == 10
    assert out["return_pct"] == round((3200 / 3000 - 1) * 100, 2)
    assert out["excess_pct"] == out["return_pct"]            # flat index
    assert out["first_hit"] == "TP1"
    # a bar that touches both the stop and TP1 counts as the stop
    lows = [2990] + [2700] * 11
    highs = [3010] + [3200] * 11
    assert vl.measure(row, _df(closes, lows=lows, highs=highs), None, 10)["first_hit"] == "SL"
    young = vl.measure(row, _df(closes[:4]), None, 10)
    assert not young["final"] and young["days"] == 3


def test_summary_dedupes_and_groups(monkeypatch):
    with vl.get_connection() as conn:
        vl._ensure_table()
        conn.execute("DELETE FROM ai_validations")
        conn.commit()
    for _ in range(3):  # repeated clicks on the same day count once
        vl.record("PTBA.JK", "IDX", AI_OK, COMP, 3000, "9router", "2026-10-01")
    vl.record("BBCA.JK", "IDX", dict(AI_OK, verdict="AVOID"), dict(COMP, verdict="NEUTRAL"), 5000, "9router", "2026-10-01")
    data = {"PTBA.JK": _df([3000 + 20 * i for i in range(12)]), "BBCA.JK": _df([5000 - 10 * i for i in range(12)])}
    s = vl.summary("IDX", lambda t: data[t], _df([100] * 12), horizon=10)
    assert s["total"] == 2 and s["evaluated"] == 2 and not s["enough_data"]
    by = {g["verdict"]: g for g in s["by_ai_verdict"]}
    assert by["SPECULATIVE_BUY"]["count"] == 1 and by["SPECULATIVE_BUY"]["avg_return_pct"] > 0
    assert by["AVOID"]["avg_return_pct"] < 0
    assert {g["verdict"] for g in s["by_engine_verdict"]} == {"MILD_BULLISH", "NEUTRAL"}
    # final outcomes are stored and reused
    assert all(r["outcome"]["final"] for r in s["recent"])
