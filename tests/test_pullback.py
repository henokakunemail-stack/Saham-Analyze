"""Pullback-in-uptrend setup (indicators/pullback.py), scoring v4 and market modes (offline, synthetic)."""
import numpy as np
import pandas as pd

from engine.indicators.technical import compute_technical_indicators
from engine.indicators.money_flow import compute_money_flow
from engine.indicators.trend import compute_trend_direction
from engine.screener.scoring import compute_composite_score
from engine.screener.sentiment import assess_market_news_risk


def build(path_returns, seed=5, start=1000.0, vol=0.004):
    """OHLCV from a deterministic daily-return path plus small noise."""
    rng = np.random.default_rng(seed)
    rets = np.asarray(path_returns) + rng.normal(0, vol, len(path_returns))
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start], close[:-1]])
    spread = np.abs(rng.normal(0, vol, len(close))) * close + close * 0.002
    dates = pd.bdate_range("2025-01-01", periods=len(close))
    return pd.DataFrame({
        "date": dates, "open": open_, "high": np.maximum(open_, close) + spread,
        "low": np.minimum(open_, close) - spread, "close": close,
        "volume": rng.integers(800_000, 1_200_000, len(close)).astype(float),
    })


def score(df, regime=None, bench=None):
    tech = compute_technical_indicators(df)
    flow = compute_money_flow(df)
    d = compute_trend_direction(df, bench)
    return d, compute_composite_score(tech, flow, {"sentiment_score": 0.0}, None, d, regime)


# Steady 8-month climb, then a gentle 6-day dip back toward EMA20
PULLBACK = [0.003] * 240 + [-0.006] * 6
# Same climb, then a vertical 10-day spike
EXTENDED = [0.003] * 236 + [0.025] * 10
# Climb, then a 25-day collapse well below the prior swing lows
BROKEN = [0.003] * 220 + [-0.012] * 26
# Long decline
DOWNTREND = [-0.003] * 246


def test_states_are_classified():
    assert compute_trend_direction(build(PULLBACK))["pullback"]["state"] in ("PULLBACK_IDEAL", "UPTREND_RUNNING")
    assert compute_trend_direction(build(EXTENDED))["pullback"]["state"] == "UPTREND_EXTENDED"
    assert compute_trend_direction(build(BROKEN))["pullback"]["state"] in ("TREND_BROKEN", "NO_UPTREND")
    assert compute_trend_direction(build(DOWNTREND))["pullback"]["state"] == "NO_UPTREND"


def test_score_never_contradicts_state():
    for path in (PULLBACK, EXTENDED, BROKEN, DOWNTREND):
        for seed in range(8):
            pb = compute_trend_direction(build(path, seed=seed))["pullback"]
            if pb["state"] in ("NO_UPTREND", "TREND_BROKEN"):
                assert pb["score"] <= 0.15, pb
            if pb["state"] == "UPTREND_EXTENDED":
                assert pb["score"] <= 0.25, pb


def test_pullback_outscores_chasing_and_downtrend():
    # Only paths whose dip stayed above the last swing low are real pullbacks
    pulls = [score(build(PULLBACK, seed=s)) for s in range(12)]
    pull = np.mean([c["score"] for d, c in pulls if d["pullback"]["state"] == "PULLBACK_IDEAL"])
    chase = np.mean([score(build(EXTENDED, seed=s))[1]["score"] for s in range(8)])
    down = np.mean([score(build(DOWNTREND, seed=s))[1]["score"] for s in range(8)])
    assert pull > chase, (pull, chase)
    assert chase <= 64  # overheated: "tunggu pullback", never a bullish verdict
    assert pull > down + 15, (pull, down)


def test_short_history_has_no_pullback_pillar():
    d, comp = score(build([0.003] * 80))
    assert d["pullback"]["state"] == "INSUFFICIENT_DATA"
    assert "pullback" not in comp["pillars"]


def _index_regime(path):
    return compute_trend_direction(build(path, seed=99))


def test_crash_mode_blocks_bullish_verdicts():
    # Index: long rise, then -25% in the last 30 sessions (like IHSG after the MSCI news)
    crash_regime = _index_regime([0.001] * 216 + [-0.0095] * 30)
    assert crash_regime["pullback"]["drawdown_60d_pct"] <= -20
    _, comp = score(build(PULLBACK), regime=crash_regime)
    assert comp["market_mode"] == "CRASH"
    assert comp["score"] <= 55
    assert comp["verdict"] not in ("STRONG_BULLISH", "MILD_BULLISH")
    assert any("Pasar Krisis" in r for r in comp["reasons"])


def test_bear_market_is_defensive_but_normal_market_is_not():
    bear = _index_regime([-0.002] * 246)
    _, in_bear = score(build(PULLBACK), regime=bear)
    _, normal = score(build(PULLBACK), regime=None)
    assert in_bear["market_mode"] in ("BEARISH", "CAUTIOUS", "CRASH")
    assert normal["market_mode"] == "NORMAL"
    assert in_bear["score"] <= normal["score"]


def test_market_news_risk_levels():
    assert assess_market_news_risk([])["level"] == "NONE"
    assert assess_market_news_risk([{"title": "BBRI bagi dividen"}])["level"] == "NONE"
    high = assess_market_news_risk([
        {"title": "MSCI usul Indonesia turun ke standalone market"},
        {"title": "IHSG ambruk 10%, BEI lakukan trading halt"},
        {"title": "Arus keluar modal asing berlanjut, rupiah anjlok"},
    ])
    assert high["level"] == "HIGH" and len(high["headlines"]) == 3


def test_news_risk_alone_makes_market_cautious():
    regime = {"direction_score": 0, "news_risk": {"level": "HIGH", "score": 9, "headlines": []}}
    _, comp = score(build(PULLBACK), regime=regime)
    assert comp["market_mode"] == "CAUTIOUS"


def test_crash_reason_is_always_first():
    crash_regime = _index_regime([0.001] * 216 + [-0.0095] * 30)
    for path in (PULLBACK, EXTENDED, DOWNTREND):
        _, comp = score(build(path), regime=crash_regime)
        assert comp["reasons"][0].startswith("⛔"), comp["reasons"]
