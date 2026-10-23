"""Technical indicators implementation with pure Pandas."""
import os
import pandas as pd
import numpy as np
from typing import Dict, Any

# "new" = engine/indicators/candles.detect (context + size + bearish counterparts); under test,
# see docs/hasil-uji-candlestick.md
CANDLE_DETECTOR = os.environ.get("SAHAM_CANDLES", "old")

def detect_candlestick_pattern(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect key single-bar and multi-bar candlestick patterns with reliability."""
    if df.empty or len(df) < 2:
        return {
            "pattern": "NORMAL",
            "label": "Konsolidasi / Stabil",
            "signal": "NEUTRAL",
            "reliability": "LOW",
            "description": "Pergerakan harga dalam rentang wajar tanpa pola pembalikan khusus."
        }

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else None

    c_open, c_high, c_low, c_close = float(curr['open']), float(curr['high']), float(curr['low']), float(curr['close'])
    p_open, p_high, p_low, p_close = float(prev['open']), float(prev['high']), float(prev['low']), float(prev['close'])

    body = abs(c_close - c_open)
    p_body = abs(p_close - p_open)
    total_range = c_high - c_low if c_high > c_low else 1e-9

    lower_shadow = min(c_open, c_close) - c_low
    upper_shadow = c_high - max(c_open, c_close)

    # Moving average trend context (last 10 closes)
    short_trend_up = float(df['close'].iloc[-1]) > float(df['close'].iloc[-min(len(df), 10)])

    # 1. Three White Soldiers (3 consecutive green candles making higher highs)
    if prev2 is not None:
        p2_open, p2_close = float(prev2['open']), float(prev2['close'])
        if (p2_close > p2_open and p_close > p_open and c_close > c_open and
            c_close > p_close > p2_close and body > 0.5 * total_range):
            return {
                "pattern": "THREE_WHITE_SOLDIERS",
                "label": "Three White Soldiers (Konfirmasi Bullish Dominan)",
                "signal": "STRONG_BULLISH",
                "reliability": "HIGH",
                "description": "Tiga lilin hijau berturut-turut menembus level tertinggi, menandakan dominasi kuat pembeli institusi."
            }

    # 2. Morning Star (Bearish -> Small Body Gap/Base -> Bullish Close > 50% of Bearish Body)
    if prev2 is not None:
        p2_open, p2_close = float(prev2['open']), float(prev2['close'])
        p2_body = abs(p2_close - p2_open)
        if (p2_close < p2_open and p2_body > 0.4 * (float(prev2['high']) - float(prev2['low'])) and
            p_body <= 0.3 * p2_body and c_close > c_open and c_close >= p2_close + (p2_body * 0.5)):
            return {
                "pattern": "MORNING_STAR",
                "label": "Morning Star (Siklus Reversal Bullish Kuat)",
                "signal": "STRONG_BULLISH",
                "reliability": "HIGH",
                "description": "Pola 3 lilin pembalikan arah dari pelemahan ke akumulasi pembeli baru."
            }

    # 3. Evening Star (Bullish -> Small Body Star -> Bearish Close > 50% into First)
    if prev2 is not None:
        p2_open, p2_close = float(prev2['open']), float(prev2['close'])
        p2_body = abs(p2_close - p2_open)
        if (p2_close > p2_open and p2_body > 0.4 * (float(prev2['high']) - float(prev2['low'])) and
            p_body <= 0.3 * p2_body and c_close < c_open and c_close <= p2_close - (p2_body * 0.5)):
            return {
                "pattern": "EVENING_STAR",
                "label": "Evening Star (Pembalikan Bearish di Puncak)",
                "signal": "STRONG_BEARISH",
                "reliability": "HIGH",
                "description": "Pola 3 lilin pelemahan di area resisten, waspada koreksi harga."
            }

    # 4. Bullish Engulfing
    if p_close < p_open and c_close > c_open and c_close >= p_open and c_open <= p_close and body > p_body:
        return {
            "pattern": "BULLISH_ENGULFING",
            "label": "Bullish Engulfing (Pembeli Menguasai / Reversal Kuat)",
            "signal": "STRONG_BULLISH",
            "reliability": "HIGH",
            "description": "Candle hijau menelan seluruh badan candle merah sebelumnya, konfirmasi dorongan beli besar."
        }

    # 5. Piercing Line (Bullish Reversal 2-Candle)
    if (p_close < p_open and c_close > c_open and c_open < p_close and
        c_close >= (p_open + p_close) / 2 and c_close < p_open):
        return {
            "pattern": "PIERCING_LINE",
            "label": "Piercing Line (Rejeksi Penurunan Kuat)",
            "signal": "BULLISH",
            "reliability": "HIGH",
            "description": "Candle hijau dibuka lebih rendah lalu ditutup menembus lebih dari 50% badan candle merah kemarin."
        }

    # 6. Bullish Harami (Inside Bar Bullish)
    if (p_close < p_open and c_close > c_open and c_open >= p_close and c_close <= p_open and body < p_body):
        return {
            "pattern": "BULLISH_HARAMI",
            "label": "Bullish Harami (Tekanan Jual Mereda)",
            "signal": "BULLISH",
            "reliability": "MEDIUM",
            "description": "Candle hijau kecil tertahan di dalam candle merah besar, indikasi penjual mulai kehilangan momentum."
        }

    # 7. Hammer vs Hanging Man (Dibedakan berdasarkan tren sebelumnya)
    if lower_shadow >= 2.0 * body and upper_shadow <= body * 0.6:
        if not short_trend_up:
            return {
                "pattern": "HAMMER",
                "label": "Hammer (Pembalikan Bullish / Rejection Bawah)",
                "signal": "BULLISH",
                "reliability": "MEDIUM",
                "description": "Ekor bawah panjang menolak harga murah di dasar swing, pembeli kembali masuk."
            }
        else:
            return {
                "pattern": "HANGING_MAN",
                "label": "Hanging Man (Waspada Rejeksi Puncak)",
                "signal": "BEARISH",
                "reliability": "MEDIUM",
                "description": "Ekor bawah di pucuk tren naik mengindikasikan adanya aksi jual awal oleh institusi."
            }

    # 8. Shooting Star vs Inverted Hammer
    if upper_shadow >= 2.0 * body and lower_shadow <= body * 0.6:
        if short_trend_up:
            return {
                "pattern": "SHOOTING_STAR",
                "label": "Shooting Star (Tekanan Jual di Atas Resisten)",
                "signal": "BEARISH",
                "reliability": "MEDIUM",
                "description": "Ekor atas panjang di area tinggi mengindikasikan aksi profit taking masif."
            }
        else:
            return {
                "pattern": "INVERTED_HAMMER",
                "label": "Inverted Hammer (Uji Coba Dorongan Beli)",
                "signal": "BULLISH",
                "reliability": "MEDIUM",
                "description": "Ekor atas di area bawah mengindikasikan adanya percobaan akumulasi awal."
            }

    # 9. Doji (Indecision)
    if body <= 0.12 * total_range:
        return {
            "pattern": "DOJI",
            "label": "Doji (Keseimbangan Sementara / Keraguan Pasar)",
            "signal": "NEUTRAL",
            "reliability": "LOW",
            "description": "Harga pembukaan dan penutupan hampir sama, pasar menunggu katalis arah berikutnya."
        }

    if c_close > c_open:
        return {
            "pattern": "BULLISH_BODY",
            "label": "Candle Hijau (Tekanan Beli Positif)",
            "signal": "BULLISH",
            "reliability": "LOW",
            "description": "Penutupan positif di atas pembukaan harian."
        }
    else:
        return {
            "pattern": "BEARISH_BODY",
            "label": "Candle Merah (Tekanan Jual)",
            "signal": "BEARISH",
            "reliability": "LOW",
            "description": "Penutupan di bawah pembukaan harian."
        }

def compute_technical_indicators(df: pd.DataFrame, market: str = "IDX", freeze_live_bar: bool = True) -> Dict[str, Any]:
    """Calculate EMA, RSI, MACD, Volume SMA, ATR(14), Entry Zone, and Candlestick."""
    if df.empty or len(df) < 20:
        return {}

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # 1. EMAs
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean() if len(df) >= 100 else close.ewm(span=len(df), adjust=False).mean()

    # 2. RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi14 = (100 - (100 / (1 + rs))).where((gain + loss) > 0, 50.0)   # no movement at all = neutral

    # 3. MACD (12, 26, 9)
    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    macd_line = fast - slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    # 4. Volume SMA 20 & Volume Ratio
    vol_sma20 = volume.rolling(20, min_periods=1).mean()
    current_vol = volume.iloc[-1]
    avg_vol = vol_sma20.iloc[-1]
    vol_ratio = float(current_vol / avg_vol) if avg_vol > 0 else 1.0

    # 5. True Range & ATR(14)
    tr0 = high - low
    tr1 = (high - close.shift(1)).abs()
    tr2 = (low - close.shift(1)).abs()
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
    atr14_series = tr.ewm(alpha=1/14, adjust=False).mean()
    atr14 = float(atr14_series.iloc[-1]) if not atr14_series.empty else float(tr.iloc[-1])
    if atr14 <= 0:
        atr14 = float(close.iloc[-1]) * 0.02

    # 6. 20-Day High Breakout & Support / Resistance
    prev_20d_high = float(high.iloc[-21:-1].max()) if len(df) >= 21 else float(high.max())
    prev_20d_low = float(low.iloc[-21:-1].min()) if len(df) >= 21 else float(low.min())
    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2]) if len(close) >= 2 else current_price
    change_pct = float(((current_price - prev_price) / prev_price) * 100) if prev_price > 0 else 0.0
    is_breakout = bool(current_price >= prev_20d_high)

    if CANDLE_DETECTOR == "new":
        from .candles import detect as detect_candles
        candlestick = detect_candles(df, atr14)
    else:
        candlestick = detect_candlestick_pattern(df)

    # 7. Realistic ATR-Based Entry Zone
    # Recent 5-day swing support
    recent_low_5d = float(low.iloc[-6:-1].min()) if len(df) >= 6 else prev_20d_low
    e20 = float(ema20.iloc[-1])

    if is_breakout:
        # Breakout entry: at or slightly below breakout level retest
        entry_high = round(current_price * 1.005, 2)
        entry_low = round(max(prev_20d_high, current_price - 0.4 * atr14), 2)
        recommended_entry = current_price
    else:
        # Pullback entry: support level between EMA20 and swing low
        support_candidate = max(e20, recent_low_5d)
        if current_price * 0.94 <= support_candidate <= current_price:
            entry_high = round(min(current_price * 0.995, support_candidate + 0.25 * atr14), 2)
            entry_low = round(max(support_candidate - 0.4 * atr14, current_price * 0.94), 2)
        else:
            entry_high = round(max(current_price * 0.97, current_price - 0.3 * atr14), 2)
            entry_low = round(max(current_price * 0.93, current_price - 1.1 * atr14), 2)

        # Invariant checks: entry_low must be strictly < entry_high and <= current_price
        entry_low = min(entry_low, round(entry_high * 0.985, 2))
        recommended_entry = round((entry_low + entry_high) / 2, 2)

    # Invariant guarantee: recommended_entry never exceeds market price during normal pullback
    if not is_breakout and recommended_entry > current_price:
        recommended_entry = round(current_price * 0.99, 2)
        entry_high = round(current_price * 0.995, 2)
        entry_low = round(current_price * 0.97, 2)

    # Market-consistent levels (exchange ticks, real support/resistance) replace the
    # heuristic zone above; see engine/screener/trade_levels.py
    from ..screener.trade_levels import compute_trade_levels, plan_position
    from ..collectors.data_quality import bar_is_final
    levels = None
    try:
        last_date = df["date"].iloc[-1] if "date" in df.columns else None
        if freeze_live_bar and last_date is not None and len(df) > 60 and bar_is_final(last_date, market) is False:
            # Today's session is still trading: keep the plan made from the last final close all
            # day (a half-formed candle would move ATR, EMAs and highs/lows) and report where the
            # live price stands against it.
            base = compute_technical_indicators(df.iloc[:-1], market, freeze_live_bar=False).get("levels")
            if base:
                live = plan_position(base, current_price, float(high.iloc[-1]), float(low.iloc[-1]))
                live["date"] = str(last_date)[:10]
                levels = {**base, "frozen": True, "live": live}
        if levels is None:
            levels = compute_trade_levels(df.reset_index(drop=True), market, is_breakout, prev_20d_high)
        entry_low, entry_high = levels["entry_low"], levels["entry_high"]
        recommended_entry = levels["recommended_entry"]
    except Exception as e:  # never break the analysis because of level maths
        print(f"[TradeLevels] fallback to heuristic zone: {e}")

    return {
        "price": current_price,
        "change_pct": round(change_pct, 2),
        "ema20": round(e20, 2),
        "ema50": round(float(ema50.iloc[-1]), 2),
        "ema200": round(float(ema200.iloc[-1]), 2),
        "rsi14": round(float(rsi14.iloc[-1]), 2),
        "macd_line": round(float(macd_line.iloc[-1]), 4),
        "macd_signal": round(float(signal_line.iloc[-1]), 4),
        "macd_hist": round(float(macd_hist.iloc[-1]), 4),
        "macd_hist_prev": round(float(macd_hist.iloc[-2]), 4) if len(macd_hist) >= 2 else 0.0,
        "vol_ratio": round(vol_ratio, 2),
        "is_breakout": is_breakout,
        "prev_20d_high": prev_20d_high,
        "prev_20d_low": prev_20d_low,
        "recent_low_5d": recent_low_5d,
        "atr14": round(atr14, 2),
        "entry_low": entry_low,
        "entry_high": entry_high,
        "recommended_entry": recommended_entry,
        "levels": levels,
        "candlestick": candlestick
    }
