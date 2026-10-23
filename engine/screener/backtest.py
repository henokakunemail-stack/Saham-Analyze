"""Walk-forward backtest of the scoring model on historical candles.

At every evaluation date only data up to that date is visible (no look-ahead).
Measures whether higher scores really precede higher forward returns:
  - IC: average cross-sectional Spearman correlation (score vs forward return)
  - per-score-bucket average forward return, excess return vs index and hit rate
  - the trade plan of every evaluation date simulated on the bars that followed it
    (plan_sim: was the entry zone reached, then stop or target first, in R)
"""
from typing import Dict, Any, List, Optional, Callable
import numpy as np
import pandas as pd

from ..indicators.technical import compute_technical_indicators
from ..indicators.money_flow import compute_money_flow
from ..indicators.trend import compute_trend_direction
from ..indicators.screen_metrics import ILLIQUID_IDR, ILLIQUID_USD
from .scoring import compute_composite_score
from .actionability import assess
from .plan_sim import simulate_plan, summarize_sims, FILL_DAYS

LOOKBACK_BARS = 260  # same window the live screener sees

BUCKETS = [(0, 35, "0-34"), (35, 45, "35-44"), (45, 55, "45-54"), (55, 65, "55-64"), (65, 75, "65-74"), (75, 101, "75-100")]
RR_BUCKETS = [(0, 0.5, "< 0,5"), (0.5, 1.0, "0,5-1"), (1.0, 1.5, "1-1,5"), (1.5, 99, ">= 1,5")]
ATR_BUCKETS = [(0, 3, "< 3%"), (3, 5, "3-5%"), (5, 8, "5-8%"), (8, 999, ">= 8%")]
PLAN_KEYS = ("recommended_entry", "entry_low", "entry_high", "stop_loss", "target_tp1", "target_tp2")


_regime_cache: Dict[str, Any] = {}


