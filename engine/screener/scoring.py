"""Composite Scoring Algorithm for Stock Bullish/Bearish Ranking with Financial Health.

v4 "pullback in uptrend": every pillar is normalized to [-1, +1] and combined with
fixed weights. The dominant pillar is the pullback setup (indicators/pullback.py):
a healthy ~6-month uptrend that is temporarily resting near support. Short-term
strength (breakouts, RSI/CMF spikes, price stretched above EMA20) is no longer
rewarded on its own — on IDX large caps it tended to reverse within 1-4 weeks.
Oscillator, candlestick and VSA signals are read in trend context, and a bearish
market (index in a downtrend) switches the model to a defensive mode.
"""
import math
import os
from typing import Dict, Any, Optional, List, Tuple

# Candlestick patterns in the setup pillar: "on" (default) or "off" — under test,
# see docs/hasil-uji-candlestick.md
CANDLE_SCORING = os.environ.get("SAHAM_CANDLE_SCORE", "on")

PILLAR_WEIGHTS = {
    "pullback": 0.35,
    "trend": 0.20,
    "money_flow": 0.10,
    "momentum": 0.10,
    "setup": 0.05,
    "fundamental": 0.12,
    "sentiment": 0.08,
}

def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x is None or not math.isfinite(x):
        return 0.0
    return max(lo, min(hi, x))


