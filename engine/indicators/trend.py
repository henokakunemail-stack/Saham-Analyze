"""Trend Direction Engine: multi-factor reading of where price is heading.

Each component is normalized to [-1, +1] (bearish → bullish) and combined into a
single direction score in [-100, +100], plus a regime label and a confidence
value that measures how strongly the components agree with each other.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

from .pullback import compute_pullback_setup

PIVOT_K = 3  # bars on each side to confirm a swing high / low

# Weights of each component in the final direction score (sum = 1.0)
COMPONENT_WEIGHTS = {
    "ema_structure": 0.20,
    "adx_dmi": 0.15,
    "regression": 0.15,
    "market_structure": 0.15,
    "momentum": 0.10,
    "weekly": 0.15,
    "relative_strength": 0.10,
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x is None or not np.isfinite(x):
        return 0.0
    return float(max(lo, min(hi, x)))


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def compute_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Wilder's ADX with +DI / -DI."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr = _true_range(df).ewm(alpha=1 / period, adjust=False).mean().replace(0, 1e-9)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return (100 - (100 / (1 + gain / loss.replace(0, 1e-9)))).where((gain + loss) > 0, 50.0)


def _regression(values: np.ndarray) -> Tuple[float, float]:
    """Linear regression on log values → (slope per bar, R²)."""
    y = np.log(np.clip(values, 1e-9, None))
    x = np.arange(len(y), dtype=float)
    if len(y) < 5 or np.allclose(y, y[0]):
        return 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-12
    return float(slope), max(0.0, 1.0 - ss_res / ss_tot)


def find_pivots(series: pd.Series, k: int = PIVOT_K, kind: str = "high") -> List[int]:
    """Indices of confirmed swing highs/lows (k bars on both sides)."""
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    pivots = []
    for i in range(k, n - k):
        window = vals[i - k:i + k + 1]
        if kind == "high" and vals[i] == window.max() and vals[i] > vals[i - 1]:
            pivots.append(i)
        elif kind == "low" and vals[i] == window.min() and vals[i] < vals[i - 1]:
            pivots.append(i)
    return pivots


def _market_structure(df: pd.DataFrame) -> Dict[str, Any]:
    """Higher-high/higher-low vs lower-high/lower-low reading + break of structure."""
    lookback = df.iloc[-120:]
    offset = len(df) - len(lookback)
    highs = find_pivots(lookback["high"], kind="high")
    lows = find_pivots(lookback["low"], kind="low")
    close = float(df["close"].iloc[-1])

    score = 0.0
    label = "TIDAK JELAS"
    last_swing_high = float(lookback["high"].iloc[highs[-1]]) if highs else None
    last_swing_low = float(lookback["low"].iloc[lows[-1]]) if lows else None

    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = float(lookback["high"].iloc[highs[-2]]), float(lookback["high"].iloc[highs[-1]])
        l1, l2 = float(lookback["low"].iloc[lows[-2]]), float(lookback["low"].iloc[lows[-1]])
        hh, hl = h2 > h1, l2 > l1
        if hh and hl:
            score, label = 0.8, "HIGHER HIGH & HIGHER LOW"
        elif not hh and not hl:
            score, label = -0.8, "LOWER HIGH & LOWER LOW"
        elif hl:
            score, label = 0.3, "HIGHER LOW (Basis Menguat)"
        else:
            score, label = -0.3, "LOWER LOW (Basis Melemah)"

    # Break of structure overrides stale swings
    bos = "NONE"
    if last_swing_high is not None and close > last_swing_high:
        bos = "BULLISH_BOS"
        score = max(score, 0.0) + 0.4
    elif last_swing_low is not None and close < last_swing_low:
        bos = "BEARISH_BOS"
        score = min(score, 0.0) - 0.4

    return {
        "score": _clip(score),
        "label": label,
        "break_of_structure": bos,
        "last_swing_high": round(last_swing_high, 2) if last_swing_high is not None else None,
        "last_swing_low": round(last_swing_low, 2) if last_swing_low is not None else None,
        "swing_high_idx": [i + offset for i in highs],
        "swing_low_idx": [i + offset for i in lows],
    }


def detect_rsi_divergence(df: pd.DataFrame, rsi: pd.Series, recent_bars: int = 12, max_span: int = 45) -> str:
    """Regular RSI divergence between the last two confirmed swing points."""
    n = len(df)
    lows = find_pivots(df["low"], kind="low")
    highs = find_pivots(df["high"], kind="high")

    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if n - 1 - b <= recent_bars and b - a <= max_span:
            if df["low"].iloc[b] < df["low"].iloc[a] and rsi.iloc[b] > rsi.iloc[a] + 2 and rsi.iloc[a] < 45:
                return "BULLISH"
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if n - 1 - b <= recent_bars and b - a <= max_span:
            if df["high"].iloc[b] > df["high"].iloc[a] and rsi.iloc[b] < rsi.iloc[a] - 2 and rsi.iloc[a] > 55:
                return "BEARISH"
    return "NONE"


def _weekly_trend(df: pd.DataFrame) -> Tuple[float, str]:
    """Higher-timeframe filter: weekly EMA10/EMA20 stack and slope."""
    if "date" not in df.columns:
        return 0.0, "N/A"
    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.isna().any():
        return 0.0, "N/A"
    weekly = df.assign(_d=dates).set_index("_d")["close"].resample("W-FRI").last().dropna()
    if len(weekly) < 12:
        return 0.0, "N/A"
    e10 = weekly.ewm(span=10, adjust=False).mean()
    e20 = weekly.ewm(span=min(20, len(weekly)), adjust=False).mean()
    w_close = float(weekly.iloc[-1])
    score = 0.0
    score += 0.4 if w_close > e10.iloc[-1] else -0.4
    score += 0.3 if e10.iloc[-1] > e20.iloc[-1] else -0.3
    score += 0.3 if e10.iloc[-1] > e10.iloc[-3] else -0.3
    if score >= 0.6:
        label = "UPTREND MINGGUAN"
    elif score <= -0.6:
        label = "DOWNTREND MINGGUAN"
    else:
        label = "SIDEWAYS MINGGUAN"
    return _clip(score), label


def _relative_strength(df: pd.DataFrame, benchmark: Optional[pd.DataFrame]) -> Tuple[Optional[float], Dict[str, float]]:
    """Excess return vs index over 20 & 60 bars (aligned by date)."""
    if benchmark is None or benchmark.empty or "date" not in df.columns:
        return None, {}
    s = pd.Series(df["close"].to_numpy(dtype=float), index=pd.to_datetime(df["date"]).dt.normalize())
    b = pd.Series(benchmark["close"].to_numpy(dtype=float), index=pd.to_datetime(benchmark["date"]).dt.normalize())
    b = b[~b.index.duplicated(keep="last")].reindex(s.index).ffill()
    joined = pd.concat([s, b], axis=1, keys=["s", "b"]).dropna()
    if len(joined) < 25:
        return None, {}
    out = {}
    parts = []
    for n in (20, 60):
        if len(joined) > n:
            rs = (joined["s"].iloc[-1] / joined["s"].iloc[-n - 1]) - (joined["b"].iloc[-1] / joined["b"].iloc[-n - 1])
            out[f"rs_{n}d_pct"] = round(float(rs) * 100, 2)
            parts.append(np.tanh(rs / 0.08))
    if not parts:
        return None, out
    return _clip(float(np.mean(parts))), out


def compute_trend_direction(df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Return direction score [-100, 100], regime, confidence and component breakdown."""
    if df is None or df.empty or len(df) < 30:
        return {
            "direction_score": 0, "direction": "NETRAL", "direction_label": "Data Tidak Cukup",
            "regime": "UNKNOWN", "confidence": 0, "adx": 0.0, "components": {},
            "rsi_divergence": "NONE", "squeeze": False, "notes": [],
        }

    df = df.reset_index(drop=True)
    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    atr = float(_true_range(df).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]) or price * 0.02
    notes: List[str] = []
    comps: Dict[str, float] = {}

    # 1. EMA structure + slope (normalized by ATR)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    s = 0.0
    s += 0.25 if price > ema20.iloc[-1] else -0.25
    s += 0.25 if ema20.iloc[-1] > ema50.iloc[-1] else -0.25
    if len(df) >= 200:
        ema200 = close.ewm(span=200, adjust=False).mean()
        s += 0.2 if price > ema200.iloc[-1] else -0.2
        s += 0.1 if ema50.iloc[-1] > ema200.iloc[-1] else -0.1
    else:
        s *= 1.6  # rescale so the component can still reach ±0.8
    slope20 = (ema20.iloc[-1] - ema20.iloc[-6]) / atr
    s += 0.2 * np.tanh(slope20)
    comps["ema_structure"] = _clip(s)

    # 2. ADX / DMI — direction from DI spread, magnitude from ADX
    adx_s, pdi, mdi = compute_adx(df)
    adx = float(adx_s.iloc[-1])
    di_dir = np.tanh((pdi.iloc[-1] - mdi.iloc[-1]) / 10.0)
    strength = min(1.0, max(0.0, (adx - 12) / 18))  # 12 → 0, 30+ → 1
    comps["adx_dmi"] = _clip(di_dir * (0.35 + 0.65 * strength))
    adx_rising = bool(adx_s.iloc[-1] > adx_s.iloc[-4])

    # 3. Log-linear regression slope × R² (trend quality) on 20 and 60 bars
    reg_parts = []
    reg_info = {}
    for n, w in ((20, 0.5), (60, 0.5)):
        if len(close) >= n:
            slope, r2 = _regression(close.iloc[-n:].to_numpy())
            daily_vol = float(np.log(close).diff().iloc[-n:].std()) or 1e-4
            reg_parts.append(w * np.tanh(slope / daily_vol * 4) * (0.3 + 0.7 * r2))
            reg_info[f"slope_{n}d_pct"] = round(slope * 100, 3)
            reg_info[f"r2_{n}d"] = round(r2, 2)
    comps["regression"] = _clip(sum(reg_parts) / (0.5 * len(reg_parts))) if reg_parts else 0.0

    # 4. Market structure
    ms = _market_structure(df)
    comps["market_structure"] = ms["score"]

    # 5. Momentum: risk-adjusted ROC + MACD histogram
    daily_vol = float(np.log(close).diff().iloc[-60:].std()) or 1e-4
    roc10 = float(np.log(close.iloc[-1] / close.iloc[-11])) if len(close) > 11 else 0.0
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    m = 0.6 * np.tanh(roc10 / (daily_vol * np.sqrt(10)))
    m += 0.25 if hist.iloc[-1] > 0 else -0.25
    m += 0.15 if hist.iloc[-1] > hist.iloc[-2] else -0.15
    comps["momentum"] = _clip(m)

    # 6. Weekly trend (higher timeframe)
    w_score, w_label = _weekly_trend(df)
    if w_label != "N/A":
        comps["weekly"] = w_score

    # 7. Relative strength vs index
    rs_score, rs_info = _relative_strength(df, benchmark_df)
    if rs_score is not None:
        comps["relative_strength"] = rs_score

    # Weighted combination (renormalize over available components)
    total_w = sum(COMPONENT_WEIGHTS[k] for k in comps)
    raw = sum(COMPONENT_WEIGHTS[k] * v for k, v in comps.items()) / (total_w or 1)
    direction_score = int(round(raw * 100))

    # Confidence: agreement of components with the overall sign, scaled by ADX
    sign = np.sign(raw) if abs(raw) > 0.05 else 0
    if sign == 0:
        agreement = 1 - np.mean([abs(v) for v in comps.values()])
    else:
        agreement = sum(COMPONENT_WEIGHTS[k] for k, v in comps.items() if np.sign(v) == sign) / total_w
    confidence = int(round(100 * (0.7 * agreement + 0.3 * strength)))

    # Volatility squeeze: Bollinger bandwidth in the lowest 20% of the last 120 bars
    sma20 = close.rolling(20).mean()
    bw = (4 * close.rolling(20).std() / sma20).dropna()
    squeeze = bool(len(bw) >= 60 and bw.iloc[-1] <= bw.iloc[-120:].quantile(0.2))

    rsi = compute_rsi(close)
    rsi_div = detect_rsi_divergence(df, rsi)
    pullback = compute_pullback_setup(df, adx, float(rsi.iloc[-1]), ms["last_swing_low"], benchmark_df)

    # Regime
    if squeeze and adx < 20:
        regime = "SQUEEZE"
    elif adx >= 20 and direction_score >= 20:
        regime = "TRENDING_UP"
    elif adx >= 20 and direction_score <= -20:
        regime = "TRENDING_DOWN"
    else:
        regime = "RANGING"

    if direction_score >= 50:
        direction, label = "NAIK_KUAT", "Uptrend Kuat"
    elif direction_score >= 20:
        direction, label = "NAIK", "Cenderung Naik"
    elif direction_score > -20:
        direction, label = "NETRAL", "Sideways / Belum Ada Arah"
    elif direction_score > -50:
        direction, label = "TURUN", "Cenderung Turun"
    else:
        direction, label = "TURUN_KUAT", "Downtrend Kuat"

    # Human-readable notes (Indonesian)
    notes.append(f"ADX {adx:.0f} ({'tren kuat' if adx >= 25 else 'tren lemah' if adx < 20 else 'tren moderat'}"
                 f"{', menguat' if adx_rising else ''})")
    if ms["label"] != "TIDAK JELAS":
        notes.append(f"Struktur: {ms['label']}")
    if ms["break_of_structure"] == "BULLISH_BOS":
        notes.append("Break of Structure bullish (tembus swing high terakhir)")
    elif ms["break_of_structure"] == "BEARISH_BOS":
        notes.append("Break of Structure bearish (jebol swing low terakhir)")
    if w_label != "N/A":
        notes.append(w_label.title())
    if "rs_20d_pct" in rs_info:
        rs20 = rs_info["rs_20d_pct"]
        notes.append(f"{'Outperform' if rs20 >= 0 else 'Underperform'} indeks {rs20:+.1f}% (20 hari)")
    if rsi_div == "BULLISH":
        notes.append("Bullish divergence RSI (tekanan jual melemah)")
    elif rsi_div == "BEARISH":
        notes.append("Bearish divergence RSI (momentum naik melemah)")
    if squeeze:
        notes.append("Volatility squeeze: siap bergerak tajam")

    return {
        "direction_score": direction_score,
        "direction": direction,
        "direction_label": label,
        "regime": regime,
        "confidence": confidence,
        "adx": round(adx, 1),
        "plus_di": round(float(pdi.iloc[-1]), 1),
        "minus_di": round(float(mdi.iloc[-1]), 1),
        "adx_rising": adx_rising,
        "components": {k: round(v, 3) for k, v in comps.items()},
        "market_structure": ms["label"],
        "break_of_structure": ms["break_of_structure"],
        "last_swing_high": ms["last_swing_high"],
        "last_swing_low": ms["last_swing_low"],
        "weekly_trend": w_label,
        "rsi_divergence": rsi_div,
        "squeeze": squeeze,
        **reg_info,
        **rs_info,
        "pullback": pullback,
        "notes": notes,
    }
