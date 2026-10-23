"""Analisa Penutupan: honest assessment from the final close, panel rows, recap on final bars only."""
import pandas as pd
from fastapi.testclient import TestClient

from engine.screener import closing_review as cr
from engine.screener import session_recap as sr

LV = {"price": 4800, "as_of": "2026-10-23", "recommended_entry": 4740, "entry_low": 4700, "entry_high": 4790,
      "stop_loss": 4450, "target_tp1": 4910, "target_tp2": 5200, "atr14": 100.0, "risk_reward_ratio": 0.59, "flags": []}


def test_fill_chance_follows_the_backtest_table():
    assert cr.fill_chance(4790, 4790, 100) == {"dist_atr": 0.0, "fill_pct": 78}
    assert cr.fill_chance(4830, 4790, 100)["fill_pct"] == 61
    assert cr.fill_chance(4880, 4790, 100)["fill_pct"] == 41
    assert cr.fill_chance(4920, 4790, 100)["fill_pct"] == 25
    assert cr.fill_chance(5000, 4790, 100)["fill_pct"] == 15


def test_assessment_is_specific_and_honest():
    a = cr.assess(LV, {"status": "TUNGGU", "reasons": ["Pasar bearish — hanya untuk saham pemimpin tren"]})
    assert a["verdict"] == "Belum layak dibeli: Pasar bearish — hanya untuk saham pemimpin tren."
    assert a["points"][0] == ("Harga beli 4.740 ada 1,2% di bawah penutupan (0,1× gerak harian) — peluang terisi "
                              "dalam 5 hari bursa ±78% (uji historis).")
    assert a["fill_pct"] == 78 and a["dist_atr"] == 0.1                       # close 0.1 ATR above the zone
    assert "untung kecil dibanding risiko" in a["points"][1]
    layak = cr.assess({**LV, "risk_reward_ratio": 2.4, "target_tp1": 5400}, {"status": "LAYAK", "reasons": []})
    assert layak["verdict"] == "Layak dipasang order beli limit di 4.740." and "sepadan" in layak["points"][1]


def test_target_already_reached_and_volatility_are_said():
    a = cr.assess({**LV, "price": 4950, "flags": ["too_volatile"]}, {"status": "TUNGGU", "reasons": []})
    assert any("sudah tercapai di harga penutupan" in p for p in a["points"])
    assert any("mudah kena cut loss" in p for p in a["points"])
    assert cr.assess({}, None)["points"] == []


def test_build_keeps_top10_order_and_adds_recap_and_watchlist():
    ranked = [{"ticker": f"T{i}.JK", "levels": dict(LV), "action": {"status": "TUNGGU", "reasons": []}} for i in range(12)]
    recap = {"session_date": "2026-10-23", "plan_as_of": "2026-10-22", "counts": {"TP1": 1},
             "rows": [{"ticker": "OLD.JK", "outcome": "TP1", "text": "x"}, {"ticker": "T0.JK", "outcome": "ABOVE", "text": "y"}]}
    out = cr.build(ranked, recap, ["T11.JK"])
    tickers = [r["ticker"] for r in out["rows"]]
    assert tickers[:10] == [f"T{i}.JK" for i in range(10)] and tickers[10:] == ["OLD.JK", "T11.JK"]
    assert out["rows"][0]["recap"]["outcome"] == "ABOVE" and out["rows"][0]["in_top"]
    assert out["rows"][10]["plan"] is None and out["rows"][10]["recap"]["outcome"] == "TP1"
    assert out["rows"][11]["watchlist"] and not out["rows"][11]["in_top"]
    assert out["plan_as_of"] == "2026-10-23" and out["status_history"]["LAYAK"]["avg_r"] == 0.116


def test_recap_ignores_a_bar_that_is_still_trading():
    sr._cache.clear()
    dates = pd.bdate_range(end="2026-10-26", periods=80).strftime("%Y-%m-%d")
    df = pd.DataFrame([{"date": d, "open": 4800, "high": 4820, "low": 4780, "close": 4800, "volume": 1e6} for d in dates])
    df.loc[len(df) - 2, ["open", "high", "low", "close"]] = [4800, 4950, 4780, 4940]   # Fri 23 Oct: final, hit TP1
    df.loc[len(df) - 1, ["open", "high", "low", "close"]] = [4700, 4710, 4400, 4420]   # Mon 26 Oct: still trading
    out = sr.recap("IDX", {"X.JK": "Top 10"}, fetch=lambda t: df,
                   plan_fn=lambda f: {k: LV[k] for k in ("entry_low", "entry_high", "recommended_entry", "stop_loss",
                                                         "target_tp1", "target_tp2", "as_of")},
                   final_fn=lambda d: d != "2026-10-26")
    assert out["session_date"] == "2026-10-23" and out["rows"][0]["outcome"] == "TP1"


def test_closing_review_endpoint(monkeypatch):
    from engine import main
    monkeypatch.setattr(main, "_session_recap", lambda m, ranked, picks: None)
    r = TestClient(main.app).get("/api/plan/closing-review?market=IDX").json()
    assert "rows" in r and "status_history" in r and "session" in r
