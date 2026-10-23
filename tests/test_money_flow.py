"""Technical indicators + money flow on synthetic data; the live yfinance check is a network test."""
import pytest

from engine.indicators.technical import compute_technical_indicators
from engine.indicators.money_flow import compute_money_flow


def _check(df):
    tech = compute_technical_indicators(df)
    assert "rsi14" in tech
    assert 0 <= tech["rsi14"] <= 100
    assert tech["price"] == pytest.approx(float(df["close"].iloc[-1]), rel=1e-6)
    flow = compute_money_flow(df)
    assert "cmf20" in flow
    assert -1 <= flow["cmf20"] <= 1
    assert flow["money_flow_status"]
    return tech, flow


def test_indicators_on_synthetic_series(make_ohlcv):
    _check(make_ohlcv(n=130, seed=5))


def test_inflow_reads_positive_cmf(make_ohlcv):
    df = make_ohlcv(n=130, seed=6)
    # Every bar closes at its high: maximal buying pressure
    df["close"] = df["high"]
    _, flow = _check(df)
    assert flow["cmf20"] > 0.5


@pytest.mark.network
@pytest.mark.parametrize("ticker", ["BBCA.JK", "AAPL"])
def test_live_yfinance(ticker):
    from engine.collectors.market_data import fetch_stock_ohlcv
    df = fetch_stock_ohlcv(ticker, period="6mo", force_refresh=True)
    assert not df.empty, f"Failed to fetch data for {ticker}"
    _check(df)
