"""Pullback-in-Uptrend setup detector.

Idea (plain language): buy strength on weakness. A stock qualifies when its
medium-term trend (~6 months, skipping the most recent month) is clearly up and
still healthy, but it is *temporarily* resting or dipping toward support. Stocks
that just ran hard are treated as "wait for a pullback", and stocks whose
pullback broke the last swing low are treated as a broken trend, not a dip.

Why: on IDX large caps, short-term strength (price far above EMA20, high RSI/CMF,
near 20-day highs) tended to *reverse* over the next 1-4 weeks, while 6-month
momentum held up. Combining "long-term up" with "short-term down" was the one
combination that ranked forward returns positively in our walk-forward tests.

Everything here uses only data up to the last bar (no look-ahead).
"""
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

LONG_WINDOW = 120  # ~6 months of trading days
SKIP_RECENT = 20   # skip the last month (short-term reversal zone)

STATE_LABELS = {
    "PULLBACK_IDEAL": "Pullback Sehat dalam Uptrend (Area Beli)",
    "PULLBACK_DEEP": "Koreksi Dalam, Tren Masih Bertahan (Tunggu Konfirmasi)",
    "UPTREND_RUNNING": "Uptrend Berjalan (Belum Ada Diskon)",
    "UPTREND_EXTENDED": "Uptrend Terlalu Panas (Tunggu Pullback)",
    "TREND_BROKEN": "Tren Naik Rusak (Jebol Support)",
    "NO_UPTREND": "Bukan Uptrend (Hindari Strategi Pullback)",
    "INSUFFICIENT_DATA": "Data Belum Cukup (< 6 Bulan)",
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x is None or not np.isfinite(x):
        return 0.0
    return float(max(lo, min(hi, x)))


def _long_momentum(close: pd.Series) -> Optional[float]:
    if len(close) <= LONG_WINDOW:
        return None
    return float(close.iloc[-1 - SKIP_RECENT] / close.iloc[-1 - LONG_WINDOW] - 1)


def _benchmark_long_momentum(benchmark: Optional[pd.DataFrame], last_date) -> Optional[float]:
    if benchmark is None or benchmark.empty or last_date is None:
        return None
    b = benchmark.copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b[b["date"] <= last_date].drop_duplicates("date", keep="last")
    return _long_momentum(b["close"].astype(float).reset_index(drop=True))


def compute_pullback_setup(
    df: pd.DataFrame,
    adx: float,
    rsi: float,
    last_swing_low: Optional[float],
    benchmark_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Classify the pullback state and return a setup score in [-1, +1].

    adx / rsi / last_swing_low come from the trend engine so they are computed once.
    """
    close = df["close"].astype(float).reset_index(drop=True)
    high = df["high"].astype(float).reset_index(drop=True)
    low = df["low"].astype(float).reset_index(drop=True)
    price = float(close.iloc[-1])

    long_mom = _long_momentum(close)
    if long_mom is None:
        return {"state": "INSUFFICIENT_DATA", "label": STATE_LABELS["INSUFFICIENT_DATA"],
                "score": 0.0, "long_momentum_pct": None, "notes": []}

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]) or price * 0.02

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    has_200 = len(close) >= 200
    ema_long = close.ewm(span=200 if has_200 else 100, adjust=False).mean()

    stretch = (price - float(ema20.iloc[-1])) / atr          # ATRs above/below EMA20
    roc5 = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 6 else 0.0
    ema50_rising = bool(ema50.iloc[-1] > ema50.iloc[-11]) if len(ema50) > 11 else False
    above_long = price > float(ema_long.iloc[-1])
    high_60 = float(high.iloc[-60:].max())
    drawdown = price / high_60 - 1                            # depth of the current dip

    last_date = pd.to_datetime(df["date"].iloc[-1]).normalize() if "date" in df.columns else None
    bench_mom = _benchmark_long_momentum(benchmark_df, last_date)
    rel_mom = long_mom - bench_mom if bench_mom is not None else None

    structure_intact = last_swing_low is None or price > float(last_swing_low)
    strong_trend = adx >= 20

    # ── Component scores, each in [-1, 1] ──────────────────────────────────
    # 1. Medium-term trend quality (the "uptrend" half)
    trend_q = 0.55 * np.tanh(long_mom / 0.20)
    trend_q += 0.25 if above_long else -0.25
    trend_q += 0.20 if ema50_rising else -0.20
    if rel_mom is not None:
        trend_q = 0.8 * trend_q + 0.2 * np.tanh(rel_mom / 0.15)
    trend_q = _clip(trend_q)

    # 2. Short-term discount (the "pullback" half): rewarded when price rests near/below EMA20
    dip = -np.tanh((stretch - 0.3) / 1.5)          # ~+0.2 at EMA20, negative when stretched
    dip += 0.25 * float(np.clip((55 - rsi) / 15, -1, 1))
    dip += -0.15 * np.tanh(roc5 / 0.05)
    dip = _clip(dip)

    # 3. Combine: a discount only matters inside a healthy uptrend
    if trend_q > 0:
        score = 0.55 * trend_q + 0.45 * dip * trend_q / max(trend_q, 0.35)
        if strong_trend:
            score += 0.1
    else:
        score = 0.7 * trend_q - 0.1  # no uptrend → never a pullback buy
    if not structure_intact:
        score = min(score, -0.2)

    # ── State classification ──────────────────────────────────────────────
    uptrend = long_mom > 0.05 and above_long and ema50_rising
    if not uptrend:
        state = "TREND_BROKEN" if (long_mom > 0.10 and not structure_intact) else "NO_UPTREND"
    elif not structure_intact:
        state = "TREND_BROKEN"
    elif stretch > 2.2 or rsi > 72:
        state = "UPTREND_EXTENDED"
    elif -1.5 <= stretch <= 0.6 and 35 <= rsi <= 58:
        state = "PULLBACK_IDEAL"
    elif stretch < -1.5 or rsi < 35:
        state = "PULLBACK_DEEP"
    else:
        state = "UPTREND_RUNNING"

    # The state is the decision; the score may never contradict it
    if state == "NO_UPTREND":
        score = min(score, 0.15 if long_mom > 0 else -0.05)
    elif state == "TREND_BROKEN":
        score = min(score, -0.3)
    elif state == "UPTREND_EXTENDED":
        score = min(score, 0.25)
    elif state == "PULLBACK_DEEP":
        score = min(score, 0.45)

    notes = [f"Momentum 6 bulan (lewati 1 bln terakhir): {long_mom * 100:+.1f}%"]
    if rel_mom is not None:
        notes.append(f"{'Lebih kuat' if rel_mom >= 0 else 'Lebih lemah'} dari indeks {rel_mom * 100:+.1f}% (6 bulan)")
    notes.append(f"Jarak dari EMA20: {stretch:+.1f}x ATR · Turun {abs(drawdown) * 100:.1f}% dari puncak 60 hari")
    if not structure_intact:
        notes.append("Harga di bawah swing low terakhir — ini bukan pullback lagi")

    return {
        "state": state,
        "label": STATE_LABELS[state],
        "score": round(_clip(score), 3),
        "trend_quality": round(trend_q, 3),
        "discount": round(dip, 3),
        "long_momentum_pct": round(long_mom * 100, 2),
        "relative_momentum_pct": round(rel_mom * 100, 2) if rel_mom is not None else None,
        "stretch_atr": round(stretch, 2),
        "drawdown_60d_pct": round(drawdown * 100, 2),
        "structure_intact": structure_intact,
        "ema50_rising": ema50_rising,
        "above_long_ema": above_long,
        "support_level": round(float(last_swing_low), 2) if last_swing_low is not None else None,
        "notes": notes,
    }
