"""Data health (Bagian 5): lag vs the index, fresh-data gate, per-scan summary, plan date, endpoint."""
from datetime import datetime

import pandas as pd

from engine.collectors.data_quality import lag_vs_reference
from engine.screener import data_health
from engine.screener.actionability import assess

# Saturday 24 Oct 2026, 10:00 WIB: the last closed IDX session is Friday 23 Oct
NOW = datetime.fromisoformat("2026-10-24T10:00:00+07:00")


def _frame(dates):
    return pd.DataFrame({"date": dates, "close": [100.0] * len(dates)})


def test_lag_counts_index_sessions():
    idx = _frame(["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"])
    assert lag_vs_reference(_frame(["2026-10-22", "2026-10-23"]), idx, "IDX", NOW)["days"] == 0
    late = lag_vs_reference(_frame(["2026-10-20", "2026-10-21"]), idx, "IDX", NOW)
    assert late == {"days": 2, "last_bar": "2026-10-21", "expected": "2026-10-23"}


def test_lag_holiday_and_stale_index_are_not_late():
    # 22 Oct was an exchange holiday: the index has no bar, so a stock without it is not late
    idx = _frame(["2026-10-20", "2026-10-21", "2026-10-23"])
    assert lag_vs_reference(_frame(["2026-10-21", "2026-10-23"]), idx, "IDX", NOW)["days"] == 0
    # index cache behind the stock: never counts as late
    assert lag_vs_reference(_frame(["2026-10-23"]), _frame(["2026-10-21"]), "IDX", NOW)["days"] == 0
    assert lag_vs_reference(_frame(["2026-10-23"]), None, "IDX", NOW) is None


def test_lag_ignores_unfinished_bar():
    during = datetime.fromisoformat("2026-10-23T11:00:00+07:00")  # Friday, session open
    idx = _frame(["2026-10-21", "2026-10-22", "2026-10-23"])        # live (unfinished) bar for today
    stock = _frame(["2026-10-21", "2026-10-22"])                    # no live bar yet
    assert lag_vs_reference(stock, idx, "IDX", during)["days"] == 0


def _layak_row(**kw):
    row = {"market": "IDX", "verdict": "MILD_BULLISH", "market_mode": "NORMAL",
           "levels": {"risk_pct": 4.0, "risk_reward_ratio": 1.5, "flags": [], "as_of": "2026-10-23"},
           "screen": {"avg_value_20d": 5e9}}
    row.update(kw)
    return row


def test_fresh_gate():
    assert assess(_layak_row())["status"] == "LAYAK"                       # no lag info (backtest): passes
    assert assess(_layak_row(data_lag={"days": 0}))["status"] == "LAYAK"
    out = assess(_layak_row(data_lag={"days": 2, "last_bar": "2026-10-21", "expected": "2026-10-23"}))
    assert out["status"] == "TUNGGU" and out["gates"]["fresh_ok"] is False
    assert any("terlambat 2 hari bursa" in r and "21 Okt" in r for r in out["reasons"])


def test_summary_counts():
    rows = [
        {"ticker": "AAA.JK", "data_lag": {"days": 0, "expected": "2026-10-23"}},
        {"ticker": "BBB.JK", "data_lag": {"days": 3, "last_bar": "2026-10-20", "expected": "2026-10-23"}},
        {"ticker": "CCC.JK", "data_lag": {"days": 0, "expected": "2026-10-23"}},
    ]
    reports = {"AAA.JK": {"score": 99, "issues": []},
               "CCC.JK": {"score": 72, "issues": [{"code": "PRICE_JUMP", "severity": "warning"},
                                                   {"code": "SHORT_HISTORY", "severity": "info"}]}}
    s = data_health.summarize("IDX", ["AAA.JK", "BBB.JK", "CCC.JK", "DDD.JK"], rows, reports.get, NOW)
    assert (s["asked"], s["analysed"], s["fresh"], s["stale_count"], s["failed_count"]) == (4, 3, 2, 1, 1)
    assert s["failed"] == ["DDD.JK"] and s["stale"][0]["ticker"] == "BBB.JK"
    assert s["low_quality"] == [{"ticker": "CCC.JK", "score": 72, "issues": ["lompatan harga"]}]
    assert s["issues_by_type"] == {"lompatan harga": 1}
    assert s["expected_session"] == "2026-10-23" and not s["ok"]
    assert s["text"] == "Data: 2 dari 4 saham segar · 1 terlambat · 1 gagal diunduh · 1 kualitas rendah"


def test_summary_without_lag_info_does_not_claim_zero_fresh():
    s = data_health.summarize("IDX", ["AAA.JK"], [{"ticker": "AAA.JK"}], lambda t: None, NOW)
    assert "kesegaran diperiksa di scan berikutnya" in s["text"] and not s["ok"]


def test_plan_date_tolerates_a_few_stale_rows():
    def row(d, final=True, frozen=False):
        return {"levels": {"as_of": d, "bar_final": final, "frozen": frozen}}
    rows = [row("2026-10-23")] * 5 + [row("2026-10-22")]
    assert data_health.plan_date(rows) == "2026-10-23"
    # Yahoo mid-update: the newest date is not yet the majority
    assert data_health.plan_date([row("2026-10-23")] + [row("2026-10-22")] * 3) is None
    assert data_health.plan_date([row("2026-10-23", frozen=True)]) is None


def test_endpoint_saved_and_rebuilt(client):
    from engine.db import set_setting
    set_setting(data_health.KEY.format("US"), "")
    r = client.get("/api/data/health?market=US").json()
    assert r["market"] == "US"
    data_health.save(data_health.summarize("US", ["X"], [{"ticker": "X", "data_lag": {"days": 0}}], lambda t: None, NOW))
    r = client.get("/api/data/health?market=US").json()
    assert r["text"] == "Data: 1 dari 1 saham segar" and r["ok"]