def evaluate_confluence_breakout(
    tech: Dict[str, Any],
    flow: Dict[str, Any],
    financials: Optional[Dict[str, Any]] = None,
    direction: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Evaluate High-Probability Confluence Gates to confirm genuine setup and calculate realistic TP/CL/Entry."""
    price = float(tech.get("price", 0))
    ema20 = float(tech.get("ema20", 0))
    ema50 = float(tech.get("ema50", 0))
    ema200 = float(tech.get("ema200", 0))
    atr14 = float(tech.get("atr14", price * 0.02)) or price * 0.02
    cmf = float(flow.get("cmf20", 0.0))
    flow_status = flow.get("money_flow_status", "NEUTRAL")
    vol_ratio = float(tech.get("vol_ratio", 1.0))
    is_breakout = bool(tech.get("is_breakout", False))

    entry_low = float(tech.get("entry_low", round(price * 0.98, 2)))
    entry_high = float(tech.get("entry_high", round(price * 1.002, 2)))
    recommended_entry = float(tech.get("recommended_entry", price))

    # Stop loss: prefer the last confirmed swing low (structure), fall back to ATR/5-day low
    recent_low = float(tech.get("recent_low_5d", tech.get("prev_20d_low", price * 0.95)))
    calculated_sl = round(min(recent_low, entry_low - 1.2 * atr14), 2)
    swing_low = (direction or {}).get("last_swing_low")
    if swing_low and swing_low < entry_low:
        structural_sl = round(float(swing_low) - 0.25 * atr14, 2)
        if structural_sl >= recommended_entry * 0.92:
            calculated_sl = structural_sl
    # Keep at least ~1 ATR of breathing room, and cap max risk at ~8%
    calculated_sl = min(calculated_sl, round(recommended_entry - 1.0 * atr14, 2))
    stop_loss = max(calculated_sl, round(recommended_entry * 0.92, 2))
    if stop_loss >= recommended_entry:
        stop_loss = round(recommended_entry * 0.95, 2)

    # Targets: nearest overhead resistance (20d high / last swing high) or ATR projection
    res_20d = float(tech.get("prev_20d_high", price * 1.05))
    swing_high = (direction or {}).get("last_swing_high")
    resistance = res_20d
    if swing_high and float(swing_high) > recommended_entry * 1.01:
        resistance = min(res_20d, float(swing_high)) if res_20d > recommended_entry * 1.01 else float(swing_high)
    target_tp1 = round(max(resistance, recommended_entry + 1.8 * atr14), 2)
    target_tp2 = round(target_tp1 + 1.5 * atr14, 2)

    risk = max(recommended_entry - stop_loss, 1e-4)
    reward = max(target_tp1 - recommended_entry, 1e-4)
    rr_ratio = round(reward / risk, 2)

    # Structured, tick-aligned levels from trade_levels win over the legacy heuristics above
    # (the legacy path remains for callers that pass a bare indicator dict without candles).
    lv = tech.get("levels") or None
    if lv:
        entry_low, entry_high = lv["entry_low"], lv["entry_high"]
        recommended_entry = lv["recommended_entry"]
        stop_loss, target_tp1, target_tp2 = lv["stop_loss"], lv["target_tp1"], lv["target_tp2"]
        rr_ratio = lv["risk_reward_ratio"]

    health_ok = True
    if financials:
        health_ok = financials.get("health_grade") != "DISTRESSED" and not financials.get("is_speculative", False)

    pb_state = ((direction or {}).get("pullback") or {}).get("state")
    if direction and "direction_score" in direction:
        trend_ok = (direction["direction_score"] >= 20 and price > ema20) or pb_state in ("PULLBACK_IDEAL", "UPTREND_RUNNING")
    else:
        trend_ok = price > ema20 and (ema20 > ema50 or price > ema200)

    gates = {
        "gate_smart_money": cmf >= 0.04 and flow_status in ["STRONG_INFLOW", "MILD_INFLOW"],
        "gate_volume_expansion": vol_ratio >= 1.3,
        "gate_trend_alignment": trend_ok,
        "gate_resistance_breakout": is_breakout or flow.get("vsa_signal") in ["ABSORPTION", "MARKUP", "NO_SUPPLY_TEST"],
        "gate_risk_reward": rr_ratio >= 1.4,
        "gate_financial_health": health_ok
    }
    passed_count = sum(1 for v in gates.values() if v)
    # A setup against the trend is never "confirmed", whatever the other gates say
    is_confirmed = passed_count >= 4 and gates["gate_trend_alignment"]

    return {
        "is_confirmed_breakout": is_confirmed,
        "confluence_score": passed_count,
        "confluence_gates": gates,
        "risk_reward_ratio": rr_ratio,
        "target_tp": target_tp1,
        "target_tp1": target_tp1,
        "target_tp2": target_tp2,
        "stop_loss": stop_loss,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "recommended_entry": recommended_entry,
        "levels": lv,
    }


def _trend_pillar(tech: Dict[str, Any], direction: Optional[Dict[str, Any]], reasons: List[Tuple[float, str]]) -> float:
    if direction and "direction_score" in direction:
        d = direction["direction_score"] / 100.0
        label = direction.get("direction_label", "")
        if abs(d) >= 0.2:
            reasons.append((d * PILLAR_WEIGHTS["trend"],
                            f"{'📈' if d > 0 else '📉'} {label} (Arah {direction['direction_score']:+d}, ADX {direction.get('adx', 0):.0f})"))
        return _clip(d)

    # Fallback when no direction engine output is available
    price, e20, e50, e200 = (float(tech.get(k, 0)) for k in ("price", "ema20", "ema50", "ema200"))
    s = (0.35 if price > e20 else -0.35) + (0.35 if e20 > e50 else -0.35) + (0.3 if price > e200 else -0.3)
    if s >= 0.6:
        reasons.append((0.15, "Struktur EMA Bullish (Harga > EMA20 > EMA50)"))
    elif s <= -0.6:
        reasons.append((-0.15, "Struktur EMA Bearish (Harga < EMA20 < EMA50)"))
    return _clip(s)


def _money_flow_pillar(tech, flow, trend: float, reasons) -> float:
    cmf = float(flow.get("cmf20", 0.0))
    obv_div = flow.get("obv_divergence", "NONE")
    obv_trend = float(flow.get("obv_trend", 0.0))
    vsa = flow.get("vsa_signal", "NORMAL")
    w = PILLAR_WEIGHTS["money_flow"]

    s = 0.45 * math.tanh(cmf / 0.12) + 0.2 * obv_trend
    if cmf >= 0.15:
        reasons.append((0.45 * w, f"Chaikin Money Flow Masif ({cmf:+.2f})"))
    elif cmf >= 0.05:
        reasons.append((0.25 * w, f"Uang Masuk Positif (CMF {cmf:+.2f})"))
    elif cmf <= -0.10:
        reasons.append((-0.4 * w, f"Uang Keluar Deras (CMF {cmf:+.2f})"))

    if obv_div == "BULLISH_ACCUMULATION":
        s += 0.25
        reasons.append((0.25 * w, "Akumulasi Diam-diam (OBV naik saat harga datar)"))
    elif obv_div == "BEARISH_DISTRIBUTION":
        s -= 0.3
        reasons.append((-0.3 * w, "Distribusi Terselubung (OBV turun saat harga naik)"))

    # VSA signals, read in trend context
    vsa_label = flow.get("vsa_label", vsa)
    if vsa in ("MARKUP", "ABSORPTION"):
        s += 0.3
        reasons.append((0.3 * w, vsa_label))
    elif vsa == "NO_SUPPLY_TEST":
        bonus = 0.2 if trend > -0.2 else 0.05
        s += bonus
        reasons.append((bonus * w, vsa_label))
    elif vsa == "SELLING_CLIMAX":
        # Panic absorbed: meaningful only after a decline
        bonus = 0.25 if trend < 0 else 0.05
        s += bonus
        reasons.append((bonus * w, vsa_label))
    elif vsa == "BUYING_CLIMAX":
        s -= 0.4
        reasons.append((-0.4 * w, vsa_label))
    elif vsa == "SELLING_PRESSURE":
        s -= 0.35
        reasons.append((-0.35 * w, vsa_label))
    elif vsa == "EFFORT_NO_RESULT":
        s += -0.15 if trend > 0.2 else 0.1

    return _clip(s)


def _momentum_pillar(tech, direction, trend: float, reasons) -> float:
    """Momentum as a *trigger*: the dip is ending (MACD turning up, RSI recovering),
    not "already running hot". Overheated RSI is penalized in every regime."""
    rsi = float(tech.get("rsi14", 50))
    hist = float(tech.get("macd_hist", 0))
    hist_prev = float(tech.get("macd_hist_prev", 0))
    rsi_div = (direction or {}).get("rsi_divergence", "NONE")
    pb_state = ((direction or {}).get("pullback") or {}).get("state", "")
    w = PILLAR_WEIGHTS["momentum"]
    s = 0.0

    in_dip = pb_state in ("PULLBACK_IDEAL", "PULLBACK_DEEP")
    if hist < 0 and hist > hist_prev:
        bonus = 0.45 if in_dip else 0.15
        s += bonus
        if in_dip:
            reasons.append((bonus * w, "MACD Mulai Berbalik Naik di Area Pullback (Pemicu Masuk)"))
    elif hist > 0 and hist > hist_prev:
        s += 0.15
    elif hist < 0 and hist < hist_prev:
        s -= 0.3 if trend < 0 else 0.1  # falling momentum: wait, unless it's a dip in an uptrend

    if rsi > 78:
        s -= 0.5
        reasons.append((-0.5 * w, f"RSI Jenuh Beli Ekstrem ({rsi:.0f}) — Rawan Koreksi"))
    elif rsi > 70:
        s -= 0.25
    elif 38 <= rsi <= 55 and in_dip:
        s += 0.2
    elif rsi < 30 and trend <= -0.2 and rsi_div != "BULLISH":
        s -= 0.1  # oversold in a downtrend is not a buy signal by itself

    if rsi_div == "BULLISH":
        s += 0.3
        reasons.append((0.3 * w, "Bullish Divergence RSI (Tekanan Jual Melemah)"))
    elif rsi_div == "BEARISH":
        s -= 0.35
        reasons.append((-0.35 * w, "Bearish Divergence RSI (Momentum Naik Melemah)"))

    return _clip(s)


def _pullback_pillar(direction, reasons) -> Optional[float]:
    pb = (direction or {}).get("pullback") or {}
    state = pb.get("state")
    if not state or state == "INSUFFICIENT_DATA":
        return None
    val = float(pb.get("score", 0.0))
    w = PILLAR_WEIGHTS["pullback"]
    mom = pb.get("long_momentum_pct")
    if state == "PULLBACK_IDEAL":
        reasons.append((val * w + 0.05, f"🎯 {pb.get('label')} · Momentum 6 bln {mom:+.1f}%"))
    elif state == "PULLBACK_DEEP":
        reasons.append((val * w, f"{pb.get('label')}"))
    elif state == "UPTREND_EXTENDED":
        reasons.append((-0.04, f"⏳ {pb.get('label')}"))
    elif state == "TREND_BROKEN":
        reasons.append((val * w - 0.02, f"⚠️ {pb.get('label')}"))
    elif state == "UPTREND_RUNNING":
        reasons.append((val * w, f"{pb.get('label')} · Momentum 6 bln {mom:+.1f}%"))
    return _clip(val)


def _setup_pillar(tech, direction, trend: float, rr_ratio: float, reasons) -> float:
    price = float(tech.get("price", 0))
    e20 = float(tech.get("ema20", 0))
    e50 = float(tech.get("ema50", 0))
    atr = float(tech.get("atr14", 0)) or price * 0.02
    vol_ratio = float(tech.get("vol_ratio", 1.0))
    is_breakout = bool(tech.get("is_breakout", False))
    w = PILLAR_WEIGHTS["setup"]
    s = 0.0

    stretch = (price - e20) / atr if atr > 0 else 0.0
    is_pullback = trend >= 0.2 and -0.6 <= stretch <= 1.0 and price > e50

    # Breakouts are informational: chasing them historically reversed short-term
    if is_breakout:
        reasons.append((0.0, f"Breakout 20 Hari{f' + Volume {vol_ratio:.1f}x' if vol_ratio >= 1.3 else ''} — Lebih Aman Tunggu Retest"))
    elif is_pullback:
        s += 0.3

    if stretch > 3.0:
        s -= 0.5
        reasons.append((-0.5 * w, f"Harga Terlalu Jauh dari EMA20 ({stretch:.1f}x ATR) — Rawan Koreksi"))
    elif stretch > 2.0:
        s -= 0.2

    if (direction or {}).get("squeeze") and trend >= 0:
        s += 0.15
        reasons.append((0.15 * w, "Volatility Squeeze (Persiapan Pergerakan Besar)"))

    candle = (tech.get("candlestick") or {}) if CANDLE_SCORING == "on" else {}
    sig = candle.get("signal", "NEUTRAL")
    rel = candle.get("reliability", "LOW")
    rel_mult = {"HIGH": 1.0, "MEDIUM": 0.7}.get(rel, 0.4)
    # Reversal candles only matter at a meaningful location
    at_support = is_pullback or (trend < 0 and (direction or {}).get("rsi_divergence") == "BULLISH")
    if sig in ("STRONG_BULLISH", "BULLISH"):
        base = 0.35 if sig == "STRONG_BULLISH" else 0.2
        bonus = base * rel_mult * (1.0 if at_support or trend >= 0.2 else 0.5)
        s += bonus
        if bonus >= 0.15:
            reasons.append((bonus * w, f"Pola Candle: {candle.get('label', '')}"))
    elif sig in ("BEARISH", "STRONG_BEARISH"):
        pen = (0.35 if sig == "STRONG_BEARISH" else 0.2) * rel_mult
        s -= pen
        if pen >= 0.15:
            reasons.append((-pen * w, f"Pola Candle: {candle.get('label', '')}"))

    if rr_ratio >= 2.0:
        s += 0.15
    elif rr_ratio < 1.2:
        s -= 0.2

    return _clip(s)


RISK_CATALYST_PREFIX = "RISK:"


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}".replace(",", ".") if v >= 100 else f"{v:,.2f}"


def build_reading(
    tech: Dict[str, Any],
    direction: Optional[Dict[str, Any]],
    sentiment: Dict[str, Any],
    market_mode: str,
    verdict: str,
    is_speculative: bool,
    stop_loss: float,
    target_tp1: float,
) -> Dict[str, Any]:
    """Explicit, deterministic action plan: stance, entry triggers (and whether they are met),
    invalidation level, nearest target, and news overlay. Pure function of the inputs."""
    pb = (direction or {}).get("pullback") or {}
    state = pb.get("state", "INSUFFICIENT_DATA")
    price = float(tech.get("price", 0) or 0)
    ema20 = float(tech.get("ema20", 0) or 0)
    hist = float(tech.get("macd_hist", 0) or 0)
    hist_prev = float(tech.get("macd_hist_prev", 0) or 0)
    # One exit level per card: the plan's cut loss (the pullback support is a structural reference)
    support = stop_loss or pb.get("support_level") or None
    rel = pb.get("relative_momentum_pct")

    triggers = [
        {"label": "MACD histogram berbalik naik", "met": hist > hist_prev},
        {"label": f"Harga tutup di atas EMA20 ({_fmt(ema20)})", "met": price > ema20 > 0},
    ]
    triggers_met = sum(1 for t in triggers if t["met"])

    news_cat = sentiment.get("catalyst") or ""
    news_label = sentiment.get("sentiment_label", "NEUTRAL")
    news_risk = news_cat.startswith(RISK_CATALYST_PREFIX)

    if news_risk:
        stance, headline = "HINDARI", f"Ada berita risiko ({news_cat.replace(RISK_CATALYST_PREFIX, '').strip()}) — hindari sampai jelas."
    elif market_mode == "CRASH":
        stance = "TAHAN"
        headline = ("Pasar krisis: tahan pembelian. " +
                    ("Saham ini termasuk yang terkuat — masukkan daftar pantau untuk saat indeks stabil."
                     if state in ("PULLBACK_IDEAL", "UPTREND_RUNNING") or (rel or 0) > 10 else
                     "Tunggu indeks stabil sebelum menilai ulang."))
    elif is_speculative:
        stance, headline = "HINDARI", "Fundamental lemah (rugi/utang tinggi) — risiko spekulatif."
    elif state == "PULLBACK_IDEAL":
        if triggers_met == 2 and verdict in ("STRONG_BULLISH", "MILD_BULLISH"):
            stance, headline = "LAYAK_DIPERTIMBANGKAN", "Pullback sehat dan pemicu sudah muncul — layak dipertimbangkan dengan batas risiko jelas."
        else:
            stance, headline = "TUNGGU_PEMICU", "Sedang diskon dalam tren naik — tunggu pemicu sebelum masuk."
    elif state == "PULLBACK_DEEP":
        stance, headline = "TUNGGU_PEMICU", "Koreksi dalam — tunggu harga bertahan di atas support dan pemicu muncul."
    elif state == "UPTREND_EXTENDED":
        stance, headline = "TUNGGU_PULLBACK", "Tren naik tapi sudah terlalu panas — tunggu koreksi ke area EMA20."
    elif state == "UPTREND_RUNNING":
        stance, headline = "PANTAU", "Tren naik berjalan tanpa diskon — pantau, entry lebih baik saat pullback."
    elif state == "TREND_BROKEN":
        stance, headline = "HINDARI", "Tren naik rusak (jebol support) — bukan saatnya masuk."
    elif state == "NO_UPTREND":
        stance, headline = "HINDARI", "Belum ada tren naik — strategi pullback tidak berlaku."
    else:
        stance, headline = "NETRAL", "Data belum cukup untuk membaca arah."

    if market_mode == "BEARISH" and stance == "LAYAK_DIPERTIMBANGKAN":
        stance, headline = "TUNGGU_PEMICU", headline + " Namun pasar bearish: kecilkan ukuran posisi atau tunggu indeks pulih."

    news_note = None
    if not news_risk and news_label == "POSITIVE" and news_cat:
        news_note = f"Berita mendukung: {news_cat}"
    elif not news_risk and news_label == "NEGATIVE":
        news_note = f"Berita membebani: {news_cat}"

    return {
        "stance": stance,
        "headline": headline,
        "triggers": triggers,
        "triggers_met": triggers_met,
        "invalidation": f"Batal jika tutup di bawah {_fmt(support)}" if support else None,
        "invalidation_level": round(float(support), 2) if support else None,
        "target": f"Target terdekat {_fmt(target_tp1)}" if target_tp1 else None,
        "news_note": news_note,
    }


def compute_composite_score(
    tech: Dict[str, Any],
    flow: Dict[str, Any],
    sentiment: Dict[str, Any],
    financials: Optional[Dict[str, Any]] = None,
    direction: Optional[Dict[str, Any]] = None,
    market_regime: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Calculate weighted 6-pillar Composite 0-100 Score with Saham Gorengan Shield.

    direction: output of indicators.trend.compute_trend_direction for this stock.
    market_regime: same output computed on the benchmark index (IHSG / S&P 500).
    """
    reasons: List[Tuple[float, str]] = []
    flow_status = flow.get("money_flow_status", "NEUTRAL")

    confluence = evaluate_confluence_breakout(tech, flow, financials, direction)

    pillars: Dict[str, float] = {}
    pb_val = _pullback_pillar(direction, reasons)
    if pb_val is not None:
        pillars["pullback"] = pb_val
    pillars["trend"] = _trend_pillar(tech, direction, reasons)
    trend = pillars["trend"]
    pillars["money_flow"] = _money_flow_pillar(tech, flow, trend, reasons)
    pillars["momentum"] = _momentum_pillar(tech, direction, trend, reasons)
    pillars["setup"] = _setup_pillar(tech, direction, trend, confluence["risk_reward_ratio"], reasons)

    if financials and not financials.get("unavailable"):
        grade = financials.get("health_grade", "MODERATE")
        roe = financials.get("roe", 0.0)
        der = financials.get("debt_to_equity", 0.0)
        if grade == "HEALTHY":
            pillars["fundamental"] = 0.7
            reasons.append((0.07, f"🛡️ Fundamental Sehat (ROE {roe}%, DER {der}%)"))
        elif grade == "DISTRESSED":
            pillars["fundamental"] = -0.8
            reasons.append((-0.08, f"⚠️ Beban Utang/Rugi (ROE {roe}%, DER {der}%)"))
        else:
            pillars["fundamental"] = 0.1

    sent_score = float(sentiment.get("sentiment_score", 0.0) or 0.0)
    if sent_score != 0.0:   # neutral news says nothing: it must not pull the score toward 50
        pillars["sentiment"] = _clip(math.tanh(sent_score / 0.3))
        catalyst = sentiment.get("catalyst", "")
        if sent_score >= 0.20:
            reasons.append((0.06, f"Sentimen Berita Positif ({catalyst})"))
        elif sent_score <= -0.20:
            reasons.append((-0.07, f"Sentimen Berita Negatif ({catalyst})"))

    total_w = sum(PILLAR_WEIGHTS[k] for k in pillars)
    raw = sum(PILLAR_WEIGHTS[k] * v for k, v in pillars.items()) / (total_w or 1.0)
    score = 50.0 + 60.0 * raw

    if confluence["is_confirmed_breakout"]:
        score += 2.0
        reasons.append((0.2, f"🚀 Konfluensi Lolos ({confluence['confluence_score']}/6 Gate)"))

    # The stock's own score before the market brake and the caps below: tie-breaker and
    # signal basis for the actionability gates (the market gets its own gate there)
    raw_score = int(max(0, min(100, round(score))))

    # Market regime filter. In a bear market most dips keep falling, so only
    # relative-strength leaders in a clean pullback may keep a bullish score.
    market_mode = "NORMAL"
    pb = (direction or {}).get("pullback") or {}
    if market_regime:
        idx_dir = market_regime.get("direction_score", 0)
        idx_pb = market_regime.get("pullback") or {}
        idx_mom = idx_pb.get("long_momentum_pct")
        idx_dd = idx_pb.get("drawdown_60d_pct")
        news_level = (market_regime.get("news_risk") or {}).get("level", "NONE")
        if idx_dd is not None and idx_dd <= -20:
            market_mode = "CRASH"
        elif idx_dir <= -30 and (idx_mom is not None and idx_mom <= -10 or idx_dir <= -60):
            market_mode = "BEARISH"
        elif idx_dir <= -30 or news_level == "HIGH":
            market_mode = "CAUTIOUS"
        if news_level in ("HIGH", "ELEVATED") and market_mode != "NORMAL":
            reasons.append((-0.07, "📰 Berita Risiko Sistemik Pasar (mis. MSCI/Trading Halt/Arus Keluar Asing)"))
    if market_mode == "CRASH":
        # Index fell ≥20% from its 60-day high: forced/panic selling hits good and bad stocks alike.
        # No bullish verdicts until the index stabilizes (drawdown back above -20%).
        # Compress (not clip) so the relative ranking of the strongest names survives
        if score > 50:
            score = min(55.0, 50 + (score - 50) * 0.15)
        reasons.append((-0.3, "⛔ Pasar Krisis: IHSG Turun ≥20% dalam 60 Hari — Tahan Pembelian, Utamakan Jaga Modal"))
    elif market_mode != "NORMAL" and score > 50:
        leader = pb.get("state") in ("PULLBACK_IDEAL", "UPTREND_RUNNING") and (pb.get("relative_momentum_pct") or 0) > 0
        if market_mode == "BEARISH":
            score = 50 + (score - 50) * (0.6 if leader else 0.3)
            score = min(score, 72.0 if leader else 58.0)
            reasons.append((-0.06, "🐻 Mode Defensif: Pasar Bearish — Hanya Saham Terkuat yang Layak Dipantau"))
        else:
            score = 50 + (score - 50) * (0.85 if leader else 0.7)
            reasons.append((-0.05, f"⚠️ Indeks Sedang {market_regime.get('direction_label', 'Melemah')}"))

    # Overheated uptrend: strong trend + inflow would otherwise read as a buy, but chasing a
    # stretched move historically reversed. Keep it below the bullish band until it pulls back.
    if pb.get("state") == "UPTREND_EXTENDED" and score > 64:
        score = 64.0

    # No strong-bullish verdict against a strong downtrend
    if trend <= -0.5 and score > 55:
        score = 55.0

    final_score = int(max(0, min(100, round(score))))

    # Saham Gorengan Shield: emiten spekulatif/merugi dibatasi skor maksimal 60
    is_speculative = bool(financials and financials.get("is_speculative", False))
    if is_speculative and final_score > 60:
        final_score = 60

    # Final Classification & Badging
    if market_mode == "CRASH" and not is_speculative and final_score >= 45:
        verdict = "NEUTRAL"
        badge_text = "⛔ PASAR KRISIS — TAHAN DULU"
    elif is_speculative:
        verdict = "NEUTRAL"   # losses/heavy debt: never a buy signal, whatever the chart says
        badge_text = "⚠️ SPEKULATIF (RUGI/UTANG)"
    elif final_score >= 80:
        verdict = "STRONG_BULLISH"
        badge_text = "🟢 POTENSI NAIK TINGGI"
    elif final_score >= 65:
        verdict = "MILD_BULLISH"
        badge_text = "🟡 SINYAL NAIK AWAL"
    elif final_score >= 45:
        verdict = "NEUTRAL"
        badge_text = "⚪ KONSOLIDASI"
    elif final_score >= 30:
        verdict = "MILD_BEARISH"
        badge_text = "🟠 TEKANAN JUAL"
    else:
        verdict = "STRONG_BEARISH"
        badge_text = "🔴 DISTRIBUSI / UANG KELUAR"

    # Most impactful reasons first; when the verdict is bullish, lead with supporting reasons
    reasons.sort(key=lambda r: abs(r[0]), reverse=True)  # zero-impact notes naturally sink
    if final_score >= 55:
        reasons.sort(key=lambda r: r[0] < 0)
    elif final_score < 45:
        reasons.sort(key=lambda r: r[0] > 0)
    if market_mode in ("CRASH", "BEARISH"):
        # The market condition outranks any single-stock argument: always show it first
        reasons.sort(key=lambda r: not (r[1].startswith("⛔") or r[1].startswith("🐻")))
    is_confirmed = bool(confluence["is_confirmed_breakout"])
    if market_mode == "CRASH":
        # No "confirmed" setups while the whole market is in forced selling
        is_confirmed = False
        reasons = [r for r in reasons if not r[1].startswith("🚀 Konfluensi")]
    if is_speculative:
        reasons.insert(0, (-0.3, "⚠️ Saham Spekulatif: Kinerja keuangan rugi / utang tinggi"))
    reason_texts = [text for _, text in reasons]
    # Sign of each reason (+1 supports a rise, -1 argues against, 0 neutral note), so the UI never
    # puts a green check next to "⛔ Pasar Krisis" or "Uang Keluar Deras"
    reason_signs = [(impact > 0) - (impact < 0) for impact, _ in reasons]

    return {
        "score": final_score,
        "verdict": verdict,
        "badge_text": badge_text,
        "money_flow_status": flow_status,
        "reasons": reason_texts[:5],
        "reason_signs": reason_signs[:5],
        "pillars": {k: round(v, 2) for k, v in pillars.items()},
        "raw_score": raw_score,
        "pillar_values": {k: round(v, 3) for k, v in pillars.items()},
        "market_mode": market_mode,
        "pullback_state": pb.get("state"),
        "pullback_label": pb.get("label"),
        "is_confirmed_breakout": is_confirmed,
        "confluence_score": confluence["confluence_score"],
        "confluence_gates": confluence["confluence_gates"],
        "risk_reward_ratio": confluence["risk_reward_ratio"],
        "target_tp": confluence["target_tp"],
        "target_tp1": confluence["target_tp1"],
        "target_tp2": confluence["target_tp2"],
        "stop_loss": confluence["stop_loss"],
        "entry_low": confluence["entry_low"],
        "entry_high": confluence["entry_high"],
        "recommended_entry": confluence["recommended_entry"],
        "levels": confluence.get("levels"),
        "is_speculative": is_speculative,
        "reading": build_reading(tech, direction, sentiment, market_mode, verdict, is_speculative,
                                 confluence["stop_loss"], confluence["target_tp1"]),
    }
