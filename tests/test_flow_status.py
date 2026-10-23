"""money_flow_status must never contradict a clear 20-day CMF reading."""
import numpy as np
import pandas as pd

from engine.indicators.money_flow import compute_money_flow


def frame(close_pos: float, n: int = 60, seed: int = 0, last_bar=None):
    """Bars that close at `close_pos` of their range (0 = at the low, 1 = at the high)."""
    rng = np.random.default_rng(seed)
    close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    high = close * 1.02
    low = close * 0.98
    c = low + (high - low) * close_pos
    df = pd.DataFrame({"date": pd.bdate_range("2026-01-01", periods=n), "open": close, "high": high,
                       "low": low, "close": c, "volume": rng.integers(900_000, 1_100_000, n).astype(float)})
    if last_bar:
        for k, v in last_bar.items():
            df.loc[df.index[-1], k] = v
    return df


def test_strong_negative_cmf_is_never_inflow():
    for seed in range(10):
        # 20 days of closes near the lows, then one high-volume bar closing near its high (VSA-bullish look)
        df = frame(0.1, seed=seed)
        last = df.iloc[-1]
        df.loc[df.index[-1], ["close", "volume"]] = [last["low"] + 0.9 * (last["high"] - last["low"]), last["volume"] * 2]
        flow = compute_money_flow(df)
        if flow["cmf20"] <= -0.12:
            assert flow["money_flow_status"] in ("STRONG_OUTFLOW", "MILD_OUTFLOW"), flow


def test_strong_positive_cmf_is_never_outflow():
    for seed in range(10):
        flow = compute_money_flow(frame(0.9, seed=seed))
        if flow["cmf20"] >= 0.12:
            assert flow["money_flow_status"] in ("STRONG_INFLOW", "MILD_INFLOW"), flow


def test_flow_proxy_summary():
    from engine.indicators.money_flow import summarize_flow_proxy
    df = frame(0.8, seed=1)
    s = summarize_flow_proxy(df, compute_money_flow(df))
    assert s["available"] and "bukan data broker" in s["disclaimer"]
    assert s["up_days"] + s["down_days"] <= 20
    assert s["pressure"] in ("BELI", "JUAL", "SEIMBANG")
    assert s["biggest_volume_day"]["volume_x_avg"] >= 1.0
    assert summarize_flow_proxy(df.iloc[:10], {})["available"] is False
