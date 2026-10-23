"""Screener metrics: liquidity, returns and price position (offline, synthetic)."""
import numpy as np
import pandas as pd

from engine.indicators.screen_metrics import compute_screen_metrics


def frame(n=260, start=1000.0, drift=0.001, volume=1_000_000.0):
    close = start * np.exp(np.cumsum(np.full(n, drift)))
    return pd.DataFrame({"date": pd.bdate_range("2025-01-01", periods=n), "open": close, "high": close * 1.01,
                         "low": close * 0.99, "close": close, "volume": volume})


def test_liquidity_and_returns():
    df = frame()
    m = compute_screen_metrics(df, {"ema200": float(df.close.iloc[-1]) * 0.9, "atr14": 20.0},
                               {"rs_20d_pct": 3.0, "rs_60d_pct": 8.0, "pullback": {"stretch_atr": 0.5}}, {"market_cap": 1e12})
    price = float(df.close.iloc[-1])
    assert m["avg_value_20d"] == round(float((df.close * df.volume).iloc[-20:].mean()), 0)
    assert m["illiquid"] is False  # ~Rp1,2 miliar/hari
    assert m["ret_1m"] == round((price / float(df.close.iloc[-22]) - 1) * 100, 2)
    assert m["ret_3m"] > m["ret_1m"] > 0
    assert m["rs_60d"] == 8.0 and m["stretch_atr"] == 0.5 and m["market_cap"] == 1e12
    assert m["dist_ema200_pct"] == round((1 / 0.9 - 1) * 100, 2)
    assert -1.5 < m["dist_52w_high_pct"] <= 0


def test_illiquid_flag_and_short_history():
    m = compute_screen_metrics(frame(n=30, volume=1_000.0), {}, None, None)
    assert m["illiquid"] is True
    assert m["ret_3m"] is None and m["ret_6m"] is None and m["dist_ema200_pct"] is None
    assert compute_screen_metrics(frame(volume=1_000.0), {}, None, None, market="US")["illiquid"] is True
