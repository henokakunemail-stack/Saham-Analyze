"""Money Flow & Accumulation/Distribution Engine (CMF, OBV, True VSA)."""
import pandas as pd
import numpy as np
from typing import Dict, Any

def compute_money_flow(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate CMF, OBV, 14-period OBV Divergence, and true Volume Spread Analysis."""
    if df.empty or len(df) < 20:
        return {
            "cmf20": 0.0,
            "obv": 0.0,
            "obv_divergence": "NONE",
            "obv_trend": 0.0,
            "money_flow_status": "NEUTRAL",
            "vsa_signal": "NORMAL",
            "vsa_label": "Aktivitas Volume Normal",
            "vsa_desc": "Volume dan rentang harga bergerak seimbang.",
            "spread_ratio": 1.0
        }

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    open_p = df['open']

    # 1. Chaikin Money Flow (CMF 20)
    hl_diff = (high - low).replace(0, 1e-9)
    mfm = ((close - low) - (high - close)) / hl_diff
    mfv = mfm * volume
    cmf20_series = mfv.rolling(20, min_periods=1).sum() / volume.rolling(20, min_periods=1).sum().replace(0, 1e-9)
    cmf20 = float(cmf20_series.iloc[-1])

    # 2. On-Balance Volume (OBV)
    direction = np.sign(close.diff()).fillna(0)
    obv_series = (direction * volume).cumsum()
    current_obv = float(obv_series.iloc[-1])

    # 3. OBV Trend & Divergence (regression slopes over 20 bars, not just two endpoints)
    # Both slopes are normalized so they are comparable: price in volatility units,
    # OBV in "average daily volumes per bar".
    obv_divergence = "NONE"
    obv_trend = 0.0
    window = min(20, len(df))
    x = np.arange(window, dtype=float)
    avg_vol = float(volume.iloc[-window:].mean()) or 1.0
    obv_slope = np.polyfit(x, obv_series.iloc[-window:].to_numpy(dtype=float), 1)[0] / avg_vol
    log_close = np.log(close.iloc[-window:].clip(lower=1e-9).to_numpy(dtype=float))
    daily_vol = float(np.std(np.diff(log_close))) or 1e-4
    price_slope = np.polyfit(x, log_close, 1)[0] / daily_vol
    obv_trend = float(np.tanh(obv_slope * 3))

    # Bullish Divergence: harga datar/turun, tetapi OBV terakumulasi naik secara konsisten
    if price_slope <= 0.05 and obv_slope >= 0.12:
        obv_divergence = "BULLISH_ACCUMULATION"
    # Bearish Divergence: harga naik, tetapi OBV turun (distribusi terselubung)
    elif price_slope >= 0.10 and obv_slope <= -0.08:
        obv_divergence = "BEARISH_DISTRIBUTION"

    # 4. True Volume Spread Analysis (VSA)
    vol_sma20 = volume.rolling(20, min_periods=1).mean().iloc[-1]
    vol_ratio = float(volume.iloc[-1] / vol_sma20) if vol_sma20 > 0 else 1.0

    spreads = high - low
    avg_spread20 = spreads.rolling(20, min_periods=1).mean().iloc[-1]
    curr_spread = float(spreads.iloc[-1])
    spread_ratio = float(curr_spread / avg_spread20) if avg_spread20 > 0 else 1.0

    close_pos = float((close.iloc[-1] - low.iloc[-1]) / curr_spread) if curr_spread > 0 else 0.5
    is_up_bar = float(close.iloc[-1]) >= float(open_p.iloc[-1])

    vsa_signal = "NORMAL"
    vsa_label = "Aktivitas Volume Normal"
    vsa_desc = "Volume dan rentang harga dalam kondisi seimbang."

    # One-price bar (ARA/ARB lock, or barely traded): the spread says nothing about supply
    if curr_spread <= float(close.iloc[-1]) * 1e-6 and len(close) > 1:
        up = float(close.iloc[-1]) >= float(close.iloc[-2])
        vsa_signal = "LOCKED"
        vsa_label = "Harga Terkunci Satu Harga" + (" (naik)" if up else " (turun)")
        vsa_desc = ("Seharian hanya satu harga (mis. ARA/ARB atau transaksi sangat sepi) — "
                    "volume & rentang hari ini tidak bisa dibaca sebagai sinyal.")

    # A. No Supply Test: Volume kering, spread sempit, penawaran jual habis
    elif vol_ratio <= 0.75 and spread_ratio <= 0.85:
        vsa_signal = "NO_SUPPLY_TEST"
        vsa_label = "Uji Penawaran Kering (No Supply Test)"
        vsa_desc = "Volume transaksi mengecil dan tekanan jual habis, potensi siap melesat."

    # B. Effort vs No Result: Volume masif tapi rentang lilin sempit (reversal / batas gerak)
    elif vol_ratio >= 1.7 and spread_ratio <= 0.75:
        vsa_signal = "EFFORT_NO_RESULT"
        vsa_label = "Effort vs No Result (Aktivitas Tertahan)"
        vsa_desc = "Volume transaksi masif namun rentang harga tertahan rapat, waspada pembalikan arah."

    # C. Buying Climax: Volume meledak, namun penutupan jatuh di bawah tengah lilin (distribusi pucuk)
    elif vol_ratio >= 1.9 and close_pos <= 0.40 and is_up_bar:
        vsa_signal = "BUYING_CLIMAX"
        vsa_label = "Buying Climax (Pelepasan Saham di Pucuk)"
        vsa_desc = "Volume euforia tinggi namun harga gagal tutup di pucuk, indikasi distribusi institusi."

    # D. Selling Climax: Volume meledak di area bawah dengan penutupan naik kembali (penyerapan panik)
    elif vol_ratio >= 1.8 and close_pos >= 0.50 and not is_up_bar:
        vsa_signal = "SELLING_CLIMAX"
        vsa_label = "Selling Climax (Penyerapan Panik Pasar)"
        vsa_desc = "Aksi panic selling retail diserap oleh institusi dengan penutupan rebound dari titik terendah."

    # E. Absorption: Volume tinggi diserap rapi di area atas/resisten
    elif vol_ratio >= 1.35 and spread_ratio <= 1.25 and close_pos >= 0.55:
        vsa_signal = "ABSORPTION"
        vsa_label = "Penyerapan Offer Institusi (Absorption)"
        vsa_desc = "Smart money menyerap antrian jual (offer) secara agresif untuk persiapan reli."

    # F. Markup: Volume tinggi + spread lebar ditutup dekat puncak
    elif vol_ratio >= 1.30 and spread_ratio >= 1.20 and close_pos >= 0.65:
        vsa_signal = "MARKUP"
        vsa_label = "Markup Akumulatif (Dorongan Beli Kuat)"
        vsa_desc = "Harga didorong naik agresif dengan dukungan volume pembeli nyata."

    # G. Selling Pressure: Volume di atas rata-rata dengan penutupan tertekan di dasar
    elif vol_ratio >= 1.30 and close_pos <= 0.30:
        vsa_signal = "SELLING_PRESSURE"
        vsa_label = "Tekanan Jual Dominan (Distribution)"
        vsa_desc = "Penjual mendominasi pasar menekan harga ke area terendah harian."

    # 5. Composite Accumulation / Distribution Status
    # CMF (20 days of flow) is the primary measure. A one-bar VSA read or an OBV divergence
    # may confirm or tilt it, but never flip a clearly negative CMF to "accumulation"
    # (or a clearly positive one to "distribution").
    bull_hint = obv_divergence == "BULLISH_ACCUMULATION" or vsa_signal in ("ABSORPTION", "MARKUP", "NO_SUPPLY_TEST")
    bear_hint = obv_divergence == "BEARISH_DISTRIBUTION" or vsa_signal in ("BUYING_CLIMAX", "SELLING_PRESSURE")
    if cmf20 >= 0.15 or (cmf20 >= 0.08 and bull_hint):
        status = "STRONG_INFLOW"
    elif cmf20 >= 0.04 or (cmf20 > -0.04 and bull_hint and not bear_hint):
        status = "MILD_INFLOW"
    elif cmf20 <= -0.12 or (cmf20 <= -0.05 and bear_hint):
        status = "STRONG_OUTFLOW"
    elif cmf20 <= -0.04 or (cmf20 < 0.04 and bear_hint):
        status = "MILD_OUTFLOW"
    else:
        status = "NEUTRAL"

    return {
        "cmf20": round(cmf20, 4),
        "obv": round(current_obv, 2),
        "obv_divergence": obv_divergence,
        "obv_trend": round(obv_trend, 3),
        "vsa_signal": vsa_signal,
        "vsa_label": vsa_label,
        "vsa_desc": vsa_desc,
        "spread_ratio": round(spread_ratio, 2),
        "money_flow_status": status
    }


def summarize_flow_proxy(df: pd.DataFrame, flow: Dict[str, Any]) -> Dict[str, Any]:
    """Money-flow summary from price & volume only (shown when no broker data is available).

    It is an *indication* derived from candles: it says nothing about which brokers or
    investors traded.
    """
    if df is None or df.empty or len(df) < 21:
        return {"available": False}
    w = df.iloc[-20:].copy()
    close = df["close"].astype(float)
    chg = close.diff().iloc[-20:]
    vol = w["volume"].astype(float)
    up_vol = float(vol[chg.values > 0].sum())
    down_vol = float(vol[chg.values < 0].sum())
    ratio = round(up_vol / down_vol, 2) if down_vol > 0 else None
    big_i = int(vol.values.argmax())
    big_row = w.iloc[big_i]
    big_chg = float(chg.iloc[big_i]) if not np.isnan(chg.iloc[big_i]) else 0.0
    avg_vol = float(vol.mean()) or 1.0

    if ratio is None or ratio >= 1.3:
        tilt = "BELI"
    elif ratio <= 0.77:
        tilt = "JUAL"
    else:
        tilt = "SEIMBANG"
    tilt_label = {"BELI": "Volume lebih banyak di hari naik (tekanan beli dominan)",
                  "JUAL": "Volume lebih banyak di hari turun (tekanan jual dominan)",
                  "SEIMBANG": "Volume hari naik dan turun seimbang"}[tilt]

    date = big_row["date"]
    date_str = str(date)[:10] if not hasattr(date, "strftime") else date.strftime("%Y-%m-%d")
    return {
        "available": True,
        "disclaimer": "Indikasi dari harga & volume — bukan data broker/bandar.",
        "cmf20": flow.get("cmf20", 0.0),
        "money_flow_status": flow.get("money_flow_status", "NEUTRAL"),
        "obv_trend": flow.get("obv_trend", 0.0),
        "vsa_label": flow.get("vsa_label", ""),
        "up_down_volume_ratio": ratio,
        "pressure": tilt,
        "pressure_label": tilt_label,
        "up_days": int((chg > 0).sum()),
        "down_days": int((chg < 0).sum()),
        "biggest_volume_day": {
            "date": date_str,
            "direction": "NAIK" if big_chg > 0 else "TURUN" if big_chg < 0 else "DATAR",
            "volume_x_avg": round(float(vol.iloc[big_i]) / avg_vol, 2),
        },
    }
