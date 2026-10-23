"""Candlestick patterns, read the way the textbooks define them — in context and at a real size.

Changes from the first version (docs/hasil-uji-candlestick.md):
- a one-price bar (ARA/ARB lock, or no trading) is LOCKED, never a hammer;
- a doji is checked before hammer / shooting star (a doji with a long lower shadow is not a hammer);
- reversal patterns need the move they reverse: bullish after a decline, bearish after an advance
  (close of the bar before the pattern vs 5 bars earlier);
- a pattern needs a real size: the bar's range (or the engulfed body) is compared with ATR;
- bearish counterparts exist for every bullish pattern (engulfing, dark cloud, harami, three crows),
  so the reading is not biased toward "buy".
`reliability` is the textbook label only; whether a pattern helped on IDX is measured separately
(engine/screener/candle_study.py) and shown next to it.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

NEUTRAL = {"pattern": "NORMAL", "label": "Konsolidasi / Stabil", "signal": "NEUTRAL", "reliability": "LOW",
           "description": "Pergerakan harga dalam rentang wajar tanpa pola pembalikan khusus."}

PATTERNS: Dict[str, Dict[str, str]] = {
    "LOCKED": {"label": "Harga Terkunci (satu harga)", "signal": "NEUTRAL", "reliability": "LOW",
               "description": "Seharian hanya satu harga (ARA/ARB atau transaksi sangat sepi) — bukan pola candle."},
    "THREE_WHITE_SOLDIERS": {"label": "Three White Soldiers (3 candle hijau kuat)", "signal": "STRONG_BULLISH",
                             "reliability": "HIGH",
                             "description": "Tiga candle hijau berbadan besar berturut-turut dengan penutupan makin tinggi setelah penurunan."},
    "THREE_BLACK_CROWS": {"label": "Three Black Crows (3 candle merah kuat)", "signal": "STRONG_BEARISH",
                          "reliability": "HIGH",
                          "description": "Tiga candle merah berbadan besar berturut-turut dengan penutupan makin rendah setelah kenaikan."},
    "MORNING_STAR": {"label": "Morning Star (pembalikan naik 3 candle)", "signal": "STRONG_BULLISH", "reliability": "HIGH",
                     "description": "Candle merah besar, candle kecil, lalu candle hijau yang menutup lebih dari separuh badan candle merah."},
    "EVENING_STAR": {"label": "Evening Star (pembalikan turun 3 candle)", "signal": "STRONG_BEARISH", "reliability": "HIGH",
                     "description": "Candle hijau besar, candle kecil, lalu candle merah yang menutup lebih dari separuh badan candle hijau."},
    "BULLISH_ENGULFING": {"label": "Bullish Engulfing (candle hijau menelan merah)", "signal": "STRONG_BULLISH",
                          "reliability": "HIGH",
                          "description": "Setelah turun, candle hijau menelan seluruh badan candle merah sebelumnya."},
    "BEARISH_ENGULFING": {"label": "Bearish Engulfing (candle merah menelan hijau)", "signal": "STRONG_BEARISH",
                          "reliability": "HIGH",
                          "description": "Setelah naik, candle merah menelan seluruh badan candle hijau sebelumnya."},
    "PIERCING_LINE": {"label": "Piercing Line (tembus separuh candle merah)", "signal": "BULLISH", "reliability": "MEDIUM",
                      "description": "Dibuka di bawah penutupan kemarin, lalu ditutup di atas separuh badan candle merah kemarin."},
    "DARK_CLOUD_COVER": {"label": "Dark Cloud Cover (awan gelap)", "signal": "BEARISH", "reliability": "MEDIUM",
                         "description": "Dibuka di atas penutupan kemarin, lalu ditutup di bawah separuh badan candle hijau kemarin."},
    "BULLISH_HARAMI": {"label": "Bullish Harami (tekanan jual mereda)", "signal": "BULLISH", "reliability": "MEDIUM",
                       "description": "Candle hijau kecil di dalam badan candle merah besar sebelumnya."},
    "BEARISH_HARAMI": {"label": "Bearish Harami (tekanan beli mereda)", "signal": "BEARISH", "reliability": "MEDIUM",
                       "description": "Candle merah kecil di dalam badan candle hijau besar sebelumnya."},
    "HAMMER": {"label": "Hammer (penolakan harga bawah)", "signal": "BULLISH", "reliability": "MEDIUM",
               "description": "Setelah turun: ekor bawah panjang, badan kecil di atas — pembeli menolak harga lebih rendah."},
    "HANGING_MAN": {"label": "Hanging Man (waspada di puncak)", "signal": "BEARISH", "reliability": "MEDIUM",
                    "description": "Setelah naik: ekor bawah panjang, badan kecil di atas — mulai ada tekanan jual."},
    "INVERTED_HAMMER": {"label": "Inverted Hammer (uji dorongan beli)", "signal": "BULLISH", "reliability": "LOW",
                        "description": "Setelah turun: ekor atas panjang, badan kecil di bawah — percobaan naik yang belum berhasil."},
    "SHOOTING_STAR": {"label": "Shooting Star (penolakan harga atas)", "signal": "BEARISH", "reliability": "MEDIUM",
                      "description": "Setelah naik: ekor atas panjang, badan kecil di bawah — penjual menolak harga lebih tinggi."},
    "DOJI": {"label": "Doji (pasar ragu)", "signal": "NEUTRAL", "reliability": "LOW",
             "description": "Harga pembukaan dan penutupan hampir sama — pasar menunggu arah."},
    "BULLISH_BODY": {"label": "Candle Hijau", "signal": "BULLISH", "reliability": "LOW",
                     "description": "Penutupan di atas pembukaan (hanya warna candle, bukan pola)."},
    "BEARISH_BODY": {"label": "Candle Merah", "signal": "BEARISH", "reliability": "LOW",
                     "description": "Penutupan di bawah pembukaan (hanya warna candle, bukan pola)."},
}

CONTEXT_BARS = 5
_STATS_PATH = Path(__file__).resolve().parent.parent / "data" / "candle_stats.json"
_stats: Optional[Dict[str, Any]] = None


def _pct(v: float) -> str:
    return f"{v:+.1f}".replace(".", ",") + "%"


def evidence(pattern: str) -> Optional[Dict[str, Any]]:
    """What this pattern was followed by on IDX (engine/data/candle_stats.json, from the event study):
    10-day return vs all stocks on the same day, early and test period, and a plain verdict."""
    global _stats
    if _stats is None:
        try:
            _stats = json.loads(_STATS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _stats = {}
    p = (_stats.get("patterns") or {}).get(pattern)
    if not p or p.get("verdict") == "bukan_pola":
        return None
    a, b = p["periods"].get("in"), p["periods"].get("oos")
    v = p["verdict"]
    if v == "data_kurang" or not a or not b:
        text = "Kejadian pola ini di IDX masih terlalu sedikit untuk dinilai."
    else:
        moves = f"10 hari setelahnya rata-rata {_pct(a['x10'])} (periode awal) dan {_pct(b['x10'])} (periode uji) dibanding saham lain"
        if v == "terbukti":
            text = f"Di IDX pola ini cenderung diikuti hasil {'lebih baik' if p['direction'] == 'naik' else 'lebih buruk'} dari rata-rata: {moves} — selisihnya kecil."
        else:
            text = f"Di IDX pola ini tidak terbukti mendahului {'kenaikan' if p['direction'] == 'naik' else 'penurunan'}: {moves}."
    return {"verdict": v, "direction": p.get("direction"), "text": text,
            "n": (a or {}).get("n", 0) + (b or {}).get("n", 0)}


def _result(name: str) -> Dict[str, Any]:
    return {"pattern": name, **PATTERNS[name]}


def _atr(df: pd.DataFrame) -> float:
    tail = df.iloc[-40:]
    h, l, c = tail["high"].astype(float), tail["low"].astype(float), tail["close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    return atr if atr > 0 else float(c.iloc[-1]) * 0.02


def _trend_before(df: pd.DataFrame, start: int) -> float:
    """Close change into the pattern: close of the bar before it vs CONTEXT_BARS bars earlier (in ATR units
    is not needed: only the sign matters)."""
    end = len(df) + start - 1          # index of the bar before the pattern's first bar
    if end - CONTEXT_BARS < 0:
        return 0.0
    c = df["close"].astype(float)
    return float(c.iloc[end] - c.iloc[end - CONTEXT_BARS])


def detect(df: pd.DataFrame, atr: Optional[float] = None) -> Dict[str, Any]:
    """Pattern of the last bar (or last 2–3 bars). `df` oldest first with open/high/low/close."""
    if df is None or len(df) < 3:
        return dict(NEUTRAL)
    atr = atr or _atr(df)
    o, h, l, c = (df[k].astype(float) for k in ("open", "high", "low", "close"))
    O, H, L, C = o.iloc[-1], h.iloc[-1], l.iloc[-1], c.iloc[-1]
    rng = H - L
    if rng <= max(C, 1e-9) * 1e-6:
        return _result("LOCKED")
    body = abs(C - O)
    up, down = C > O, C < O
    p_o, p_c = o.iloc[-2], c.iloc[-2]
    p_body = abs(p_c - p_o)
    p_rng = h.iloc[-2] - l.iloc[-2]

    def big(i: int) -> bool:   # a "real" candle: body ≥ 0.3 ATR and ≥ half its range
        b, r = abs(c.iloc[i] - o.iloc[i]), h.iloc[i] - l.iloc[i]
        return b >= 0.3 * atr and r > 0 and b >= 0.5 * r

    # ── three bars ───────────────────────────────────────────────────────────
    if len(df) >= 3 + CONTEXT_BARS:
        g = [c.iloc[i] > o.iloc[i] for i in (-3, -2, -1)]
        r = [c.iloc[i] < o.iloc[i] for i in (-3, -2, -1)]
        if all(g) and all(big(i) for i in (-3, -2, -1)) and c.iloc[-3] < c.iloc[-2] < C and _trend_before(df, -3) < 0:
            return _result("THREE_WHITE_SOLDIERS")
        if all(r) and all(big(i) for i in (-3, -2, -1)) and c.iloc[-3] > c.iloc[-2] > C and _trend_before(df, -3) > 0:
            return _result("THREE_BLACK_CROWS")
        b3 = abs(c.iloc[-3] - o.iloc[-3])
        small_mid = p_body <= 0.3 * b3
        if r[0] and big(-3) and small_mid and up and C >= c.iloc[-3] + 0.5 * b3 and _trend_before(df, -3) < 0:
            return _result("MORNING_STAR")
        if g[0] and big(-3) and small_mid and down and C <= c.iloc[-3] - 0.5 * b3 and _trend_before(df, -3) > 0:
            return _result("EVENING_STAR")

    # ── two bars ─────────────────────────────────────────────────────────────
    trend2 = _trend_before(df, -2)
    prev_red, prev_green = p_c < p_o, p_c > p_o
    prev_real = p_body >= 0.3 * atr
    if prev_real and prev_red and up and O <= p_c and C >= p_o and body > p_body and trend2 < 0:
        return _result("BULLISH_ENGULFING")
    if prev_real and prev_green and down and O >= p_c and C <= p_o and body > p_body and trend2 > 0:
        return _result("BEARISH_ENGULFING")
    if prev_real and prev_red and up and O < p_c and (p_o + p_c) / 2 <= C < p_o and trend2 < 0:
        return _result("PIERCING_LINE")
    if prev_real and prev_green and down and O > p_c and p_o < C <= (p_o + p_c) / 2 and trend2 > 0:
        return _result("DARK_CLOUD_COVER")
    not_doji = body > 0.1 * rng
    if prev_real and prev_red and up and not_doji and O >= p_c and C <= p_o and body < 0.6 * p_body and trend2 < 0:
        return _result("BULLISH_HARAMI")
    if prev_real and prev_green and down and not_doji and O <= p_c and C >= p_o and body < 0.6 * p_body and trend2 > 0:
        return _result("BEARISH_HARAMI")

    # ── one bar ──────────────────────────────────────────────────────────────
    lower = min(O, C) - L
    upper = H - max(O, C)
    trend1 = _trend_before(df, -1)
    if body <= 0.1 * rng:
        return _result("DOJI")
    if rng >= 0.5 * atr:
        if lower >= 2 * body and upper <= 0.25 * rng:
            if trend1 < 0:
                return _result("HAMMER")
            if trend1 > 0:
                return _result("HANGING_MAN")
        if upper >= 2 * body and lower <= 0.25 * rng:
            if trend1 < 0:
                return _result("INVERTED_HAMMER")
            if trend1 > 0:
                return _result("SHOOTING_STAR")
    return _result("BULLISH_BODY" if up else "BEARISH_BODY") if (up or down) else dict(NEUTRAL)
