"""Signal Trust: prediction evaluation (EXPIRED / honest win rate), broker NO_DATA, backtest endpoint."""
import os
import sys
import tempfile
import time
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="saham_signals_")
os.environ.setdefault("SAHAM_DB_PATH", os.path.join(_tmp_dir, "test.db"))
os.environ["SAHAM_DISABLE_AUTOSCAN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from engine.db import init_db, set_setting, save_broker_summary
from engine.screener import predictions as pred
from engine.screener import broker_summary as bs
from engine.routes import signals as sig

init_db()


def _candles(start: str, bars):
    """bars: list of (open, high, low, close); dates are consecutive business days after start."""
    dates = pd.bdate_range(start=pd.Timestamp(start) + pd.Timedelta(days=1), periods=len(bars))
    return [{"date": d.strftime("%Y-%m-%d"), "open": o, "high": h, "low": l, "close": c, "volume": 1000}
            for d, (o, h, l, c) in zip(dates, bars)]


def _item(**kw):
    base = {"ticker": "TEST.JK", "snapshot_date": "2026-01-02", "price_at_prediction": 100.0,
            "target_tp1": 110.0, "target_tp2": 120.0, "stop_loss": 90.0}
    base.update(kw)
    return base


FLAT = (100, 101, 99, 100)


def test_expired_when_nothing_hit_within_horizon():
    bars = [FLAT] * 4 + [(100, 104, 99, 103)] + [FLAT] * 5
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", bars), horizon=5)
    assert ev["status"] == "EXPIRED"
    assert ev["return_pct"] == 3.0          # measured at the horizon close
    assert ev["eval_days"] == 5
    assert ev["is_closed"] is True


def test_in_progress_when_horizon_not_reached():
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", [FLAT, (100, 103, 99, 102)]), horizon=5)
    assert ev["status"] == "IN_PROGRESS"
    assert ev["return_pct"] == 2.0
    assert ev["is_closed"] is False


def test_tp_after_horizon_does_not_count():
    bars = [FLAT] * 5 + [(100, 125, 100, 122)]
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", bars), horizon=5)
    assert ev["status"] == "EXPIRED"


def test_same_day_sl_and_tp_counts_as_stop():
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", [(100, 125, 85, 100)]), horizon=5)
    assert ev["status"] == "STOPPED_OUT"
    assert ev["return_pct"] == -10.0


def test_gap_below_stop_fills_at_open():
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", [(80, 82, 78, 81)]), horizon=5)
    assert ev["status"] == "STOPPED_OUT"
    assert ev["return_pct"] == -20.0


def test_tp1_then_tp2_within_horizon():
    bars = [(100, 111, 99, 110), (110, 121, 108, 119)]
    ev = pred.evaluate_item(_item(), _candles("2026-01-02", bars), horizon=5)
    assert ev["status"] == "HIT_TP2"
    assert ev["return_pct"] == 20.0


def test_summary_win_rate_only_closed_and_only_tp():
    items = [
        {"status": "HIT_TP1", "return_pct": 10.0, "benchmark_return_pct": 2.0, "excess_return_pct": 8.0},
        {"status": "STOPPED_OUT", "return_pct": -10.0, "benchmark_return_pct": 1.0, "excess_return_pct": -11.0},
        {"status": "EXPIRED", "return_pct": 3.0, "benchmark_return_pct": 0.0, "excess_return_pct": 3.0},
        {"status": "EXPIRED", "return_pct": -1.0, "benchmark_return_pct": 1.0, "excess_return_pct": -2.0},
        {"status": "IN_PROGRESS", "return_pct": 15.0, "benchmark_return_pct": None, "excess_return_pct": None},
    ]
    s = pred.summarize_evaluations(items, horizon=20)
    assert s["closed_count"] == 4
    assert s["win_count"] == 1                     # EXPIRED +3% is NOT a win
    assert s["win_rate_pct"] == 25.0
    assert s["expired_count"] == 2
    assert s["expired_positive_count"] == 1
    assert s["in_progress_count"] == 1
    assert s["avg_return_pct"] == 0.5              # (10 - 10 + 3 - 1) / 4, IN_PROGRESS excluded
    assert s["benchmark_avg_return_pct"] == 1.0
    assert s["avg_excess_return_pct"] == -0.5
    assert s["beat_benchmark_count"] == 2


def test_summary_empty_has_no_win_rate():
    s = pred.summarize_evaluations([], horizon=20)
    assert s["win_rate_pct"] is None and s["closed_count"] == 0


def test_evaluate_predictions_with_benchmark(monkeypatch):
    bars = [FLAT] * 4 + [(100, 104, 99, 105)]
    candles = _candles("2026-01-02", bars)
    bench = pd.DataFrame(_candles("2025-12-20", [(1000, 1000, 1000, 1000)] * 30))
    bench.loc[bench["date"] > candles[-1]["date"], "close"] = 1100
    bench.loc[bench["date"] == candles[-1]["date"], "close"] = 1020
    monkeypatch.setattr(pred, "get_candles", lambda t, limit=260: candles)
    monkeypatch.setattr(pred, "get_benchmark_context", lambda m: (bench, None))
    out = pred.evaluate_predictions([_item()], "IDX", horizon=5)
    ev = out["items"][0]
    assert ev["status"] == "EXPIRED"
    assert ev["benchmark_return_pct"] == 2.0
    assert ev["excess_return_pct"] == 3.0
    assert out["summary"]["benchmark_symbol"] == "^JKSE"


def test_simulated_broker_returns_neutral_status():
    set_setting("sectors_api_key", "")
    res = bs.fetch_and_evaluate_broker_summary("SIMU.JK", "IDX", current_price=10000, cmf20=0.3,
                                               vol_ratio=2.0, change_pct=3.0, vsa_signal="ABSORPTION")
    assert res["bandar_status"] == "NO_DATA"
    assert res["top_buyers"] == [] and res["top_sellers"] == []
    assert res["data_available"] is False
    assert "Pengaturan" in res["no_data_message"]


def test_cached_proxy_rows_are_not_served():
    proxy = bs.generate_proxy_broker_summary("TLKM.JK", 3000, 0.3, 2.0, 3.0, "ABSORPTION")
    ev = bs.evaluate_bandarmologi(proxy["top_buyers"], proxy["top_sellers"], 3000)
    save_broker_summary({"ticker": "TLKM.JK", "trade_date": proxy["trade_date"], "source": "PROXY",
                         "top_buyers": proxy["top_buyers"], "top_sellers": proxy["top_sellers"], **ev})
    res = bs.fetch_and_evaluate_broker_summary("TLKM.JK", "IDX", current_price=3000)
    assert res["bandar_status"] == "NO_DATA"
    assert res["top_buyers"] == []


def test_broker_fetch_failure_is_neutral(monkeypatch):
    set_setting("sectors_api_key", "dummy-test-key")
    monkeypatch.setattr(bs, "fetch_from_sectors_app", lambda sym, key: None)
    try:
        res = bs.fetch_and_evaluate_broker_summary("ASII.JK", "IDX", current_price=5000, force_refresh=True)
        assert res["bandar_status"] == "NO_DATA" and res["no_data_reason"] == "FETCH_FAILED"
    finally:
        set_setting("sectors_api_key", "")


def test_backtest_verdict():
    assert sig.backtest_verdict(-0.05, -1.2, 10)["code"] == "NO_EDGE"
    assert "belum terbukti" in sig.backtest_verdict(0.01, 5.0, 10)["text"]
    assert sig.backtest_verdict(0.06, 3.0, 10)["code"] == "POSITIVE"
    assert sig.backtest_verdict(-0.06, -3.0, 10)["code"] == "NEGATIVE"
    assert sig.backtest_verdict(None, None, 10)["code"] == "NO_DATA"


def test_backtest_endpoint_is_non_blocking_and_persists(monkeypatch):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    import threading
    release = threading.Event()

    def slow_compute(market, horizon):
        release.wait(5)   # blocked until the first response is checked (a blocking endpoint would wait here)
        return {"ok": True, "market": market, "horizon_days": horizon, "score": {"ic": 0.0, "samples": 1, "buckets": []},
                "verdict": sig.backtest_verdict(0.0, 0.0, horizon)}

    monkeypatch.setattr(sig, "compute_backtest", slow_compute)
    sig._backtest_cache.clear()
    sig._backtest_errors.clear()
    app = FastAPI()
    app.include_router(sig.router)
    client = TestClient(app)

    r = client.get("/api/backtest", params={"market": "US", "horizon": 7}).json()
    assert r["status"] == "running"
    release.set()
    for _ in range(50):
        r = client.get("/api/backtest", params={"market": "US", "horizon": 7}).json()
        if r["status"] == "ready":
            break
        time.sleep(0.1)
    assert r["status"] == "ready" and r["verdict"]["code"] == "NO_EDGE"

    # survives a restart: in-memory cache gone, persisted result is served
    sig._backtest_cache.clear()
    r2 = client.get("/api/backtest", params={"market": "US", "horizon": 7}).json()
    assert r2["status"] == "ready" and r2["computed_at"] == r["computed_at"]


def test_history_endpoint_horizon_param():
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    app = FastAPI()
    app.include_router(sig.router)
    r = TestClient(app).get("/api/predictions/history", params={"market": "US", "horizon": 10}).json()
    assert r["horizon_days"] == 10
    assert r["summary"]["closed_count"] == 0 and r["summary"]["win_rate_pct"] is None


def test_summarize_groups_track_record():
    from engine.screener.backtest import summarize_groups
    rows = pd.DataFrame({
        "pullback_state": ["PULLBACK_IDEAL"] * 30 + ["UPTREND_EXTENDED"] * 30 + ["RARE"] * 3,
        "fwd_ret": [0.02] * 20 + [-0.01] * 10 + [-0.02] * 20 + [0.01] * 10 + [0.0] * 3,
        "excess_ret": [0.01] * 30 + [-0.01] * 30 + [0.0] * 3,
    })
    g = summarize_groups(rows, "pullback_state")
    assert "RARE" not in g  # below min_count: no claims from tiny samples
    assert g["PULLBACK_IDEAL"]["count"] == 30 and g["PULLBACK_IDEAL"]["hit_rate_pct"] == 66.7
    assert g["UPTREND_EXTENDED"]["beat_index_pct"] == 0.0


def test_reliability_endpoint_serves_stored_result_and_never_blocks(monkeypatch):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    import threading
    release = threading.Event()

    def compute(market, horizon):
        release.wait(5)
        return {"ok": True, "market": market, "horizon_days": horizon, "tickers": 3,
                "score": {"ic": 0.0, "samples": 90, "buckets": [{"bucket": "65-74", "count": 30}], "baseline_hit_rate_pct": 50.0},
                "verdict": sig.backtest_verdict(0.0, 0.0, horizon), "period_start": "2024-01-02", "period_end": "2026-10-01",
                "by_pullback_state": {"PULLBACK_IDEAL": {"count": 30, "hit_rate_pct": 55.0}}, "by_market_mode": {}}

    monkeypatch.setattr(sig, "compute_backtest", compute)
    sig._backtest_cache.clear()
    sig._backtest_errors.clear()
    app = FastAPI()
    app.include_router(sig.router)
    client = TestClient(app)

    r = client.get("/api/backtest/reliability", params={"market": "US", "horizon": 9}).json()
    assert r["available"] is False and r["status"] == "running"
    release.set()
    for _ in range(50):
        r = client.get("/api/backtest/reliability", params={"market": "US", "horizon": 9}).json()
        if r.get("available"):
            break
        time.sleep(0.1)
    assert r["available"] and r["by_pullback_state"]["PULLBACK_IDEAL"]["hit_rate_pct"] == 55.0
    assert r["period_end"] == "2026-10-01" and r["by_score_bucket"][0]["bucket"] == "65-74"


def test_only_buy_signals_become_predictions():
    rows = [
        {"ticker": "A", "score": 80, "verdict": "STRONG_BULLISH", "market_mode": "NORMAL"},
        {"ticker": "B", "score": 70, "verdict": "MILD_BULLISH", "market_mode": "NORMAL", "is_speculative": True},
        {"ticker": "C", "score": 66, "verdict": "MILD_BULLISH", "market_mode": "CRASH"},
        {"ticker": "D", "score": 60, "verdict": "NEUTRAL", "market_mode": "NORMAL"},
        {"ticker": "E", "score": 67, "verdict": "MILD_BULLISH", "market_mode": "BEARISH"},
    ]
    assert [r["ticker"] for r in pred.select_predictions(rows)] == ["A", "E"]


def test_snapshot_replaces_the_day_instead_of_accumulating():
    from engine.db import get_prediction_snapshot
    from engine.db import save_prediction_snapshot as save
    day, mkt = "2031-01-02", "IDX"
    base = {"price": 100, "recommended_entry": 100, "target_tp1": 110, "target_tp2": 120, "stop_loss": 95,
            "risk_reward_ratio": 2, "confluence_score": 4, "money_flow_status": "NEUTRAL", "reasons": []}
    save([{**base, "ticker": f"SNAP{i}.JK", "score": 80 - i, "verdict": "MILD_BULLISH"} for i in range(10)], market=mkt, snapshot_date=day)
    save([{**base, "ticker": "SNAPX.JK", "score": 90, "verdict": "STRONG_BULLISH"}], market=mkt, snapshot_date=day)
    assert [r["ticker"] for r in get_prediction_snapshot(day, market=mkt)] == ["SNAPX.JK"]
    save([], market=mkt, snapshot_date=day)  # a later scan with no buy signal clears the day
    assert get_prediction_snapshot(day, market=mkt) == []
