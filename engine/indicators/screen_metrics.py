"""Extra per-stock metrics for the screener filters (liquidity, returns, position)."""
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

ILLIQUID_IDR = 1_000_000_000      # < Rp1 miliar/hari rata-rata nilai transaksi
ILLIQUID_USD = 5_000_000


def _ret(close: pd.Series, bars: int) -> Optional[float]:
    if len(close) <= bars:
        return None
    base = float(close.iloc[-1 - bars])
    return round((float(close.iloc[-1]) / base - 1) * 100, 2) if base > 0 else None


def compute_screen_metrics(df: pd.DataFrame, tech: Dict[str, Any], direction: Optional[Dict[str, Any]],
                           financials: Optional[Dict[str, Any]], market: str = "IDX") -> Dict[str, Any]:
    if df is None or df.empty:
        return {}
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    price = float(close.iloc[-1])
    value = (close * vol).iloc[-20:]
    avg_value = float(value.mean()) if len(value) else 0.0
    high_52w = float(df["high"].astype(float).iloc[-250:].max())
    ema200 = float(tech.get("ema200") or 0) or None
    d = direction or {}
    pb = d.get("pullback") or {}
    atr = float(tech.get("atr14") or 0)
    illiquid = avg_value < (ILLIQUID_IDR if market == "IDX" else ILLIQUID_USD)
    return {
        "avg_value_20d": round(avg_value, 0),
        "illiquid": bool(illiquid),
        "ret_1m": _ret(close, 21),
        "ret_3m": _ret(close, 63),
        "ret_6m": _ret(close, 126),
        "rs_20d": d.get("rs_20d_pct"),
        "rs_60d": d.get("rs_60d_pct"),
        "dist_52w_high_pct": round((price / high_52w - 1) * 100, 2) if high_52w > 0 else None,
        "dist_ema200_pct": round((price / ema200 - 1) * 100, 2) if ema200 else None,
        "stretch_atr": pb.get("stretch_atr"),
        "long_momentum_pct": pb.get("long_momentum_pct"),
        "atr_pct": round(atr / price * 100, 2) if price > 0 and atr > 0 else None,
        "market_cap": (financials or {}).get("market_cap"),
    }
