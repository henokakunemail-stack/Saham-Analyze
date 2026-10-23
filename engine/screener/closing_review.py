"""Analisa Penutupan: the plan built from the last final close, read honestly.

For each stock the Top 10 page shows (a) what the last session did to the plan it traded on
(session_recap) and (b) the plan for the next session with an assessment built from backtest
numbers, not adjectives: how likely the buy limit is to fill from where the stock closed, how
much room is left to TP1 against the risk, whether the normal daily range is wider than the
stop distance. Pure functions; the route assembles the rows.

Numbers: walk-forward backtest, 126 IDX stocks, 29 Apr 2024 – 9 Oct 2026, 23,923 plans, buy limit
held 5 trading days (docs/hasil-akhir-fase1-5.md, "Peringkat").
"""
from typing import Any, Dict, List, Optional

# Share of plans whose buy limit filled within 5 trading days, by how far the close stood above the
# buy zone (in ATR). Both periods agree within a few points: ≤0.25 76.6/80.3 %, 0.25–0.5 60.0/61.8 %,
# 0.5–1 41.9/41.1 %, 1–1.5 27.3/23.0 %; > 1.5 ATR only 16 plans (12.5 %).
FILL_BY_DISTANCE = ((0.25, 78), (0.5, 61), (1.0, 41), (1.5, 25), (float("inf"), 15))

# Average outcome per status in the test period (Dec 2025 – Oct 2026), before fees.
STATUS_HISTORY = {
    "LAYAK": {"avg_r": 0.116, "plans": 253, "filled": 182},
    "TUNGGU": {"avg_r": -0.052, "plans": 3408, "filled": 2521},
    "HINDARI": {"avg_r": -0.115, "plans": 4464, "filled": 2991},
}


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _id(v: float, digits: int = 1) -> str:
    """Indonesian decimal: 3,5 / 12."""
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{v:.0f}"
    return s.replace(".", ",")


