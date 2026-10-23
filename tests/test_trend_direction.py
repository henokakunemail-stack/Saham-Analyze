"""Offline tests for the Trend Direction Engine and v3 composite scoring (synthetic data, no network)."""
import numpy as np
import pandas as pd

from engine.indicators.technical import compute_technical_indicators
from engine.indicators.money_flow import compute_money_flow
from engine.indicators.trend import compute_trend_direction, compute_adx, find_pivots
from engine.screener.scoring import compute_composite_score


def make_series(drift: float, n: int = 260, vol: float = 0.012, seed: int = 7, start: float = 1000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = drift + rng.normal(0, vol, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start], close[:-1]])
    spread = np.abs(rng.normal(0, vol, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(800_000, 1_200_000, n).astype(float)
    dates = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def score_of(df, bench=None):
    tech = compute_technical_indicators(df)
    flow = compute_money_flow(df)
    direction = compute_trend_direction(df, bench)
    comp = compute_composite_score(tech, flow, {"sentiment_score": 0.0}, None, direction)
    return direction, comp


SEEDS = range(20)


def test_uptrend_reads_up():
    scores = [compute_trend_direction(make_series(0.003, seed=s))["direction_score"] for s in SEEDS]
    assert np.mean(scores) >= 40, scores
    assert sum(x >= 20 for x in scores) >= 15, scores


def test_downtrend_reads_down_and_is_capped():
    scores = []
    for s in SEEDS:
        direction, comp = score_of(make_series(-0.003, seed=s))
        scores.append(direction["direction_score"])
        if direction["direction_score"] <= -50:
            # No bullish verdict allowed against a strong downtrend
            assert comp["score"] <= 55, comp["score"]
            assert comp["verdict"] in ("NEUTRAL", "MILD_BEARISH", "STRONG_BEARISH")
    assert np.mean(scores) <= -40, scores


def test_driftless_is_neutral_on_average():
    scores = [compute_trend_direction(make_series(0.0, seed=s))["direction_score"] for s in SEEDS]
    assert abs(np.mean(scores)) < 20, scores


def test_uptrend_scores_above_downtrend():
    up = np.mean([score_of(make_series(0.003, seed=s))[1]["score"] for s in SEEDS])
    down = np.mean([score_of(make_series(-0.003, seed=s))[1]["score"] for s in SEEDS])
    assert up > down + 15, (up, down)


def test_relative_strength_uses_benchmark():
    stock = make_series(0.003, seed=11)
    bench = make_series(-0.001, seed=12)
    direction = compute_trend_direction(stock, bench)
    assert "relative_strength" in direction["components"]
    assert direction["rs_60d_pct"] > 0


def test_adx_and_pivots_sane():
    df = make_series(0.004)
    adx, pdi, mdi = compute_adx(df)
    assert 0 <= adx.iloc[-1] <= 100
    assert pdi.iloc[-1] > mdi.iloc[-1]
    highs = find_pivots(df["high"], kind="high")
    assert len(highs) > 5 and all(3 <= i < len(df) - 3 for i in highs)


def test_short_history_does_not_crash():
    direction, comp = score_of(make_series(0.002, n=40))
    assert "direction_score" in direction
    assert 0 <= comp["score"] <= 100


def test_trade_levels_are_ordered():
    _, comp = score_of(make_series(0.003))
    assert comp["stop_loss"] < comp["recommended_entry"] < comp["target_tp1"] < comp["target_tp2"]

