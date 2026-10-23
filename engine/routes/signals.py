"""Signal-trust API: backtest of the scoring model and prediction history."""
import json
import math
import threading
import time
from typing import Optional, Dict, Any

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..config import DEFAULT_IDX_TICKERS, DEFAULT_US_TICKERS
from ..db import get_candles, get_prediction_dates, get_prediction_snapshot, get_setting, set_setting
from ..collectors.market_data import fetch_stock_ohlcv, normalize_ticker, prefetch_daily
from ..market_context import BENCHMARKS
from ..screener.backtest import walk_forward, summarize as summarize_backtest, summarize_groups, summarize_plans
from ..screener.predictions import evaluate_predictions, backfill_prediction, summarize_evaluations, DEFAULT_EVAL_HORIZON

router = APIRouter()

class PredictionBackfillRequest(BaseModel):
    market: Optional[str] = Field("IDX", pattern="^(IDX|US)$")
    days_ago: Optional[int] = Field(7, ge=1, le=365)

BACKTEST_TTL = 6 * 3600
# Bumped when the stored result gains new sections (2 = trade-plan simulation); older results
# are recomputed once instead of being served until the TTL runs out
BACKTEST_VERSION = 4  # 4: plan_sim sells half at TP1, rest to TP2 with a breakeven stop
BACKTEST_ERROR_RETRY = 5 * 60
IC_MIN = 0.03     # |IC| below this is treated as no usable edge
T_STAT_MIN = 2.0  # roughly 95% confidence that the mean IC is not zero

_backtest_cache: Dict[str, Any] = {}    # key -> (computed_ts, result)
_backtest_running: Dict[str, float] = {}  # key -> started_ts
_backtest_errors: Dict[str, Any] = {}   # key -> (ts, message)
_backtest_lock = threading.Lock()


def _setting_key(key: str) -> str:
    return f"backtest_result:{key}"


def backtest_verdict(ic: Optional[float], t_stat: Optional[float], horizon: int) -> Dict[str, str]:
    """Plain-language reading of the IC. Anything not clearly significant is reported as no edge."""
    if ic is None:
        return {"code": "NO_DATA", "text": "Data belum cukup untuk menilai keandalan skor."}
    weak_t = t_stat is None or abs(t_stat) < T_STAT_MIN
    if abs(ic) < IC_MIN or weak_t:
        return {"code": "NO_EDGE", "text": f"Skor saat ini belum terbukti memprediksi arah {horizon} hari."}
    if ic > 0:
        return {"code": "POSITIVE", "text": f"Skor lebih tinggi secara historis diikuti return {horizon} hari yang sedikit lebih baik. Tetap bukan jaminan."}
    return {"code": "NEGATIVE", "text": f"Skor lebih tinggi secara historis justru diikuti return {horizon} hari yang lebih buruk. Jangan gunakan skor sebagai sinyal beli."}