def default_score_fn(df: pd.DataFrame, bench: Optional[pd.DataFrame], market: str = "IDX") -> Dict[str, Any]:
    tech = compute_technical_indicators(df, market)
    flow = compute_money_flow(df)
    direction = compute_trend_direction(df, bench)
    regime = None
    if bench is not None and len(bench) >= 30:
        # The index regime is identical for every ticker on a given date: compute it once
        key = f"{len(bench)}:{bench['date'].iloc[-1]}:{float(bench['close'].iloc[-1]):.4f}"
        if key not in _regime_cache:
            if len(_regime_cache) > 5000:
                _regime_cache.clear()
            _regime_cache[key] = compute_trend_direction(bench)
        regime = _regime_cache[key]
    comp = compute_composite_score(tech, flow, {"sentiment_score": 0.0}, None, direction, regime)
    lv = tech.get("levels") or {}
    price = float(tech.get("price") or 0)
    tail = df.iloc[-20:]
    avg_value = float((tail["close"].astype(float) * tail["volume"].astype(float)).mean()) if len(tail) else 0.0
    atr_pct = round(100 * float(lv.get("atr14") or 0) / price, 2) if price else None
    pullback_state = (direction.get("pullback") or {}).get("state", "INSUFFICIENT_DATA")
    # Same row shape the live scan hands to actionability (no fundamentals/news/abnormal days here)
    action = assess({
        "market": market, "verdict": comp.get("verdict"), "is_speculative": False,
        "market_mode": comp.get("market_mode", "NORMAL"), "score": comp["score"],
        "raw_score": comp.get("raw_score"), "pillar_values": comp.get("pillar_values"),
        "pullback_state": pullback_state, "levels": lv,
        "screen": {"avg_value_20d": avg_value, "atr_pct": atr_pct, "rs_60d": direction.get("rs_60d_pct"),
                   "illiquid": avg_value < (ILLIQUID_IDR if market == "IDX" else ILLIQUID_USD)},
    })
    return {
        "score": comp["score"],
        "raw_score": comp.get("raw_score"),
        "pillar_values": comp.get("pillar_values"),
        "direction_score": direction["direction_score"],
        "pullback_state": pullback_state,
        "market_mode": comp.get("market_mode", "NORMAL"),
        "verdict": comp.get("verdict"),
        "rr": lv.get("risk_reward_ratio"),
        "risk_pct": lv.get("risk_pct"),
        "atr_pct": atr_pct,
        "avg_value_20d": round(avg_value, 0),
        "rs_60d": direction.get("rs_60d_pct"),
        "flags": ",".join(lv.get("flags") or []),
        "action_status": action["status"],
        "plan": {k: lv.get(k) for k in PLAN_KEYS} if lv else None,
    }


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 5 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def walk_forward(
    data: Dict[str, pd.DataFrame],
    benchmark: Optional[pd.DataFrame] = None,
    horizon: int = 10,
    step: int = 5,
    warmup: int = 120,
    score_fn: Optional[Callable[[pd.DataFrame, Optional[pd.DataFrame]], Dict[str, Any]]] = None,
    market: str = "IDX",
) -> pd.DataFrame:
    """Return one row per (ticker, date) with model outputs and realized forward returns."""
    if score_fn is None:
        score_fn = lambda d, b: default_score_fn(d, b, market)  # noqa: E731
    bench = None
    if benchmark is not None and not benchmark.empty:
        bench = benchmark.copy()
        bench["date"] = pd.to_datetime(bench["date"]).dt.normalize()
        bench = bench.drop_duplicates("date", keep="last").reset_index(drop=True)
    bench_close = bench.set_index("date")["close"] if bench is not None else None

    rows = []
    for ticker, df in data.items():
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df[df["volume"] > 0].drop_duplicates("date", keep="last").reset_index(drop=True)
        n = len(df)
        for i in range(warmup, n - horizon, step):
            window = df.iloc[max(0, i - LOOKBACK_BARS + 1):i + 1]
            date = window["date"].iloc[-1]
            b_win = None
            if bench is not None:
                b_win = bench[bench["date"] <= date].iloc[-LOOKBACK_BARS:]
            try:
                out = score_fn(window, b_win)
            except Exception:
                continue
            p0 = float(df["close"].iloc[i])
            p1 = float(df["close"].iloc[i + horizon])
            fwd = p1 / p0 - 1
            excess = np.nan
            if bench_close is not None:
                d1 = df["date"].iloc[i + horizon]
                b0 = bench_close.asof(date)
                b1 = bench_close.asof(d1)
                if b0 and b1 and np.isfinite(b0) and np.isfinite(b1):
                    excess = fwd - (b1 / b0 - 1)
            plan = out.pop("plan", None)
            sim = {}
            if plan:
                future = df.iloc[i + 1:i + 1 + FILL_DAYS + horizon][["date", "open", "high", "low", "close"]]
                sim = simulate_plan(plan, future.to_dict("records"), horizon=horizon)
            rows.append({"ticker": ticker, "date": date, **out, "fwd_ret": fwd, "excess_ret": excess,
                         "plan_status": sim.get("status"), "filled": bool(sim.get("filled")),
                         "r": sim.get("r"), "plan_return_pct": sim.get("return_pct"),
                         "bars_held": sim.get("bars_held")})
    return pd.DataFrame(rows)


def summarize_groups(results: pd.DataFrame, group_col: str, min_count: int = 20) -> Dict[str, Any]:
    """Track record per category (e.g. pullback state): how often and how much price rose afterwards."""
    if results.empty or group_col not in results.columns:
        return {}
    out = {}
    for key, g in results.groupby(group_col):
        if len(g) < min_count:
            continue
        exc = g["excess_ret"].dropna()
        out[str(key)] = {
            "count": int(len(g)),
            "hit_rate_pct": round(float((g["fwd_ret"] > 0).mean()) * 100, 1),
            "avg_fwd_ret_pct": round(float(g["fwd_ret"].mean()) * 100, 2),
            "avg_excess_ret_pct": round(float(exc.mean()) * 100, 2) if len(exc) else None,
            "beat_index_pct": round(float((exc > 0).mean()) * 100, 1) if len(exc) else None,
        }
    return out


