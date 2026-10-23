"""Technical Quality: OHLCV cleaning, quality report, cache freshness, yfinance retry, DB init (offline)."""
import threading
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from engine.collectors import data_quality as dq
from engine.collectors import market_data as md
from engine import db

WIB = timezone(timedelta(hours=7))


def dirty_frame(make_ohlcv):
    df = make_ohlcv(n=250, seed=9, vol=0.008)
    df.loc[10, "close"] = np.nan                       # INVALID_PRICE
    df.loc[11, "open"] = 0.0                           # INVALID_PRICE
    df.loc[20, "high"] = df.loc[20, "low"] * 0.9       # HIGH_LOW_REPAIRED
    df.loc[30, "volume"] = 0.0                         # ZERO_VOLUME (holiday bar)
    df.loc[31, "volume"] = 0.0
    c = df.loc[100, "close"]                           # BAD_TICK: +80% for one bar, then back
    df.loc[101, ["open", "high", "low", "close"]] = [c, c * 1.85, c, c * 1.8]
    df.loc[150:, ["open", "high", "low", "close"]] *= 0.5   # PRICE_JUMP: unadjusted 2:1 split
    df = df.drop(index=range(180, 190))                # DATE_GAP (two weeks missing)
    df = pd.concat([df, df.loc[[40]]], ignore_index=True)  # DUPLICATE_DATE
    return df.sample(frac=1, random_state=1)           # shuffled order


def codes(report):
    return {i["code"]: i for i in report["issues"]}