def _clean(obj: Any) -> Any:
    """Replace NaN/inf with None so the result is valid JSON."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def compute_backtest(market: str, horizon: int) -> Dict[str, Any]:
    tickers = DEFAULT_IDX_TICKERS if market == "IDX" else DEFAULT_US_TICKERS
    norms = [normalize_ticker(t, market) for t in tickers]
    # ~3y per ticker in a few batched requests (one request per ticker would hit Yahoo's limits)
    try:
        prefetch_daily(norms, period="3y", min_bars=400)
    except Exception as e:
        print(f"[Backtest] batch prefetch failed: {e}")
    data = {}
    for norm in norms:
        candles = get_candles(norm, limit=1000)
        # The live cache holds ~1y; a meaningful track record needs ~3y of history
        if not candles or len(candles) < 400:
            try:
                fetch_stock_ohlcv(norm, period="3y", force_refresh=True)
            except Exception:
                pass
            candles = get_candles(norm, limit=1000)
        if candles and len(candles) >= 150:
            data[norm] = pd.DataFrame(candles)
    if not data:
        return {"ok": False, "market": market, "horizon_days": horizon, "message": "Data historis belum cukup untuk backtest"}
    try:
        bench_df = fetch_stock_ohlcv(BENCHMARKS.get(market, "^JKSE"), period="3y", force_refresh=True)
    except Exception:
        bench_df = pd.DataFrame()

    rows = walk_forward(data, bench_df if not bench_df.empty else None, horizon=horizon, step=3, market=market)
    score = summarize_backtest(rows, "score")
    return _clean({
        "ok": True,
        "market": market,
        "horizon_days": horizon,
        "tickers": len(data),
        "benchmark_symbol": BENCHMARKS.get(market, ""),
        "score": score,
        "direction_ic": summarize_backtest(rows, "direction_score").get("ic"),
        "verdict": backtest_verdict(score.get("ic"), score.get("ic_t_stat"), horizon),
        "period_start": str(rows["date"].min())[:10] if not rows.empty else None,
        "period_end": str(rows["date"].max())[:10] if not rows.empty else None,
        "by_pullback_state": summarize_groups(rows, "pullback_state"),
        "by_market_mode": summarize_groups(rows, "market_mode"),
        # Trade plans simulated on the following bars (entry zone reached? stop or TP first?)
        "plans": summarize_plans(rows),
    })


def _run_backtest_job(key: str, market: str, horizon: int) -> None:
    try:
        result = compute_backtest(market, horizon)
        now = time.time()
        result["computed_at"] = now
        result["version"] = BACKTEST_VERSION
        with _backtest_lock:
            _backtest_cache[key] = (now, result)
            _backtest_errors.pop(key, None)
        try:
            set_setting(_setting_key(key), json.dumps(result))
        except Exception as e:
            print(f"Backtest persist failed for {key}: {e}")
    except Exception as e:
        print(f"Backtest failed for {key}: {e}")
        with _backtest_lock:
            _backtest_errors[key] = (time.time(), str(e))
    finally:
        with _backtest_lock:
            _backtest_running.pop(key, None)


def _load_persisted(key: str) -> Optional[Dict[str, Any]]:
    try:
        raw = get_setting(_setting_key(key), "")
        if not raw:
            return None
        res = json.loads(raw)
        return res if isinstance(res, dict) and res.get("computed_at") else None
    except Exception:
        return None


@router.get("/api/backtest")
def run_backtest_endpoint(market: str = Query("IDX", pattern="^(IDX|US)$"), horizon: int = Query(10, ge=3, le=40), refresh: bool = False):
    """Walk-forward test of the scoring model on cached candles (no look-ahead).

    Non-blocking: the computation (minutes when uncached) runs in a background thread.
    Returns {status:"running"} (with the previous result, if any) until it finishes; poll again.
    Results are cached 6h in memory and the last one is persisted in app_settings.
    """
    market = market if market in BENCHMARKS else "IDX"
    key = f"{market}:{horizon}"
    now = time.time()
    with _backtest_lock:
        cached = _backtest_cache.get(key)
        running_since = _backtest_running.get(key)
        error = _backtest_errors.get(key)
    if cached is None:
        persisted = _load_persisted(key)
        if persisted:
            cached = (float(persisted["computed_at"]), persisted)
            with _backtest_lock:
                _backtest_cache.setdefault(key, cached)

    fresh = (cached is not None and now - cached[0] < BACKTEST_TTL
             and cached[1].get("version") == BACKTEST_VERSION)
    if fresh and not refresh and running_since is None:
        return {**cached[1], "status": "ready", "age_sec": int(now - cached[0])}

    previous = cached[1] if cached else None
    if running_since is None and error and not refresh and now - error[0] < BACKTEST_ERROR_RETRY:
        return {"status": "error", "market": market, "horizon_days": horizon, "message": error[1], "previous": previous}

    if running_since is None:
        with _backtest_lock:
            if key not in _backtest_running:
                _backtest_running[key] = now
                running_since = now
                threading.Thread(target=_run_backtest_job, args=(key, market, horizon), daemon=True,
                                 name=f"backtest-{key}").start()
            else:
                running_since = _backtest_running[key]
    return {
        "status": "running",
        "market": market,
        "horizon_days": horizon,
        "started_at": running_since,
        "elapsed_sec": int(now - running_since),
        "previous": previous,
    }

RELIABILITY_MAX_AGE = 7 * 24 * 3600


@router.get("/api/backtest/reliability")
def get_reliability_endpoint(market: str = Query("IDX", pattern="^(IDX|US)$"), horizon: int = Query(10, ge=3, le=40)):
    """Lightweight track record for the stock-detail view: per pullback state, market mode
    and score bucket. Never computes inline: serves the last stored backtest and, when it is
    missing or older than 7 days, starts a background refresh (same job as /api/backtest)."""
    market = market if market in BENCHMARKS else "IDX"
    key = f"{market}:{horizon}"
    with _backtest_lock:
        cached = _backtest_cache.get(key)
    result = cached[1] if cached else _load_persisted(key)
    age = time.time() - float(result["computed_at"]) if result and result.get("computed_at") else None
    status = "ready"
    if result is None or "by_pullback_state" not in result or age is None or age > RELIABILITY_MAX_AGE:
        status = run_backtest_endpoint(market=market, horizon=horizon, refresh=False).get("status", "running")
        if result is None or "by_pullback_state" not in result:
            return {"status": status, "market": market, "horizon_days": horizon, "available": False}
    return {
        "status": status,
        "available": True,
        "market": market,
        "horizon_days": horizon,
        "age_sec": int(age) if age is not None else None,
        "period_start": result.get("period_start"),
        "period_end": result.get("period_end"),
        "tickers": result.get("tickers"),
        "benchmark_symbol": result.get("benchmark_symbol"),
        "baseline_hit_rate_pct": (result.get("score") or {}).get("baseline_hit_rate_pct"),
        "by_pullback_state": result.get("by_pullback_state", {}),
        "by_market_mode": result.get("by_market_mode", {}),
        "by_score_bucket": (result.get("score") or {}).get("buckets", []),
        "verdict": result.get("verdict"),
    }


@router.get("/api/predictions/dates")
def get_prediction_dates_endpoint(market: str = Query("IDX", pattern="^(IDX|US)$")):
    """Get list of snapshot dates available for market."""
    dates = get_prediction_dates(market=market)
    return {"market": market, "dates": dates}

@router.get("/api/predictions/history")
def get_prediction_history_endpoint(
    market: str = Query("IDX", pattern="^(IDX|US)$"),
    snapshot_date: Optional[str] = None,
    horizon: int = Query(DEFAULT_EVAL_HORIZON, ge=1, le=120),
):
    """Evaluated prediction history for a snapshot date.

    Each prediction gets `horizon` trading days to hit TP/SL, otherwise it is EXPIRED.
    Win rate counts only TP hits over closed predictions (IN_PROGRESS is excluded).
    """
    dates = get_prediction_dates(market=market)
    if not dates:
        return {
            "snapshot_date": "",
            "market": market,
            "horizon_days": horizon,
            "summary": summarize_evaluations([], horizon, BENCHMARKS.get(market, "")),
            "items": [],
            "available_dates": []
        }

    selected_date = snapshot_date if (snapshot_date and snapshot_date in dates) else dates[0]
    items = get_prediction_snapshot(selected_date, market=market)
    evaluated = evaluate_predictions(items, market=market, horizon=horizon)
    return {
        "snapshot_date": selected_date,
        "market": market,
        "horizon_days": horizon,
        "summary": evaluated["summary"],
        "items": evaluated["items"],
        "available_dates": dates
    }

@router.post("/api/predictions/backfill")
def trigger_backfill_endpoint(req: PredictionBackfillRequest):
    """Trigger backfill snapshot for historical tracking."""
    return backfill_prediction(market=req.market or "IDX", days_ago=req.days_ago or 7)
