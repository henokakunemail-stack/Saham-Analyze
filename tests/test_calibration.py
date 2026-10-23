"""Offline calibration helpers on a tiny synthetic walk-forward table (no candles, no network)."""
import pandas as pd

from engine.screener.calibration import (
    split, stats, apply_config, by_status, ordered, accepted, evaluate_gates, reweight, top_n,
    bucket_r, monotonic_share, evaluate_weights, best_gate_variant, best_weight_variant, per_day,
    single_changes, WEIGHT_VARIANTS,
)

PV_GOOD = {"pullback": 0.8, "trend": 0.6, "money_flow": 0.2, "momentum": 0.2, "setup": 0.1}
PV_BAD = {"pullback": -0.5, "trend": -0.2, "money_flow": 0.9, "momentum": 0.9, "setup": 0.9}


def row(date, ticker, verdict="MILD_BULLISH", mode="NORMAL", r=0.5, filled=True, status="HIT_TP1",
        risk=5.0, value=10e9, flags="", pv=None, score=70, raw=70, state="PULLBACK_IDEAL"):
    return {"ticker": ticker, "date": pd.Timestamp(date), "score": score, "raw_score": raw,
            "pillar_values": pv or PV_GOOD, "pullback_state": state, "market_mode": mode, "verdict": verdict,
            "rr": 1.0, "risk_pct": risk, "atr_pct": 3.0, "avg_value_20d": value, "rs_60d": 5.0, "flags": flags,
            "plan_status": status if filled or status in ("NOT_FILLED", "CANCELLED") else "NOT_FILLED",
            "filled": filled, "r": r if filled else None, "plan_return_pct": r * 4 if filled else None,
            "bars_held": 3 if filled else None}


def table():
    rows = []
    for d in ("2025-06-02", "2025-06-05", "2026-01-05", "2026-01-08"):
        rows += [
            row(d, "AAA", r=1.0),                                                  # LAYAK, wins
            row(d, "BBB", r=0.8, pv=PV_BAD),                                       # LAYAK
            row(d, "CCC", verdict="NEUTRAL", r=0.1, score=55, raw=55),             # TUNGGU
            row(d, "DDD", risk=9.0, r=0.0, status="EXPIRED"),                       # TUNGGU (risk)
            row(d, "EEE", verdict="MILD_BEARISH", r=-1.0, status="STOPPED_OUT", score=35, raw=35),  # HINDARI
            row(d, "FFF", filled=False, status="NOT_FILLED"),                       # LAYAK, not filled
            row(d, "GGG", mode="CRASH", verdict="NEUTRAL", r=0.3, score=54, raw=75),  # TUNGGU (market)
        ]
    return pd.DataFrame(rows)


def test_split_and_stats():
    t = table()
    ins, oos = split(t, "2025-12-11")
    assert len(ins) == 14 and len(oos) == 14
    s = stats(ins)
    assert s["plans"] == 14 and s["filled"] == 12
    assert s["fill_rate_pct"] == round(100 * 12 / 14, 1)
    assert s["tp_first_pct"] == round(100 * 8 / 12, 1)   # AAA, BBB, CCC, GGG hit TP1 on both dates
    assert s["avg_r"] == round((1.0 + 0.8 + 0.1 + 0.0 - 1.0 + 0.3) * 2 / 12, 3)


def test_status_groups_and_acceptance():
    t = table()
    st = apply_config(t)
    assert st[t["ticker"] == "AAA"].eq("LAYAK").all()
    assert st[t["ticker"] == "DDD"].eq("TUNGGU").all()
    assert st[t["ticker"] == "EEE"].eq("HINDARI").all()
    res = by_status(t, st)
    assert res["LAYAK"]["avg_r"] == 0.9 and res["HINDARI"]["avg_r"] == -1.0
    assert ordered(res)
    assert not accepted(res)          # far fewer than 100 filled LAYAK trades
    # The lenient market + raw-signal variant turns the CRASH leader into LAYAK
    lenient = {"blocked_modes": (), "leaders_only_modes": ("CRASH", "BEARISH"), "signal_basis": "raw"}
    assert apply_config(t, lenient)[t["ticker"] == "GGG"].eq("LAYAK").all()


def test_evaluate_gates_and_choice():
    t = table()
    variants = {
        "default": {},
        "risk10": {"max_risk_pct": 10.0},
        "longgar": {"blocked_modes": (), "leaders_only_modes": ("CRASH",), "signal_basis": "raw"},
    }
    tab = evaluate_gates(t, variants)
    assert list(tab["variant"]) == ["default", "risk10", "longgar"]
    assert {"LAYAK_avg_r", "TUNGGU_avg_r", "HINDARI_avg_r", "LAYAK_filled", "LAYAK_per_day", "ordered"} <= set(tab.columns)
    assert best_gate_variant(tab) is None        # none has 100 filled LAYAK trades
    tab.loc[:, "LAYAK_filled"] = 150
    assert best_gate_variant(tab) == "default"   # highest LAYAK avg R among ordered variants


def test_reweight_top_n_and_monotonicity():
    t = table()
    cur = reweight(t, WEIGHT_VARIANTS["sekarang"])
    assert cur[t["ticker"] == "AAA"].iloc[0] > cur[t["ticker"] == "BBB"].iloc[0]
    flow = reweight(t, {"pullback": 0.0, "trend": 0.0, "money_flow": 1.0, "momentum": 0.0, "setup": 0.0})
    assert flow[t["ticker"] == "BBB"].iloc[0] == 50 + 60 * 0.9
    top = top_n(t, cur, n=2)
    assert len(top) == 2 * t["date"].nunique()
    assert set(top[top["date"] == pd.Timestamp("2025-06-02")]["ticker"]) <= {"AAA", "DDD", "FFF", "GGG", "CCC"}
    assert monotonic_share([0.1, 0.2, 0.3]) == 1.0 and monotonic_share([0.3, 0.2, 0.25]) == 0.5
    assert bucket_r(t.head(3), cur.head(3)) == []        # too few trades for quintiles
    tab = evaluate_weights(t, {"sekarang": WEIGHT_VARIANTS["sekarang"], "flow": {"money_flow": 1.0}}, n=1)
    assert set(tab["variant"]) == {"sekarang", "flow"}
    assert best_weight_variant(tab) in ("sekarang", "flow")


def test_per_day_and_single_changes():
    t = table()
    assert per_day(t, 0) == 0
    base = {"blocked_modes": ("CRASH",), "signal_basis": "verdict", "max_risk_pct": 8.0}
    variants = {"a": dict(base), "b": {**base, "max_risk_pct": 6.0},
                "c": {**base, "max_risk_pct": 6.0, "signal_basis": "raw"}}
    assert single_changes(base, variants) == ["a", "b"]