def _price(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") if v >= 100 else _id(v, 2)


def fill_chance(close: float, entry_high: float, atr: float) -> Dict[str, Any]:
    """Backtest fill rate for a buy zone `entry_high` when the stock closed at `close`."""
    dist = max(0.0, (close - entry_high) / atr) if atr > 0 else 0.0
    pct = next(p for limit, p in FILL_BY_DISTANCE if dist <= limit)
    return {"dist_atr": round(dist, 2), "fill_pct": pct}


def assess(levels: Dict[str, Any], action: Optional[Dict[str, Any]] = None,
           screen: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Honest reading of a plan built from a final close. Returns {verdict, points, fill_pct, dist_atr}."""
    lv = levels or {}
    close = _f(lv.get("price"))
    buy = _f(lv.get("recommended_entry"))
    eh, sl, tp1 = _f(lv.get("entry_high")), _f(lv.get("stop_loss")), _f(lv.get("target_tp1"))
    atr = _f(lv.get("atr14")) or 0.0
    if not (close and buy and eh and sl and tp1):
        return {"verdict": "Rencana belum tersedia untuk saham ini.", "points": [], "fill_pct": None, "dist_atr": None}

    status = (action or {}).get("status")
    reason = ((action or {}).get("reasons") or [None])[0]
    if status == "LAYAK":
        verdict = f"Layak dipasang order beli limit di {_price(buy)}."
    elif status == "HINDARI":
        verdict = f"Hindari{': ' + reason if reason else ''}."
    elif status == "TUNGGU":
        verdict = f"Belum layak dibeli{': ' + reason if reason else ''}."
    else:
        verdict = f"Rencana: beli limit {_price(buy)}, cut loss {_price(sl)}, TP1 {_price(tp1)}."

    points: List[str] = []
    caution: Optional[str] = None   # the one warning shown without expanding the row
    fc = fill_chance(close, eh, atr)
    below = (1 - buy / close) * 100
    if close <= eh:
        points.append(f"Penutupan sudah di zona beli — peluang order limit {_price(buy)} terisi dalam 5 hari bursa "
                      f"±{fc['fill_pct']}% (uji historis).")
    else:
        points.append(f"Harga beli {_price(buy)} ada {_id(below)}% di bawah penutupan ({_id(fc['dist_atr'], 2)}× gerak harian) "
                      f"— peluang terisi dalam 5 hari bursa ±{fc['fill_pct']}% (uji historis).")

    risk = (buy - sl) / buy * 100
    reward = (tp1 - buy) / buy * 100
    rr = _f(lv.get("risk_reward_ratio")) or (reward / risk if risk > 0 else None)
    if tp1 <= close:
        points.append(f"TP1 {_price(tp1)} sudah tercapai di harga penutupan — sisa ruang naik ke target kecil; "
                      f"untung hanya bila harga turun dulu ke harga beli lalu naik lagi.")
        caution = "Target 1 sudah tercapai di harga penutupan"
    elif rr is not None and rr < 1.2:
        points.append(f"Ruang ke TP1 hanya +{_id(reward)}% dengan risiko −{_id(risk)}% (Rugi : Untung 1 : {_id(rr, 2)}) "
                      f"— untung kecil dibanding risiko.")
        caution = f"Untung ke TP1 (+{_id(reward)}%) lebih kecil dari risiko (−{_id(risk)}%)"
    elif rr is not None and rr >= 2:
        points.append(f"Ruang ke TP1 +{_id(reward)}% dengan risiko −{_id(risk)}% (1 : {_id(rr, 2)}) — sepadan.")
    else:
        points.append(f"Ruang ke TP1 +{_id(reward)}%, risiko −{_id(risk)}%.")

    flags = lv.get("flags") or []
    atr_pct = _f((screen or {}).get("atr_pct")) or (atr / close * 100 if close else None)
    if "too_volatile" in flags:
        points.append(f"Gerak harian normal ±{_id(atr_pct)}% lebih lebar dari jarak cut loss — "
                      f"mudah kena cut loss oleh gerak biasa." if atr_pct else
                      "Gerak harian normal lebih lebar dari jarak cut loss — mudah kena cut loss oleh gerak biasa.")
        caution = caution or "Gerak harian lebih lebar dari jarak cut loss"
    if "market_entry" in flags:
        points.append("Tidak ada support dekat: harga beli sama dengan harga pasar, tanpa bantalan support.")
    return {"verdict": verdict, "points": points, "caution": caution,
            "fill_pct": fc["fill_pct"], "dist_atr": fc["dist_atr"],
            "risk_pct": round(risk, 2), "reward_pct": round(reward, 2), "rr": round(rr, 2) if rr is not None else None}


def build(ranked: List[Dict[str, Any]], recap: Optional[Dict[str, Any]], watchlist: List[str],
          top: int = 10) -> Dict[str, Any]:
    """Rows for the panel: today's Top 10 (with their plan for the next session), plus stocks that
    were in the list the last session traded on or in the watchlist; each with its recap if any."""
    recap_rows = {r["ticker"]: r for r in (recap or {}).get("rows", [])}
    by_ticker = {r["ticker"]: r for r in ranked}
    top_set = {r["ticker"] for r in ranked[:top]}
    order: List[str] = [r["ticker"] for r in ranked[:top]]
    for t in list(recap_rows) + list(watchlist):
        if t not in order and (t in by_ticker or t in recap_rows):
            order.append(t)
    rows = []
    for t in order:
        row = by_ticker.get(t) or {}
        lv = row.get("levels") or {}
        rows.append({
            "ticker": t,
            "in_top": t in top_set,
            "watchlist": t in watchlist,
            "status": (row.get("action") or {}).get("status"),
            "plan": {k: lv.get(k) for k in ("price", "as_of", "recommended_entry", "entry_low", "entry_high",
                                            "stop_loss", "target_tp1", "target_tp2", "risk_reward_ratio")} if lv else None,
            "assessment": assess(lv, row.get("action"), row.get("screen")) if lv else None,
            "recap": recap_rows.get(t),
        })
    plan_dates = sorted({str((r.get("levels") or {}).get("as_of") or "")[:10] for r in ranked[:top]} - {""})
    return {"plan_as_of": plan_dates[-1] if plan_dates else None,
            "session_date": (recap or {}).get("session_date"),
            "recap_plan_as_of": (recap or {}).get("plan_as_of"),
            "counts": (recap or {}).get("counts"),
            "status_history": STATUS_HISTORY,
            "rows": rows}