def test_clean_ohlcv_repairs_and_reports(make_ohlcv):
    raw = dirty_frame(make_ohlcv)
    clean, report = dq.clean_ohlcv(raw, ticker="DIRTY.JK")
    found = codes(report)
    for code in ("INVALID_PRICE", "DUPLICATE_DATE", "HIGH_LOW_REPAIRED", "ZERO_VOLUME", "BAD_TICK", "PRICE_JUMP", "DATE_GAP"):
        assert code in found, (code, list(found))
    assert found["INVALID_PRICE"]["count"] == 2
    assert found["ZERO_VOLUME"]["count"] == 2
    assert found["BAD_TICK"]["count"] == 1
    assert found["PRICE_JUMP"]["count"] == 1

    assert list(clean.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert clean["date"].is_monotonic_increasing and clean["date"].is_unique
    assert (clean[["open", "high", "low", "close"]] > 0).all().all()
    assert (clean["high"] >= clean[["open", "close"]].max(axis=1)).all()
    assert (clean["low"] <= clean[["open", "close"]].min(axis=1)).all()
    assert (clean["volume"] > 0).all()
    assert report["rows_raw"] == len(raw)
    assert report["rows_clean"] == len(clean)
    assert report["score"] < 70 and report["grade"] in ("FAIR", "POOR")


def test_clean_series_scores_full(make_ohlcv):
    clean, report = dq.clean_ohlcv(make_ohlcv(n=260), ticker="BBCA.JK")
    assert report["issues"] == []
    assert len(clean) == 260
    assert report["base_score"] == 100


def test_empty_input():
    clean, report = dq.clean_ohlcv(pd.DataFrame(), ticker="X.JK")
    assert clean.empty and report["score"] == 0 and report["grade"] == "POOR"


def test_last_closed_session_idx():
    # Tue 2026-10-20 10:00 WIB (market open): last final bar is Mon 19th
    assert dq.last_closed_session("BBCA.JK", datetime(2026, 10, 20, 10, 0, tzinfo=WIB)).date().isoformat() == "2026-10-19"
    # Tue 17:00 WIB (after close + buffer): Tue's bar is final
    assert dq.last_closed_session("BBCA.JK", datetime(2026, 10, 20, 17, 0, tzinfo=WIB)).date().isoformat() == "2026-10-20"
    # Saturday: Friday
    assert dq.last_closed_session("BBCA.JK", datetime(2026, 10, 24, 12, 0, tzinfo=WIB)).date().isoformat() == "2026-10-23"
    # Monday 08:00 WIB before open: previous Friday
    assert dq.last_closed_session("BBCA.JK", datetime(2026, 10, 26, 8, 0, tzinfo=WIB)).date().isoformat() == "2026-10-23"


def test_last_closed_session_us_uses_new_york_time():
    # Wed 2026-10-21 08:00 WIB == Tue 21:00 New York: Tuesday's US bar is final
    assert dq.last_closed_session("AAPL", datetime(2026, 10, 21, 8, 0, tzinfo=WIB)).date().isoformat() == "2026-10-20"


def test_staleness_in_trading_days():
    now = datetime(2026, 10, 26, 17, 0, tzinfo=WIB)  # Monday after close
    assert dq.staleness_trading_days("BBCA.JK", "2026-10-26", now) == 0
    assert dq.staleness_trading_days("BBCA.JK", "2026-10-23", now) == 1   # Fri -> Mon
    assert dq.staleness_trading_days("BBCA.JK", "2026-10-19", now) == 5
    r = dq.with_staleness({"ticker": "BBCA.JK", "interval": "1d", "rows_clean": 250,
                           "base_score": 100, "last_bar_date": "2026-10-19"}, now)
    assert r["is_stale"] and r["score"] == 70 and r["grade"] == "FAIR"


# ---------------------------------------------------------------------------
# Cache freshness
# ---------------------------------------------------------------------------
def _iso_local(dt):
    # save_candles stores naive local time
    return dt.astimezone().replace(tzinfo=None).isoformat()


def test_intraday_bar_not_final_next_morning():
    fetched = datetime(2026, 10, 20, 11, 0, tzinfo=WIB)       # Tue during session
    next_morning = datetime(2026, 10, 21, 8, 30, tzinfo=WIB)  # Wed before open
    assert md.is_daily_cache_fresh("BBCA.JK", _iso_local(fetched), next_morning) is False


def test_intraday_friday_bar_not_final_on_weekend():
    saturday = datetime(2026, 10, 24, 10, 0, tzinfo=WIB)
    fetched_intraday = datetime(2026, 10, 23, 11, 0, tzinfo=WIB)
    assert md.is_daily_cache_fresh("BBCA.JK", _iso_local(fetched_intraday), saturday) is False
    fetched_after_close = datetime(2026, 10, 23, 17, 0, tzinfo=WIB)
    assert md.is_daily_cache_fresh("BBCA.JK", _iso_local(fetched_after_close), saturday) is True


def test_live_session_ttl():
    now = datetime(2026, 10, 20, 11, 0, tzinfo=WIB)
    assert md.is_daily_cache_fresh("BBCA.JK", _iso_local(now - timedelta(seconds=30)), now) is True
    stale = md.LIVE_BAR_TTL + 60
    assert md.is_daily_cache_fresh("BBCA.JK", _iso_local(now - timedelta(seconds=stale)), now) is False


def test_missing_updated_at_is_stale():
    assert md.is_daily_cache_fresh("BBCA.JK", None) is False


# ---------------------------------------------------------------------------
# yfinance robustness
# ---------------------------------------------------------------------------
def _yf_frame(df):
    idx = pd.to_datetime(df["date"])
    return pd.DataFrame({"Open": df["open"].values, "High": df["high"].values, "Low": df["low"].values,
                         "Close": df["close"].values, "Volume": df["volume"].values}, index=idx)


class FakeTicker:
    calls = 0
    script = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        assert kwargs.get("timeout") == md.YF_TIMEOUT
        FakeTicker.calls += 1
        step = FakeTicker.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake_yf(monkeypatch):
    FakeTicker.calls, FakeTicker.script = 0, []
    monkeypatch.setattr(md.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(md, "YF_RETRIES", 3)
    monkeypatch.setattr(md.time, "sleep", lambda s: None)
    return FakeTicker


def test_retries_transient_errors_then_cleans_and_caches(fake_yf, make_ohlcv):
    raw = make_ohlcv(n=230, seed=2)
    raw.loc[50, "volume"] = 0
    fake_yf.script = [ConnectionError("reset"), TimeoutError("slow"), _yf_frame(raw)]
    df = md.fetch_stock_ohlcv("RETRY.JK", force_refresh=True)
    assert fake_yf.calls == 3
    assert len(df) == 229 and list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(db.get_candles("RETRY.JK", limit=1000)) == 229
    report = db.get_data_quality_report("RETRY.JK")
    assert report["source"] == "network" and "ZERO_VOLUME" in codes(report)


def test_network_failure_falls_back_to_cache(fake_yf, make_ohlcv):
    db.save_candles("FALLBACK.JK", make_ohlcv(n=220, seed=3).to_dict("records"))
    fake_yf.script = [ConnectionError("down")] * 3
    df = md.fetch_stock_ohlcv("FALLBACK.JK", force_refresh=True)
    assert fake_yf.calls == 3
    assert len(df) == 220
    assert db.get_data_quality_report("FALLBACK.JK")["source"] == "cache_fallback"


def test_no_data_is_not_retried(fake_yf):
    fake_yf.script = [pd.DataFrame()]
    assert md.fetch_stock_ohlcv("NODATA.JK", force_refresh=True).empty
    assert fake_yf.calls == 1


def test_intraday_failure_never_returns_daily_cache(fake_yf, make_ohlcv):
    db.save_candles("INTRA.JK", make_ohlcv(n=220, seed=4).to_dict("records"))
    fake_yf.script = [ConnectionError("down")] * 3
    assert md.fetch_stock_ohlcv("INTRA.JK", interval="5m").empty


def test_fresh_cache_skips_network(fake_yf, make_ohlcv):
    db.save_candles("CACHED.JK", make_ohlcv(n=260, seed=5).to_dict("records"))
    df = md.fetch_stock_ohlcv("CACHED.JK")
    assert fake_yf.calls == 0
    assert len(df) == 260


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
def test_data_quality_endpoint_on_dirty_data(client, fake_yf, make_ohlcv):
    dirty = dirty_frame(make_ohlcv).sort_values("date").drop_duplicates("date")
    fake_yf.script = [_yf_frame(dirty)]
    md.fetch_stock_ohlcv("DIRTY.JK", force_refresh=True)

    one = client.get("/api/system/data-quality", params={"ticker": "DIRTY"})
    assert one.status_code == 200
    r = one.json()
    assert r["ticker"] == "DIRTY.JK"
    for key in ("rows_raw", "rows_clean", "last_bar_date", "staleness_trading_days", "is_stale",
                "score", "grade", "issues", "source", "expected_last_date"):
        assert key in r
    assert {"INVALID_PRICE", "BAD_TICK", "PRICE_JUMP", "ZERO_VOLUME", "DATE_GAP"} <= {i["code"] for i in r["issues"]}

    all_ = client.get("/api/system/data-quality").json()
    assert all_["summary"]["tickers"] >= 1
    assert any(x["ticker"] == "DIRTY.JK" for x in all_["reports"])
    scores = [x["score"] for x in all_["reports"]]
    assert scores == sorted(scores)

    assert client.get("/api/system/data-quality", params={"ticker": "NEVERLOADED"}).status_code == 404


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def test_init_db_idempotent_under_threads():
    errors = []

    def run():
        try:
            db.init_db()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with db.get_connection() as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
    assert {"data_quality_reports", "idx_screener_market_score", "candles"} <= names


def test_tests_use_temp_db():
    from engine.config import DB_PATH, BASE_DIR
    assert DB_PATH.resolve() != (BASE_DIR / "saham.db").resolve()


def test_prefetch_downloads_stale_tickers_in_one_batch(monkeypatch):
    import numpy as np
    import pandas as pd
    calls, saved = [], {}
    idx = pd.bdate_range("2026-01-01", periods=30)
    cols = pd.MultiIndex.from_product([["AAA.JK", "BBB.JK"], ["Open", "High", "Low", "Close", "Volume"]])
    frame = pd.DataFrame(np.tile([100.0, 101.0, 99.0, 100.5, 1e6], (30, 2)), index=idx, columns=cols)
    monkeypatch.setattr(md, "get_candles", lambda t, limit=1: [])
    monkeypatch.setattr(md, "_download_batch", lambda syms, period: calls.append(list(syms)) or frame)
    monkeypatch.setattr(md, "save_candles", lambda t, rows: saved.setdefault(t, rows))
    monkeypatch.setattr(md, "_clean_daily", lambda t, raw, src, store=True: raw)
    out = md.prefetch_daily(["AAA.JK", "BBB.JK", "CCC.JK"])
    assert calls == [["AAA.JK", "BBB.JK", "CCC.JK"]]          # one request for all three
    assert out["saved"] == 2 and set(saved) == {"AAA.JK", "BBB.JK"}  # CCC missing → fetched later one by one
    assert saved["AAA.JK"][0]["date"] == "2026-01-01"


def test_prefetch_is_incremental_after_todays_full_download(monkeypatch):
    from datetime import datetime as _dt
    import pandas as pd
    today = _dt.now().isoformat()
    full_today = [{"date": f"d{i}", "updated_at": today} for i in range(250)]
    old = [{"date": f"d{i}", "updated_at": "2026-01-01T10:00:00"} for i in range(250)]
    caches = {"AAA.JK": full_today, "BBB.JK": old}
    periods = []
    monkeypatch.setattr(md, "get_candles", lambda t, limit=1: caches[t][-limit:])
    monkeypatch.setattr(md, "is_daily_cache_fresh", lambda t, u, now=None: False)
    monkeypatch.setattr(md, "_download_batch", lambda syms, period: periods.append((tuple(syms), period)) or pd.DataFrame())
    out = md.prefetch_daily(["AAA.JK", "BBB.JK"], "1y", force=True)
    assert (("BBB.JK",), "1y") in periods and (("AAA.JK",), "5d") in periods
    assert out["full"] == 1 and out["incremental"] == 1
    # a backtest asking for long history never takes the shortcut
    periods.clear()
    md.prefetch_daily(["AAA.JK"], "3y", min_bars=400)
    assert periods == [(("AAA.JK",), "3y")]


def test_bars_written_by_this_scan_stay_fresh_for_the_scan(monkeypatch):
    from datetime import datetime as _dt, timedelta as _td
    started = _dt.now().astimezone() - _td(minutes=10)
    written = (started + _td(minutes=1)).replace(tzinfo=None).isoformat()   # save_candles writes naive local time
    rows = [{"date": f"2026-01-{i % 28 + 1:02d}", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
             "updated_at": written} for i in range(260)]
    monkeypatch.setattr(md, "get_candles", lambda t, limit=260: rows)
    monkeypatch.setattr(md, "is_daily_cache_fresh", lambda t, u, now=None: False)   # live TTL already ran out
    monkeypatch.setattr(md, "_clean_daily", lambda t, df, src, store=True: df)
    monkeypatch.setattr(md, "get_data_quality_report", lambda t: {"ok": 1})
    called = []
    monkeypatch.setattr(md, "_yf_history", lambda *a, **k: called.append(1) or (_ for _ in ()).throw(RuntimeError("network")))
    df = md.fetch_stock_ohlcv("AAA.JK", "1y", fresh_since=started)
    assert len(df) == 260 and called == []                     # served from the scan's own download
    md.fetch_stock_ohlcv("AAA.JK", "1y")                        # without the scan context it refetches
    assert called


def test_idx_holidays_follow_the_index_calendar(monkeypatch):
    from engine import db
    from engine.collectors import abnormal_days
    days = pd.bdate_range("2026-12-01", "2027-01-15")
    closed = {"2026-12-24", "2026-12-25", "2026-12-31", "2027-01-01"}
    bars = [{"date": d.strftime("%Y-%m-%d")} for d in days if d.strftime("%Y-%m-%d") not in closed]
    monkeypatch.setattr(db, "get_candles", lambda sym, limit=1000: bars if sym == "^JKSE" else [])
    monkeypatch.setitem(abnormal_days._holiday_cache, "at", 0.0)
    hol = abnormal_days.idx_market_holidays()
    assert closed <= hol and "2026-12-28" not in hol and "2024-04-10" in hol
    monkeypatch.setitem(abnormal_days._holiday_cache, "at", 0.0)
