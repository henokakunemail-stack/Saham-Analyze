"""Prediction snapshot evaluation & historical backfill."""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..config import DEFAULT_IDX_TICKERS, DEFAULT_US_TICKERS
from ..db import get_candles, save_prediction_snapshot
from ..collectors.market_data import fetch_stock_ohlcv, normalize_ticker
from ..indicators.technical import compute_technical_indicators
from ..indicators.money_flow import compute_money_flow
from ..indicators.trend import compute_trend_direction
from ..market_context import get_benchmark_context, BENCHMARKS
from .scoring import compute_composite_score
from .plan_sim import simulate_plan, FILL_DAYS, HORIZON
from .actionability import assess
from ..indicators.screen_metrics import compute_screen_metrics

DEFAULT_EVAL_HORIZON = HORIZON  # same window as the calibration evidence (plan_sim.HORIZON)

CLOSED_STATUSES = ("HIT_TP1", "HIT_TP2", "STOPPED_OUT", "EXPIRED")
WIN_STATUSES = ("HIT_TP1", "HIT_TP2")
# A plan the market never let you execute: not a win, not a loss (reported separately)
UNFILLED_STATUSES = ("NOT_FILLED", "CANCELLED")


def _pct(a: float, b: float) -> float:
    return round(((a - b) / b) * 100, 2) if b > 0 else 0.0


def _has_plan(item: Dict[str, Any]) -> bool:
    return all(float(item.get(k) or 0) > 0 for k in ("recommended_entry", "entry_high", "stop_loss", "target_tp1"))


def evaluate_item(item: Dict[str, Any], candles: List[Dict[str, Any]], horizon: int = DEFAULT_EVAL_HORIZON) -> Dict[str, Any]:
    """Snapshots that carry an entry zone are evaluated as executable plans (plan_sim: the
    buy limit must be reached first); older ones fall back to the price at prediction."""
    if _has_plan(item):
        out = _evaluate_plan(item, candles, horizon)
        if out is not None:
            return out
    return _evaluate_legacy(item, candles, horizon)


def _evaluate_plan(item: Dict[str, Any], candles: List[Dict[str, Any]], horizon: int) -> Optional[Dict[str, Any]]:
    p0 = float(item["price_at_prediction"])
    snap_date = str(item["snapshot_date"])[:10]
    future = [c for c in candles if str(c["date"])[:10] > snap_date]
    sim = simulate_plan(item, future, horizon=horizon)
    if sim["status"] == "INVALID":
        return None
    status = "WAITING_ENTRY" if sim["status"] == "PENDING" else sim["status"]
    curr_p = float(future[-1]["close"]) if future else p0
    closed = status in CLOSED_STATUSES
    filled = bool(sim.get("filled"))
    base = float(sim["fill_price"]) if filled else p0
    if filled:
        start = next(i for i, c in enumerate(future) if str(c["date"])[:10] == sim["fill_date"])
        end = next((i for i, c in enumerate(future) if str(c["date"])[:10] == sim.get("exit_date")), len(future) - 1)
        seen = future[start:end + 1]
    else:
        seen = future[:FILL_DAYS]
    max_p = max([float(c["high"]) for c in seen], default=base)
    min_p = min([float(c["low"]) for c in seen], default=base)
    if closed:
        ret = sim["return_pct"]
    elif status == "IN_PROGRESS":
        ret = sim.get("open_return_pct", 0.0)
    else:
        ret = 0.0
    out = dict(item)
    out.update({
        "current_price": curr_p,
        "max_price": max_p,
        "min_price": min_p,
        "exit_price": sim.get("exit_price") if closed else None,
        "exit_date": sim.get("exit_date") if closed else None,
        "return_pct": ret,
        "current_return_pct": _pct(curr_p, base),
        "max_return_pct": _pct(max_p, base),
        "status": status,
        "is_closed": closed,
        "hit_date": sim.get("exit_date") if status in ("HIT_TP1", "HIT_TP2", "STOPPED_OUT") else None,
        "days_elapsed": len(future),
        "eval_days": len(seen),
        "horizon_days": horizon,
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        # Executable-plan fields
        "plan_checked": True,
        "filled": filled,
        "fill_price": sim.get("fill_price"),
        "fill_date": sim.get("fill_date"),
        "touched_zone": bool(sim.get("touched_zone")),
        "r_multiple": sim.get("r") if closed else sim.get("open_r"),
    })
    return out