def _sims(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = ["plan_status", "filled", "r", "plan_return_pct", "bars_held"]
    out = []
    for st, filled, r, ret, held in frame[cols].itertuples(index=False):
        if st is None or (isinstance(st, float) and np.isnan(st)):
            continue
        out.append({"status": st, "filled": bool(filled), "r": None if pd.isna(r) else float(r),
                    "return_pct": None if pd.isna(ret) else float(ret),
                    "bars_held": None if pd.isna(held) else float(held)})
    return out


def _bucketed(results: pd.DataFrame, col: str, buckets) -> pd.Series:
    vals = pd.to_numeric(results[col], errors="coerce")
    labels = pd.Series([None] * len(results), index=results.index, dtype=object)
    for lo, hi, label in buckets:
        labels[(vals >= lo) & (vals < hi)] = label
    return labels


def summarize_plans(results: pd.DataFrame, min_count: int = 30) -> Dict[str, Any]:
    """Plan simulation results overall, per group, and for the earlier vs the later part of the
    period (the later third is kept as the out-of-sample check for new rules)."""
    if results.empty or "plan_status" not in results.columns:
        return {}
    res = results.copy()
    res["score_bucket"] = _bucketed(res, "score", BUCKETS)
    res["rr_bucket"] = _bucketed(res, "rr", RR_BUCKETS)
    res["atr_bucket"] = _bucketed(res, "atr_pct", ATR_BUCKETS)
    res["flag_tight_room"] = res["flags"].fillna("").str.contains("tight_room").map({True: "ya", False: "tidak"})
    res["flag_wide_stop"] = res["flags"].fillna("").str.contains("wide_stop").map({True: "ya", False: "tidak"})

    def groups(col: str) -> Dict[str, Any]:
        out = {}
        for key, g in res.groupby(col, dropna=True):
            if len(g) >= min_count:
                out[str(key)] = summarize_sims(_sims(g))
        return out

    dates = sorted(res["date"].unique())
    split = dates[int(len(dates) * 2 / 3)] if len(dates) >= 3 else None
    periods = {}
    if split is not None:
        periods = {
            "in_sample": {"until": str(split)[:10], **summarize_sims(_sims(res[res["date"] < split]))},
            "out_of_sample": {"from": str(split)[:10], **summarize_sims(_sims(res[res["date"] >= split]))},
        }
    return {
        "rules": {"fill_days": FILL_DAYS, "fees": "tidak dihitung (harga kotor)"},
        "overall": summarize_sims(_sims(res)),
        "periods": periods,
        "by_score_bucket": groups("score_bucket"),
        "by_verdict": groups("verdict"),
        "by_pullback_state": groups("pullback_state"),
        "by_market_mode": groups("market_mode"),
        "by_rr_bucket": groups("rr_bucket"),
        "by_atr_bucket": groups("atr_bucket"),
        "by_tight_room": groups("flag_tight_room"),
        "by_wide_stop": groups("flag_wide_stop"),
        "by_action_status": groups("action_status") if "action_status" in res.columns else {},
    }


def summarize(results: pd.DataFrame, score_col: str = "score") -> Dict[str, Any]:
    """Aggregate walk-forward rows into IC and per-bucket statistics."""
    if results.empty:
        return {"samples": 0, "ic": None, "buckets": []}

    ics = []
    for _, g in results.groupby("date"):
        ic = _spearman(g[score_col].to_numpy(dtype=float), g["fwd_ret"].to_numpy(dtype=float))
        if np.isfinite(ic):
            ics.append(ic)
    ic_mean = float(np.mean(ics)) if ics else float("nan")
    ic_t = float(ic_mean / (np.std(ics) / np.sqrt(len(ics)))) if len(ics) > 2 and np.std(ics) > 0 else float("nan")

    buckets = []
    for lo, hi, label in BUCKETS:
        g = results[(results[score_col] >= lo) & (results[score_col] < hi)]
        if g.empty:
            continue
        buckets.append({
            "bucket": label,
            "count": int(len(g)),
            "avg_fwd_ret_pct": round(float(g["fwd_ret"].mean()) * 100, 2),
            "avg_excess_ret_pct": round(float(g["excess_ret"].mean()) * 100, 2) if g["excess_ret"].notna().any() else None,
            "hit_rate_pct": round(float((g["fwd_ret"] > 0).mean()) * 100, 1),
        })

    return {
        "samples": int(len(results)),
        "dates": int(results["date"].nunique()),
        "ic": round(ic_mean, 4) if np.isfinite(ic_mean) else None,
        "ic_t_stat": round(ic_t, 2) if np.isfinite(ic_t) else None,
        "baseline_hit_rate_pct": round(float((results["fwd_ret"] > 0).mean()) * 100, 1),
        "baseline_avg_fwd_ret_pct": round(float(results["fwd_ret"].mean()) * 100, 2),
        "buckets": buckets,
    }
