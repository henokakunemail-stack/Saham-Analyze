"""Entry zone, cut loss and take-profit levels that respect the real market.

- Prices land on valid exchange ticks (IDX "fraksi harga"; US cents).
- Levels come from actual structure: confirmed swing highs/lows, 20/60-day extremes and
  EMA20/EMA50. Nearby levels (closer than 0.5 ATR) are merged into one zone.
- TP1 is the nearest resistance above the entry: it is never pushed further just to make
  the reward/risk look better. When room is tight the plan says so (flag `tight_room`).
- The stop sits under the nearest structural support below the entry zone, at least
  1 ATR away and at most 8% (flag `wide_stop` when the structure is further than that).
"""
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ..collectors.data_quality import bar_is_final
from ..indicators.trend import find_pivots
from ..collectors import abnormal_days

# Fase 2: ARA/ARB-locked, suspension and corporate-action bars are kept out of the ATR and the
# swing pivots. Off until the Fase 5 backtest shows it does not hurt (docs/PLAN_EKSEKUSI_FASE.md).
CLEAN_LEVELS = os.environ.get("SAHAM_CLEAN_LEVELS", "0") == "1"
# Candidates (under test, docs/hasil-akhir-fase1-5.md):
# TP1 must stay above the close the plan is made from after tick rounding
TP_ABOVE_CLOSE = os.environ.get("SAHAM_TP_ABOVE_CLOSE", "0") == "1"
# The stop may sit under the lower part of the support zone the entry stands on
STOP_UNDER_NEAR_ZONE = os.environ.get("SAHAM_STOP_NEAR_ZONE", "0") == "1"
# Zones grow only while a level is within MERGE_ATR of the zone's bottom (no chaining)
MERGE_FROM_BOTTOM = os.environ.get("SAHAM_MERGE_FROM_BOTTOM", "0") == "1"

IDX_TICKS = ((200, 1), (500, 2), (2000, 5), (5000, 10), (math.inf, 25))
IDX_LOT = 100
MAX_RISK_PCT = 0.08
MERGE_ATR = 0.5
LOOKBACK = 120
TP_MIN_ATR = 0.0   # minimum distance (in ATR) from the entry for a level to count as TP1


def tick_size(price: float, market: str = "IDX") -> float:
    if market != "IDX":
        return 0.01
    for limit, tick in IDX_TICKS:
        if price < limit:
            return tick
    return IDX_TICKS[-1][1]


def round_to_tick(price: float, market: str = "IDX", mode: str = "down") -> float:
    """Snap a price onto the exchange tick grid ('down', 'up' or 'nearest')."""
    if price is None or not math.isfinite(price) or price <= 0:
        return 0.0
    tick = tick_size(price, market)
    q = price / tick
    n = math.floor(q + 1e-9) if mode == "down" else math.ceil(q - 1e-9) if mode == "up" else round(q)
    value = n * tick
    # Crossing a tick-band boundary can change the tick (e.g. 1999 → 2000); re-snap once
    t2 = tick_size(value, market)
    if t2 != tick:
        q2 = value / t2
        value = (math.floor(q2 + 1e-9) if mode != "up" else math.ceil(q2 - 1e-9)) * t2
    return round(value, 2)


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") if v >= 100 else f"{v:,.2f}"


def _clusters(levels: List[Dict[str, Any]], atr: float) -> List[Dict[str, Any]]:
    """Merge levels closer than MERGE_ATR × ATR into zones (sorted ascending)."""
    out: List[Dict[str, Any]] = []
    for lv in sorted(levels, key=lambda x: x["price"]):
        if out and lv["price"] - out[-1]["bottom" if MERGE_FROM_BOTTOM else "top"] <= MERGE_ATR * atr:
            z = out[-1]
            z["top"] = max(z["top"], lv["price"])
            z["items"].append(lv)
        else:
            out.append({"bottom": lv["price"], "top": lv["price"], "items": [lv]})
    return out


def zone_label(zone: Dict[str, Any], edge: str, shown: Optional[float] = None) -> str:
    """Name the level actually used: the zone's top ('top') or bottom ('bottom'), e.g. '2.330 (puncak swing)'.
    `shown`: the tick-rounded price the plan uses, so the text matches the number on screen."""
    target = zone[edge]
    item = min(zone["items"], key=lambda it: abs(it["price"] - target))
    return f"{_fmt(item['price'] if shown is None else shown)} ({item['source']})"