def _evaluate_legacy(item: Dict[str, Any], candles: List[Dict[str, Any]], horizon: int = DEFAULT_EVAL_HORIZON) -> Dict[str, Any]:
    """Evaluate one prediction against the candles after its snapshot date.

    Within the first `horizon` trading days SL is checked before TP on every bar, so a bar
    whose range touches both counts as STOPPED_OUT (conservative). After TP1 the trade may
    still upgrade to TP2 inside the horizon. No TP/SL within the horizon -> EXPIRED with the
    return measured at the horizon close. Fewer than `horizon` bars and nothing hit -> IN_PROGRESS.
    """
    p0 = float(item["price_at_prediction"])
    tp1 = float(item.get("target_tp1") or 0)
    tp2 = float(item.get("target_tp2") or 0)
    sl = float(item.get("stop_loss") or 0)
    snap_date = str(item["snapshot_date"])[:10]

    future = [c for c in candles if str(c["date"])[:10] > snap_date]
    window = future[:horizon]

    status = "IN_PROGRESS"
    hit_date = None
    exit_price = None
    exit_idx = None
    for i, c in enumerate(window):
        c_high = float(c["high"])
        c_low = float(c["low"])
        c_open = float(c.get("open") or 0)
        c_date = str(c["date"])[:10]
        if status == "IN_PROGRESS":
            if sl > 0 and c_low <= sl:
                status = "STOPPED_OUT"
                # a gap below the stop fills at the open, not at the stop
                exit_price = min(sl, c_open) if c_open > 0 else sl
            elif tp2 > 0 and c_high >= tp2:
                status = "HIT_TP2"
                exit_price = tp2
            elif tp1 > 0 and c_high >= tp1:
                status = "HIT_TP1"
                exit_price = tp1
            else:
                continue
            hit_date = c_date
            exit_idx = i
            if status != "HIT_TP1":
                break
        elif status == "HIT_TP1" and tp2 > 0 and c_high >= tp2:
            status = "HIT_TP2"
            exit_price = tp2
            hit_date = c_date
            exit_idx = i
            break

    if status == "IN_PROGRESS" and window and len(window) >= horizon:
        status = "EXPIRED"
        exit_idx = len(window) - 1
        exit_price = float(window[-1]["close"])
        hit_date = str(window[-1]["date"])[:10]

    seen = window[:exit_idx + 1] if exit_idx is not None else window
    curr_p = float(future[-1]["close"]) if future else p0
    max_p = max([float(c["high"]) for c in seen], default=p0)
    min_p = min([float(c["low"]) for c in seen], default=p0)

    closed = status in CLOSED_STATUSES
    if closed:
        eval_price = float(exit_price)
        exit_date = hit_date
    else:
        eval_price = curr_p
        exit_date = str(future[-1]["date"])[:10] if future else None

    out = dict(item)
    out.update({
        "current_price": curr_p,
        "max_price": max_p,
        "min_price": min_p,
        "exit_price": exit_price if closed else None,
        "exit_date": exit_date,
        # realised return for closed trades, mark-to-market for open ones
        "return_pct": _pct(eval_price, p0),
        "current_return_pct": _pct(curr_p, p0),
        "max_return_pct": _pct(max_p, p0),
        "status": status,
        "is_closed": closed,
        "hit_date": hit_date if status != "EXPIRED" else None,
        "days_elapsed": len(future),
        "eval_days": len(seen),
        "horizon_days": horizon,
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        "plan_checked": False,
    })
    return out


def _benchmark_close(market: str) -> Optional[pd.Series]:
    try:
        bdf, _ = get_benchmark_context(market)
    except Exception:
        return None
    if bdf is None or bdf.empty:
        return None
    b = bdf.copy()
    d = pd.to_datetime(b["date"])
    if d.dt.tz is not None:
        d = d.dt.tz_localize(None)
    b["date"] = d.dt.normalize()
    return b.drop_duplicates("date", keep="last").set_index("date")["close"].sort_index()


def attach_benchmark(ev: Dict[str, Any], bench_close: Optional[pd.Series]) -> None:
    """Index return over the same window as the prediction (snapshot close -> exit/latest close)."""
    if bench_close is None or bench_close.empty or not ev.get("exit_date"):
        return
    try:
        start = ev.get("fill_date") or str(ev["snapshot_date"])[:10]  # executable plans: from the fill
        b0 = float(bench_close.asof(pd.Timestamp(start)))
        b1 = float(bench_close.asof(pd.Timestamp(ev["exit_date"])))
    except Exception:
        return
    if not (np.isfinite(b0) and np.isfinite(b1)) or b0 <= 0:
        return
    ev["benchmark_return_pct"] = _pct(b1, b0)
    ev["excess_return_pct"] = round(ev["return_pct"] - ev["benchmark_return_pct"], 2)


