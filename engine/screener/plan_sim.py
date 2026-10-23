"""Simulate a trade plan (entry zone, stop, TP1/TP2) on the bars that followed it.

One rule set shared by the walk-forward backtest, the prediction track record and the AI
validation log, so every "win rate" in the app means the same thing:

- A buy limit sits at the recommended entry for FILL_DAYS trading days. It fills when a bar
  trades down to it (at the open when the bar gaps below the limit). A plan whose price
  never comes back to the limit is NOT_FILLED: it could not have been executed.
- A bar that opens at or below the stop before the order fills voids the plan (CANCELLED),
  as the opening guide in the app says ("di bawah cut loss: rencana batal").
- After the fill the trade gets HORIZON trading days. The stop is checked before the target
  on every bar (a bar touching both counts as the stop); a gap below the stop exits at the
  open. TP is not counted on the fill bar itself (its high may have come before the fill).
  Nothing hit: EXPIRED at the horizon close.
- After TP1 (AFTER_TP1): "half_breakeven" (default, what the app advises) sells half at TP1 and
  keeps half with the stop moved to the fill price, aiming at TP2; "exit" sells everything at TP1. A sell limit fills at the open when the bar gaps above it.
- Results are gross (no fees). R = (exit - fill) / (fill - stop).
"""
from typing import Any, Dict, List, Optional

FILL_DAYS = 5
HORIZON = 10
AFTER_TP1 = "half_breakeven"  # chosen in the 23 Oct 2026 backtest (docs/hasil-akhir-fase1-5.md)

FILLED_CLOSED = ("STOPPED_OUT", "HIT_TP1", "HIT_TP2", "EXPIRED")
WINS = ("HIT_TP1", "HIT_TP2")


def _f(bar: Any, key: str) -> float:
    return float(bar[key])


def simulate_plan(plan: Dict[str, Any], bars: List[Dict[str, Any]], fill_days: int = FILL_DAYS,
                  horizon: int = HORIZON, after_tp1: str = AFTER_TP1) -> Dict[str, Any]:
    """`plan` needs recommended_entry, stop_loss, target_tp1 (target_tp2 optional);
    `bars` are the daily bars after the plan's date, oldest first (dicts or rows with
    open/high/low/close and date)."""
    limit = float(plan.get("recommended_entry") or 0)
    stop = float(plan.get("stop_loss") or 0)
    tp1 = float(plan.get("target_tp1") or 0)
    tp2 = float(plan.get("target_tp2") or 0)
    if limit <= 0 or stop <= 0 or tp1 <= 0 or stop >= limit:
        return {"status": "INVALID", "filled": False}
    entry_high = float(plan.get("entry_high") or limit)

    # ── Waiting for the fill ────────────────────────────────────────────────
    fill_idx, fill_price, touched_zone = None, None, False
    for i, bar in enumerate(bars[:fill_days]):
        o, lo = _f(bar, "open"), _f(bar, "low")
        if lo <= entry_high:
            touched_zone = True
        if o <= stop:
            return {"status": "CANCELLED", "filled": False, "touched_zone": touched_zone,
                    "cancel_date": str(bar["date"])[:10]}
        if lo <= limit:
            fill_idx, fill_price = i, min(o, limit)
            break
    if fill_idx is None:
        pending = len(bars) < fill_days
        return {"status": "PENDING" if pending else "NOT_FILLED", "filled": False, "touched_zone": touched_zone}

    # ── In the trade ────────────────────────────────────────────────────────
    risk = fill_price - stop
    window = bars[fill_idx:fill_idx + horizon]
    split = after_tp1 == "half_breakeven" and tp2 > tp1
    status, exit_price, exit_idx = "IN_PROGRESS", None, None
    tp1_px = None  # price the first half sold at (half_breakeven only)
    for j, bar in enumerate(window):
        o, h, lo = _f(bar, "open"), _f(bar, "high"), _f(bar, "low")
        if tp1_px is None:
            if lo <= stop:
                status, exit_idx = "STOPPED_OUT", j
                exit_price = min(stop, o) if j > 0 else stop  # gap below the stop exits at the open
                break
            if j == 0 or h < tp1:
                continue  # the fill bar: its high may predate the fill
            px1 = max(tp1, o)
            if not split:
                status, exit_price, exit_idx = "HIT_TP1", px1, j
                break
            tp1_px = px1
            if h >= tp2:  # both targets on the same bar
                status, exit_price, exit_idx = "HIT_TP2", (px1 + max(tp2, o)) / 2, j
                break
        elif lo <= fill_price:  # second half stopped at breakeven
            status, exit_price, exit_idx = "HIT_TP1", (tp1_px + min(fill_price, o)) / 2, j
            break
        elif h >= tp2:
            status, exit_price, exit_idx = "HIT_TP2", (tp1_px + max(tp2, o)) / 2, j
            break
    if status == "IN_PROGRESS" and len(window) >= horizon:
        exit_idx, last = len(window) - 1, _f(window[-1], "close")
        if tp1_px is None:
            status, exit_price = "EXPIRED", last
        else:
            status, exit_price = "HIT_TP1", (tp1_px + last) / 2

    out: Dict[str, Any] = {
        "status": status,
        "filled": True,
        "touched_zone": True,
        "fill_date": str(bars[fill_idx]["date"])[:10],
        "fill_price": round(fill_price, 4),
        "days_to_fill": fill_idx + 1,
    }
    if status == "IN_PROGRESS":
        last = _f(window[-1], "close") if window else fill_price
        if tp1_px is not None:
            last = (tp1_px + last) / 2
        out["open_r"] = round((last - fill_price) / risk, 3)
        out["open_return_pct"] = round((last / fill_price - 1) * 100, 2)
        return out
    out.update({
        "exit_date": str(window[exit_idx]["date"])[:10],
        "exit_price": round(float(exit_price), 4),
        "bars_held": exit_idx + 1,
        "r": round((float(exit_price) - fill_price) / risk, 3),
        "return_pct": round((float(exit_price) / fill_price - 1) * 100, 2),
    })
    return out


def summarize_sims(sims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fill rate over decided plans, win rate / average R over filled-and-closed trades."""
    decided = [s for s in sims if s.get("status") not in ("PENDING", "INVALID", "IN_PROGRESS")]
    filled = [s for s in decided if s.get("filled")]
    closed = [s for s in filled if s.get("status") in FILLED_CLOSED]
    rs = [s["r"] for s in closed if s.get("r") is not None]
    wins = [s for s in closed if s["status"] in WINS]
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)

    def count(st: str) -> int:
        return sum(1 for s in decided if s.get("status") == st)

    return {
        "plans": len(sims),
        "decided": len(decided),
        "filled": len(filled),
        "fill_rate_pct": round(100 * len(filled) / len(decided), 1) if decided else None,
        "not_filled": count("NOT_FILLED"),
        "cancelled": count("CANCELLED"),
        "closed": len(closed),
        "hit_tp1": count("HIT_TP1"),
        "hit_tp2": count("HIT_TP2"),
        "stopped_out": count("STOPPED_OUT"),
        "expired": count("EXPIRED"),
        "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
        "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
        "profit_factor": round(gains / losses, 2) if losses > 0 else None,
        "avg_return_pct": round(sum(s["return_pct"] for s in closed) / len(closed), 2) if closed else None,
        "avg_bars_held": round(sum(s["bars_held"] for s in closed) / len(closed), 1) if closed else None,
    }