def build_ladder(df: pd.DataFrame, atr: float, pivot_mask: Optional[np.ndarray] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Support zones below and resistance zones above the last close. `pivot_mask` (False =
    abnormal bar) keeps locked/corporate-action bars from becoming swing points."""
    look = df.iloc[-LOOKBACK:].reset_index(drop=True)
    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    levels: List[Dict[str, Any]] = []
    m = pivot_mask[-len(look):] if pivot_mask is not None else None
    highs = abnormal_days.find_pivots_masked(look["high"], m, "high") if m is not None else find_pivots(look["high"], kind="high")
    lows = abnormal_days.find_pivots_masked(look["low"], m, "low") if m is not None else find_pivots(look["low"], kind="low")
    for i in highs:
        levels.append({"price": float(look["high"].iloc[i]), "source": "puncak swing"})
    for i in lows:
        levels.append({"price": float(look["low"].iloc[i]), "source": "lembah swing"})
    hist = df.iloc[:-1]  # exclude today's bar from range extremes
    for n in (20, 60):
        if len(hist) >= n:
            levels.append({"price": float(hist["high"].iloc[-n:].max()), "source": f"high {n} hari"})
            levels.append({"price": float(hist["low"].iloc[-n:].min()), "source": f"low {n} hari"})
    for span in (20, 50):
        if len(close) >= span:
            levels.append({"price": float(close.ewm(span=span, adjust=False).mean().iloc[-1]), "source": f"EMA{span}"})

    below = [lv for lv in levels if lv["price"] < price * 0.999]
    above = [lv for lv in levels if lv["price"] > price * 1.001]
    return {"supports": _clusters(below, atr)[::-1],   # nearest first
            "resistances": _clusters(above, atr)}       # nearest first


def compute_trade_levels(df: pd.DataFrame, market: str = "IDX", is_breakout: bool = False,
                         breakout_level: Optional[float] = None) -> Dict[str, Any]:
    """Market-consistent entry zone, stop, TP1/TP2, R:R and the basis of each level."""
    close = df["close"].astype(float)
    high, low = df["high"].astype(float), df["low"].astype(float)
    price = float(close.iloc[-1])
    kinds = abnormal_days.classify_bars(df, market) if CLEAN_LEVELS else None
    if kinds is not None:
        tr = abnormal_days.clean_true_range(df, kinds)
    else:
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]) or price * 0.02
    as_of = str(df["date"].iloc[-1])[:10] if "date" in df.columns else None
    ladder = build_ladder(df, atr, abnormal_days.pivot_mask(kinds) if kinds is not None else None)
    supports, resistances = ladder["supports"], ladder["resistances"]
    flags: List[str] = []

    # ── Entry zone ──────────────────────────────────────────────────────────
    near_support = next((z for z in supports if price - z["top"] <= 1.5 * atr), None)
    if is_breakout and breakout_level:
        entry_high = price
        entry_low = max(float(breakout_level), price - 0.5 * atr)
        entry_basis = f"retest area breakout {_fmt(float(breakout_level))}"
    elif near_support:
        entry_low = near_support["top"] - 0.25 * atr
        entry_high = min(price, near_support["top"] + 0.25 * atr)
        entry_basis = f"support {zone_label(near_support, 'top')}"
    else:
        entry_high = price
        entry_low = price - 0.3 * atr
        entry_basis = "harga pasar (tidak ada support dalam 1,5×ATR)"
        flags.append("market_entry")
    entry_high = round_to_tick(entry_high, market, "down")
    entry_low = round_to_tick(min(entry_low, entry_high), market, "down")
    if entry_low >= entry_high:
        entry_low = round_to_tick(entry_high - tick_size(entry_high, market), market, "down")
    recommended = round_to_tick((entry_low + entry_high) / 2, market, "down")
    recommended = min(max(recommended, entry_low), entry_high)

    # ── Cut loss under the nearest structure below the entry zone ──────────
    edge = "bottom" if STOP_UNDER_NEAR_ZONE else "top"
    below_zone = next((z for z in supports if z[edge] < entry_low - 0.1 * atr), None)
    if below_zone:
        stop = below_zone["bottom"] - 0.25 * atr
        stop_basis = f"di bawah support {zone_label(below_zone, 'bottom')}"
    else:
        stop = entry_low - 1.2 * atr
        stop_basis = "1,2×ATR di bawah zona entry"
    stop = round_to_tick(min(stop, recommended - 1.0 * atr), market, "down")   # give it room to breathe
    # Cap the risk after rounding (rounding down can push it past the cap); the capped stop
    # rounds toward the entry so the risk never exceeds the cap
    cap_pct = round(MAX_RISK_PCT * 100)
    if recommended - stop > MAX_RISK_PCT * recommended:
        stop = round_to_tick(recommended * (1 - MAX_RISK_PCT), market, "up")
        stop_basis += f" (dibatasi risiko maks {cap_pct}%)"
        flags.append("wide_stop")
    if stop >= entry_low:
        stop = round_to_tick(entry_low - tick_size(entry_low, market), market, "down")
        if recommended - stop > MAX_RISK_PCT * recommended:
            # The entry zone itself is wider than the cap allows (ATR close to the price)
            stop_basis = stop_basis.replace(f" (dibatasi risiko maks {cap_pct}%)", "")
            stop_basis += f" — zona beli lebih lebar dari batas risiko {cap_pct}%"
            if "wide_stop" not in flags:
                flags.append("wide_stop")
    if "wide_stop" in flags and recommended - stop < atr:
        # The 8% cap put the stop inside one day's normal range: ordinary noise can hit it
        flags.append("too_volatile")

    # ── Take profit at real resistance ──────────────────────────────────────
    # Compare on the tick grid: a level just above the entry can round back down onto it
    targets = [z for z in resistances if round_to_tick(z["bottom"], market, "down") > entry_high
               and z["bottom"] >= recommended + TP_MIN_ATR * atr
               and (not TP_ABOVE_CLOSE or round_to_tick(z["bottom"], market, "down") > price)]
    if targets:
        tp1 = round_to_tick(targets[0]["bottom"], market, "down")
        tp1_basis = f"resistance {zone_label(targets[0], 'bottom', tp1)}"
    else:
        tp1 = round_to_tick(recommended + 2.0 * atr, market, "down")
        tp1_basis = "proyeksi 2×ATR (belum ada resistance tercatat)"
        flags.append("projected_tp1")
    nxt = next((z for z in targets[1:] if z["bottom"] > tp1 + 0.5 * atr), None) if targets else None
    if nxt:
        tp2 = nxt["bottom"]
        tp2_basis = f"resistance {zone_label(nxt, 'bottom', round_to_tick(tp2, market, 'down'))}"
    else:
        tp2 = tp1 + 1.5 * atr
        tp2_basis = "proyeksi TP1 + 1,5×ATR"
    tp2 = round_to_tick(tp2, market, "down")
    if tp2 <= tp1:
        tp2 = round_to_tick(tp1 + tick_size(tp1, market), market, "up")

    risk = max(recommended - stop, 1e-9)
    reward = max(tp1 - recommended, 0.0)
    rr = round(reward / risk, 2)
    if rr < 1.2:
        flags.append("tight_room")

    return {
        "price": round(price, 2),
        "tick": tick_size(recommended, market),
        "entry_low": entry_low,
        "entry_high": entry_high,
        "recommended_entry": recommended,
        "stop_loss": stop,
        "target_tp1": tp1,
        "target_tp2": tp2,
        "risk_reward_ratio": rr,
        "risk_pct": round(risk / recommended * 100, 2),
        "reward_pct": round(reward / recommended * 100, 2),
        "risk_per_lot": round(risk * IDX_LOT, 0) if market == "IDX" else None,
        "entry_basis": entry_basis,
        "stop_basis": stop_basis,
        "tp1_basis": tp1_basis,
        "tp2_basis": tp2_basis,
        "flags": flags,
        "atr14": round(atr, 4),
        # Nearest structure on each side, for the chart (max 3 each, nearest first)
        "ladder": {
            "supports": [{"price": round_to_tick(z["top"], market, "nearest"), "label": zone_label(z, "top")}
                         for z in supports[:3]],
            "resistances": [{"price": round_to_tick(z["bottom"], market, "nearest"), "label": zone_label(z, "bottom")}
                            for z in resistances[:3]],
        },
        # Which close the levels stand on, and whether that session had already ended
        "market": market,
        "as_of": as_of,
        "bar_final": bar_is_final(as_of, market) if as_of else None,
        "computed_at": datetime.now().astimezone().isoformat(timespec="minutes"),
    }


# Where a live price stands against a plan, most urgent first in the checkpoint list
POSITION_ORDER = ("BELOW_STOP", "AT_TP2", "AT_TP1", "IN_ZONE", "TESTING_SUPPORT", "ABOVE_ZONE")
# Above the zone by more than this many ATR a buy limit in the zone is unlikely to fill today
FAR_ABOVE_ATR = 1.0


def plan_position(levels: Dict[str, Any], price: float, high: Optional[float] = None,
                  low: Optional[float] = None) -> Dict[str, Any]:
    """Status of the current price against a plan made from an earlier close (same rules as the
    opening guide: don't chase above the zone, the plan is void under the stop)."""
    el, eh, sl = levels["entry_low"], levels["entry_high"], levels["stop_loss"]
    tp1, tp2 = levels["target_tp1"], levels["target_tp2"]
    touched_stop = low is not None and low <= sl
    # A target touched earlier today still counts after the price slips back (holders would have
    # sold there); only when the stop was not touched too, since then the order of events is unknown
    hit_tp2 = not touched_stop and high is not None and high >= tp2
    hit_tp1 = not touched_stop and high is not None and high >= tp1
    hi = f" (tertinggi hari ini {_fmt(float(high))})" if high is not None else ""
    if price <= sl:
        code, label = "BELOW_STOP", "Di bawah cut loss — rencana batal"
    elif price < tp2 and hit_tp2:
        code, label = "AT_TP2", f"Sempat menyentuh TP2{hi} — punya posisi: ambil untung; belum punya: jangan dikejar"
    elif price < tp1 and hit_tp1:
        code, label = "AT_TP1", f"Sempat menyentuh TP1{hi} — punya posisi: jual separuh & naikkan cut loss ke harga beli, sisanya incar TP2; belum punya: jangan dikejar"
    elif price < el:
        code, label = "TESTING_SUPPORT", "Di antara cut loss dan zona beli — support sedang diuji"
    elif price <= eh:
        # Where the price is, not a buy call: whether to buy is the status's job (LAYAK/TUNGGU/HINDARI)
        code, label = "IN_ZONE", "Di zona beli"
    elif price >= tp2:
        code, label = "AT_TP2", "Sudah di TP2 — punya posisi: ambil untung; belum punya: jangan dikejar"
    elif price >= tp1:
        code, label = "AT_TP1", "Sudah di TP1 — punya posisi: jual separuh & naikkan cut loss ke harga beli, sisanya incar TP2; belum punya: jangan dikejar"
    else:
        code, label = "ABOVE_ZONE", "Di atas zona beli — jangan dikejar"
    atr = float(levels.get("atr14") or 0)
    dist_atr = round((float(price) - eh) / atr, 2) if atr > 0 and price > eh else 0.0
    far_above = code == "ABOVE_ZONE" and dist_atr > FAR_ABOVE_ATR
    if far_above:
        label = (f"Jauh di atas zona beli ({dist_atr:.1f}×ATR) — jangan dikejar; order limit di zona "
                 f"kemungkinan kecil terisi hari ini")
    return {
        "price": round(float(price), 2),
        "status": code,
        "label": label,
        "dist_atr": dist_atr,
        "far_above": far_above,
        # False: the plan can no longer be executed today (target already reached / stop broken)
        "buyable_today": code not in ("AT_TP1", "AT_TP2", "BELOW_STOP") and not touched_stop,
        "touched_stop": bool(touched_stop),
        "touched_tp1": bool(high is not None and high >= tp1),
        "day_high": round(float(high), 2) if high is not None else None,
        "day_low": round(float(low), 2) if low is not None else None,
    }
