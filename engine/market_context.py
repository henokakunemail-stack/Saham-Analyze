"""Shared market context: benchmark index candles + market regime, and flat trend fields.

Owned by the integration layer. Other modules import from here instead of engine.main
to avoid circular imports.
"""
import time
from typing import Dict, Any, Optional

import pandas as pd

from .collectors.market_data import fetch_stock_ohlcv
from .indicators.trend import compute_trend_direction

BENCHMARKS = {"IDX": "^JKSE", "US": "^GSPC"}
_benchmark_cache: Dict[str, Any] = {}
_BENCHMARK_TTL = 300

def get_benchmark_context(market: str, force_refresh: bool = False):
    """Benchmark index candles + its own trend reading (market regime), cached 5 minutes."""
    market = market if market in BENCHMARKS else "IDX"
    cached = _benchmark_cache.get(market)
    if cached and not force_refresh and time.time() - cached[0] < _BENCHMARK_TTL:
        return cached[1], cached[2]
    try:
        bdf = fetch_stock_ohlcv(BENCHMARKS[market], period="1y", force_refresh=force_refresh)
    except Exception as e:
        print(f"Benchmark fetch failed for {market}: {e}")
        bdf = pd.DataFrame()
    regime = compute_trend_direction(bdf) if not bdf.empty and len(bdf) >= 30 else None
    bdf = bdf if not bdf.empty else None
    _benchmark_cache[market] = (time.time(), bdf, regime)
    return bdf, regime

def direction_fields(direction: Dict[str, Any]) -> Dict[str, Any]:
    """Flat subset of the trend engine output stored with screener rows."""
    return {
        "direction_score": direction.get("direction_score", 0),
        "direction": direction.get("direction", "NETRAL"),
        "direction_label": direction.get("direction_label", ""),
        "trend_regime": direction.get("regime", "UNKNOWN"),
        "trend_confidence": direction.get("confidence", 0),
        "adx": direction.get("adx", 0.0),
        "direction_notes": direction.get("notes", []),
    }


def with_news_risk(market_regime: Optional[Dict[str, Any]], all_news) -> Optional[Dict[str, Any]]:
    """Attach systemic news risk (MSCI downgrade, trading halt, outflows...) to the market regime."""
    from .screener.sentiment import assess_market_news_risk
    risk = assess_market_news_risk(all_news or [])
    if market_regime is None:
        return {"direction_score": 0, "news_risk": risk} if risk["level"] != "NONE" else None
    return {**market_regime, "news_risk": risk}