def _avg(vals: List[float]) -> Optional[float]:
    return round(sum(vals) / len(vals), 2) if vals else None


def summarize_evaluations(evaluated: List[Dict[str, Any]], horizon: int = DEFAULT_EVAL_HORIZON, benchmark_symbol: str = "") -> Dict[str, Any]:
    """Honest summary: win rate only over closed trades, and only TP hits count as wins."""
    closed = [x for x in evaluated if x["status"] in CLOSED_STATUSES]
    open_items = [x for x in evaluated if x["status"] == "IN_PROGRESS"]
    expired = [x for x in evaluated if x["status"] == "EXPIRED"]
    wins = sum(1 for x in closed if x["status"] in WIN_STATUSES)
    excess_vals = [x["excess_return_pct"] for x in closed if x.get("excess_return_pct") is not None]
    unfilled = [x for x in evaluated if x["status"] in UNFILLED_STATUSES]
    decided = len(closed) + len(open_items) + len(unfilled)
    rs = [x["r_multiple"] for x in closed if x.get("r_multiple") is not None]

    def count(st: str) -> int:
        return sum(1 for x in evaluated if x["status"] == st)

    return {
        "total_predictions": len(evaluated),
        "horizon_days": horizon,
        "closed_count": len(closed),
        "win_count": wins,
        "hit_tp1_count": count("HIT_TP1"),
        "hit_tp2_count": count("HIT_TP2"),
        "stopped_out_count": count("STOPPED_OUT"),
        "expired_count": len(expired),
        "expired_positive_count": sum(1 for x in expired if x["return_pct"] > 0),
        "in_progress_count": len(open_items),
        "win_rate_pct": round(wins / len(closed) * 100, 1) if closed else None,
        "avg_return_pct": _avg([x["return_pct"] for x in closed]),
        "avg_open_return_pct": _avg([x["return_pct"] for x in open_items]),
        "benchmark_symbol": benchmark_symbol,
        "benchmark_avg_return_pct": _avg([x["benchmark_return_pct"] for x in closed if x.get("benchmark_return_pct") is not None]),
        "avg_excess_return_pct": _avg(excess_vals),
        "beat_benchmark_count": sum(1 for v in excess_vals if v > 0),
        "benchmark_compared_count": len(excess_vals),
        # Executable plans: how many could actually be bought in the entry zone
        "not_filled_count": count("NOT_FILLED"),
        "cancelled_count": count("CANCELLED"),
        "waiting_entry_count": count("WAITING_ENTRY"),
        "fill_rate_pct": (round(100 * (len(closed) + len(open_items)) / decided, 1)
                          if decided and any(x.get("plan_checked") for x in evaluated) else None),
        "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
    }


BUY_VERDICTS = ("STRONG_BULLISH", "MILD_BULLISH")


def select_predictions(results: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Only what the app actually signalled as a buy counts as a prediction. With the Fase 1
    status (validated in docs/hasil-kalibrasi-fase1.md) that is status LAYAK; rows without a
    status (older callers) fall back to: bullish verdict, not speculative, no market crash."""
    if any(r.get("action") for r in results):
        layak = [r for r in results if (r.get("action") or {}).get("status") == "LAYAK"]
        layak.sort(key=lambda r: (r.get("raw_score") or r.get("score") or 0), reverse=True)
        return layak[:limit]
    picks = [r for r in results
             if r.get("verdict") in BUY_VERDICTS
             and not r.get("is_speculative")
             and r.get("market_mode", "NORMAL") != "CRASH"]
    picks.sort(key=lambda r: r.get("score", 0), reverse=True)
    return picks[:limit]


def evaluate_predictions(snapshot_items: List[Dict[str, Any]], market: str, horizon: int = DEFAULT_EVAL_HORIZON) -> Dict[str, Any]:
    """Evaluate actual price movement vs predicted targets (TP1, TP2, Stop Loss) over a fixed horizon."""
    horizon = max(1, int(horizon))
    bench_close = _benchmark_close(market) if snapshot_items else None
    evaluated = []
    for item in snapshot_items:
        ticker = item["ticker"]
        candles = get_candles(ticker, limit=260)
        if not candles:
            try:
                fetch_stock_ohlcv(ticker, period="6mo", force_refresh=False)
                candles = get_candles(ticker, limit=260)
            except Exception:
                candles = []
        ev = evaluate_item(item, candles, horizon)
        attach_benchmark(ev, bench_close)
        evaluated.append(ev)

    summary = summarize_evaluations(evaluated, horizon, BENCHMARKS.get(market, ""))
    return {"summary": summary, "items": evaluated}

def backfill_prediction(market: str = "IDX", days_ago: int = 7) -> Dict[str, Any]:
    """Generate historical prediction snapshot using candle data up to N days ago."""
    target_dt = datetime.now() - timedelta(days=days_ago)
    target_date_str = target_dt.strftime("%Y-%m-%d")
    tickers = DEFAULT_IDX_TICKERS if market == "IDX" else DEFAULT_US_TICKERS
    bench_full, _ = get_benchmark_context(market)
    bench_slice = None
    if bench_full is not None:
        bench_slice = bench_full[pd.to_datetime(bench_full["date"]).dt.strftime("%Y-%m-%d") <= target_date_str]
    regime_then = compute_trend_direction(bench_slice) if bench_slice is not None and len(bench_slice) >= 30 else None

    candidates = []
    for ticker in tickers:
        try:
            norm_ticker = normalize_ticker(ticker, market)
            candles = get_candles(norm_ticker, limit=260)
            if not candles or len(candles) < 30:
                fetch_stock_ohlcv(norm_ticker, period="1y", force_refresh=False)
                candles = get_candles(norm_ticker, limit=260)

            sliced_candles = [c for c in candles if str(c["date"])[:10] <= target_date_str]
            if len(sliced_candles) < 25:
                continue

            actual_snap_date = str(sliced_candles[-1]["date"])[:10]
            df_slice = pd.DataFrame(sliced_candles)
            df_slice["date"] = pd.to_datetime(df_slice["date"])

            tech = compute_technical_indicators(df_slice, market)
            flow = compute_money_flow(df_slice)
            direction = compute_trend_direction(df_slice, bench_slice)
            comp = compute_composite_score(tech, flow, {"sentiment_score": 0.0, "catalysts": []}, None, direction, regime_then)

            item = {
                "ticker": norm_ticker,
                "market": market,
                "raw_score": comp.get("raw_score"),
                "pullback_state": comp.get("pullback_state"),
                "levels": comp.get("levels"),
                "screen": compute_screen_metrics(df_slice, tech, direction, None, market),
                "price": tech.get("price", float(df_slice["close"].iloc[-1])),
                "score": comp.get("score", 50),
                "verdict": comp.get("verdict", "NEUTRAL"),
                "market_mode": comp.get("market_mode", "NORMAL"),
                "is_speculative": comp.get("is_speculative", False),
                "badge_text": comp.get("badge_text", ""),
                "reasons": comp.get("reasons", []),
                "confluence_score": comp.get("confluence_score", 0),
                "target_tp": comp.get("target_tp", 0.0),
                "target_tp1": comp.get("target_tp1", comp.get("target_tp", 0.0)),
                "target_tp2": comp.get("target_tp2", 0.0),
                "stop_loss": comp.get("stop_loss", 0.0),
                "recommended_entry": comp.get("recommended_entry", 0.0),
                "entry_low": comp.get("entry_low", 0.0),
                "entry_high": comp.get("entry_high", 0.0),
                "risk_reward_ratio": comp.get("risk_reward_ratio", 1.0),
                "money_flow_status": flow.get("money_flow_status", "NEUTRAL"),
                "_actual_snap_date": actual_snap_date
            }
            item["action"] = assess(item)
            candidates.append(item)
        except Exception as e:
            print(f"Error backfilling {ticker}: {e}")
            continue

    if not candidates:
        return {"ok": False, "message": "Tidak cukup data candle untuk backfill"}

    candidates.sort(key=lambda x: x["score"], reverse=True)
    chosen_snap_date = candidates[0].get("_actual_snap_date", target_date_str)
    top10 = select_predictions(candidates)
    save_prediction_snapshot(top10, market=market, snapshot_date=chosen_snap_date)
    if not top10:
        return {"ok": True, "snapshot_date": chosen_snap_date, "count": 0,
                "message": "Tidak ada sinyal beli pada tanggal itu (pasar lemah/krisis) — tidak ada prediksi untuk dinilai."}
    return {"ok": True, "snapshot_date": chosen_snap_date, "count": len(top10)}


def recent_summary(market: str, days: int = 7) -> Tuple[Dict[str, Any], List[str]]:
    """All prediction snapshots of the last `days` calendar days evaluated together (weekly record)."""
    from ..db import get_prediction_dates, get_prediction_snapshot
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    dates = [d for d in get_prediction_dates(market=market) if d >= cutoff]
    items: List[Dict[str, Any]] = []
    for d in dates:
        items += evaluate_predictions(get_prediction_snapshot(d, market=market), market=market,
                                      horizon=DEFAULT_EVAL_HORIZON)["items"]
    return summarize_evaluations(items, DEFAULT_EVAL_HORIZON, BENCHMARKS.get(market, "")), dates
