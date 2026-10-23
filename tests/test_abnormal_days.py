"""Abnormal trading days (ARA/ARB locks, limit moves, halts, corporate actions) and the Yahoo
corporate-action cache (offline: yfinance is monkeypatched)."""
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import pytest

from engine.collectors import abnormal_days as ad
from engine.collectors import corp_actions as ca


def frame(closes, dates=None, start="2026-09-01", spread=0.02, overrides=None):
    """Daily bars with a normal range around each close; overrides {i: (o, h, l, c)}."""
    closes = [float(c) for c in closes]
    dates = dates or pd.bdate_range(start=start, periods=len(closes)).strftime("%Y-%m-%d").tolist()
    rows = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        rows.append({"date": dates[i], "open": o, "high": max(o, c) * (1 + spread),
                     "low": min(o, c) * (1 - spread), "close": c, "volume": 1_000_000.0})
    df = pd.DataFrame(rows)
    for i, (o, h, l, c) in (overrides or {}).items():
        df.loc[i, ["open", "high", "low", "close"]] = [o, h, l, c]
    return df


# ── classify_bars ────────────────────────────────────────────────────────────

def test_vici_lock_down():
    # ... 1115 → 950 → 885 with o=h=l=c=885 on the 885 day (VICI 19 Okt 2026)
    closes = [1200, 1180, 1160, 1150, 1170, 1160, 1140, 1130, 1115, 950, 885, 1000]
    dates = pd.bdate_range(end="2026-10-20", periods=len(closes)).strftime("%Y-%m-%d").tolist()
    df = frame(closes, dates=dates, overrides={10: (885, 885, 885, 885)})
    kinds = ad.classify_bars(df, "IDX")
    assert list(kinds.index) == list(df.index)
    assert dates[10] == "2026-10-19"
    assert kinds.iloc[10] == ad.LOCK_DOWN
    assert kinds.iloc[11] is None


def test_lock_up_and_quiet_single_price_day():
    df = frame([1000] * 5 + [1250, 1260, 1270], overrides={5: (1250, 1250, 1250, 1250),
                                                          7: (1270, 1270, 1270, 1270)})
    kinds = ad.classify_bars(df, "IDX")
    assert kinds.iloc[5] == ad.LOCK_UP
    # One price all day but only 0.8% / 2 ticks from yesterday: an illiquid quiet day, not a lock
    assert kinds.iloc[7] is None
    assert kinds.iloc[:5].isna().all()


def test_lock_within_one_tick():
    df = frame([1000] * 5 + [850], overrides={5: (855, 855, 850, 850)})   # tick 5 at 850
    assert ad.classify_bars(df, "IDX").iloc[5] == ad.LOCK_DOWN


def test_limit_down_and_up_use_bands():
    # Previous close 1000 (band >200–5.000): ARA 25%; ARB 15% since 8 Apr 2025
    df = frame([1000] * 4 + [860, 1075], start="2026-09-01",
               overrides={4: (1000, 1010, 860, 860), 5: (870, 1075, 860, 1075)})
    kinds = ad.classify_bars(df, "IDX")
    assert kinds.iloc[4] == ad.LIMIT_DOWN          # -14% at the low, >= 90% of 15%
    assert kinds.iloc[5] == ad.LIMIT_UP            # +25% at the high
    # Same -14% before the ARB change (band 25% then) is not a limit move
    old = frame([1000] * 4 + [860], start="2024-09-02", overrides={4: (1000, 1010, 860, 860)})
    assert ad.classify_bars(old, "IDX").iloc[4] is None
    # A big drop that closed off the low is not at the limit
    off_low = frame([1000] * 4 + [860], overrides={4: (1000, 1010, 840, 860)})
    assert ad.classify_bars(off_low, "IDX").iloc[4] is None
    # US has no auto-rejection
    assert ad.classify_bars(df, "US").iloc[4] is None


def test_band_tables():
    assert ad.ara_band(150) == 0.35 and ad.ara_band(200) == 0.35
    assert ad.ara_band(201) == 0.25 and ad.ara_band(5000) == 0.25 and ad.ara_band(5001) == 0.20
    assert ad.arb_band(1000, "2024-06-03") == 0.25
    assert ad.arb_band(1000, "2025-04-08") == 0.15
    assert ad.arb_band(150, "2024-06-03") == 0.35


def test_suspension_gap_ignores_holidays():
    dates = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
             "2026-09-11",                     # 4 weekdays missing (7–10 Sep) → halt
             "2026-09-14", "2026-09-17"]       # 2 missing → normal
    df = frame([1000, 1005, 1010, 1000, 1002, 1004, 1006], dates=dates)
    kinds = ad.classify_bars(df, "IDX")
    assert kinds.iloc[4] == ad.SUSPENSION_GAP
    assert kinds.iloc[6] is None
    # Lebaran 2025: closed 28 Mar – 7 Apr (7 weekdays) is not a suspension
    leb = frame([1000, 1001, 1002], dates=["2025-03-26", "2025-03-27", "2025-04-08"])
    assert ad.classify_bars(leb, "IDX").iloc[2] is None
    assert ad.classify_bars(leb, "IDX", holidays=[]).iloc[2] == ad.SUSPENSION_GAP


def test_corp_action_needs_split_or_very_big_jump():
    base = [1000] * 5
    # -50% that holds (unadjusted 2:1 split): no split data needed above 45%
    df = frame(base + [500, 505, 510])
    assert ad.classify_bars(df, "IDX").iloc[5] == ad.CORP_ACTION
    # -40% that holds: only with a split recorded within ±3 days
    df40 = frame(base + [600, 605, 610])
    split_day = df40["date"].iloc[5]
    assert ad.classify_bars(df40, "IDX").iloc[5] != ad.CORP_ACTION
    near = (pd.Timestamp(split_day) + timedelta(days=2)).strftime("%Y-%m-%d")
    assert ad.classify_bars(df40, "IDX", splits=[{"date": near, "ratio": 1.67}]).iloc[5] == ad.CORP_ACTION
    far = (pd.Timestamp(split_day) + timedelta(days=10)).strftime("%Y-%m-%d")
    assert ad.classify_bars(df40, "IDX", splits=[{"date": far, "ratio": 1.67}]).iloc[5] != ad.CORP_ACTION
    # A spike that reverts the next bar is a bad tick, not an action
    spike = frame(base + [1600, 1010, 1000])
    assert ad.classify_bars(spike, "IDX").iloc[5] != ad.CORP_ACTION
    # US: Yahoo history is split-adjusted, a +60% earnings gap is real
    us = frame([20.0] * 5 + [32.0, 32.5, 33.0])
    assert ad.classify_bars(us, "US").iloc[5] is None
    assert ad.classify_bars(us, "US", splits=[us["date"].iloc[5]]).iloc[5] == ad.CORP_ACTION


def test_empty_and_tiny_frames():
    assert len(ad.classify_bars(pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]))) == 0
    assert ad.classify_bars(frame([1000])).tolist() == [None]
    assert ad.recent(pd.DataFrame()) == []


# ── recent / markers ─────────────────────────────────────────────────────────

def test_recent_labels_and_order():
    closes = [1000] * 25 + [850, 760, 800]
    df = frame(closes, overrides={25: (1000, 1000, 850, 850), 26: (760, 760, 760, 760)})
    items = ad.recent(df, "IDX", days=20)
    assert [it["kind"] for it in items] == [ad.LIMIT_DOWN, ad.LOCK_DOWN]      # newest last
    assert items[-1]["label"] == "ARB (terkunci batas bawah)"
    assert items[0]["label"] == "Turun ke batas ARB"
    assert items[-1]["date"] == df["date"].iloc[26]
    assert set(items[0]) == {"date", "kind", "label"}
    # Only the last `days` bars are reported
    assert ad.recent(df, "IDX", days=2) == items[1:]
    # Labels for all kinds are Indonesian
    assert ad.label_for(ad.LOCK_UP) == "ARA (terkunci batas atas)"
    assert ad.label_for(ad.LIMIT_UP) == "Naik ke batas ARA"
    assert ad.label_for(ad.SUSPENSION_GAP) == "Jeda perdagangan / suspensi"
    assert ad.label_for(ad.CORP_ACTION) == "Aksi korporasi (split/right issue?)"
    # Precomputed kinds give the same answer; markers use chart shape
    assert ad.recent(df, "IDX", kinds=ad.classify_bars(df, "IDX")) == items
    m = ad.markers(df, "IDX")
    assert m[-1] == {"time": items[-1]["date"], "kind": ad.LOCK_DOWN, "label": items[-1]["label"]}


def test_recent_with_datetime_dates():
    df = frame([1000] * 6 + [880], overrides={6: (880, 880, 880, 880)})
    df["date"] = pd.to_datetime(df["date"])
    assert ad.recent(df, "IDX")[-1]["date"] == df["date"].iloc[-1].strftime("%Y-%m-%d")


# ── clean_true_range / pivot_mask ────────────────────────────────────────────

def test_clean_true_range_replaces_locked_bar():
    closes = [1200, 1180, 1160, 1150, 1170, 1160, 1140, 1130, 1115, 1100,
              1090, 1080, 1100, 1110, 1120, 1115, 950, 885, 1000]
    df = frame(closes, overrides={17: (885, 885, 885, 885)})
    kinds = ad.classify_bars(df, "IDX")
    assert kinds.iloc[17] == ad.LOCK_DOWN
    raw = ad.true_range(df)
    clean = ad.clean_true_range(df, kinds)
    assert list(clean.index) == list(df.index)
    normal_prev = [raw.iloc[i] for i in range(17) if kinds.iloc[i] not in ad.TR_REPLACE_KINDS][-14:]
    assert clean.iloc[17] == pytest.approx(np.mean(normal_prev))
    assert clean.iloc[17] != pytest.approx(raw.iloc[17])
    others = [i for i in range(len(df)) if i != 17]
    assert np.allclose(clean.iloc[others], raw.iloc[others])
    # No abnormal bars → unchanged
    assert np.allclose(ad.clean_true_range(df, [None] * len(df)), raw)


def test_clean_true_range_without_history_keeps_original():
    df = frame([1000, 850], overrides={1: (850, 850, 850, 850)})
    kinds = ad.classify_bars(df, "IDX")
    assert kinds.iloc[1] == ad.LOCK_DOWN
    out = ad.clean_true_range(df, kinds)
    # Only bar 0 is normal → the lock day takes its TR
    assert out.iloc[1] == pytest.approx(ad.true_range(df).iloc[0])


def test_pivot_mask():
    kinds = [None, ad.LOCK_DOWN, ad.LIMIT_DOWN, ad.CORP_ACTION, ad.SUSPENSION_GAP, ad.LOCK_UP, ad.LIMIT_UP]
    mask = ad.pivot_mask(pd.Series(kinds))
    assert mask.dtype == bool
    assert mask.tolist() == [True, False, True, False, True, False, True]


def test_find_pivots_masked_skips_locked_low():
    lows = pd.Series([10, 9, 8, 7, 6, 3, 6.5, 6.6, 6.7, 6.8, 6.9, 7, 8, 9], dtype=float)
    mask = np.ones(len(lows), dtype=bool)
    from engine.indicators.trend import find_pivots
    assert 5 in find_pivots(lows, kind="low")
    mask[5] = False
    piv = ad.find_pivots_masked(lows, mask, kind="low")
    assert 5 not in piv
    assert 4 in piv            # the real low next to the locked bar can now be the swing low
    assert ad.find_pivots_masked(lows, None, kind="low") == find_pivots(lows, kind="low")


def test_summary_counts():
    s = ad.summary([None, ad.LOCK_DOWN, ad.LOCK_DOWN, ad.CORP_ACTION])
    assert s[ad.LOCK_DOWN] == 2 and s[ad.CORP_ACTION] == 1 and s[ad.LIMIT_UP] == 0


# ── corp_actions (yfinance monkeypatched) ───────────────────────────────────

class FakeTicker:
    calls = 0
    fail = False

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        FakeTicker.calls += 1
        assert kwargs.get("timeout")
        if FakeTicker.fail:
            raise TimeoutError("yahoo down")
        idx = pd.DatetimeIndex(["2024-05-02", "2025-06-10", "2026-07-15"], tz="Asia/Jakarta")
        return pd.DataFrame({"Close": [1.0, 2.0, 3.0], "Dividends": [12.5, 0.0, 0.0],
                             "Stock Splits": [0.0, 0.0, 5.0]}, index=idx)


@pytest.fixture
def fake_yf(monkeypatch):
    FakeTicker.calls = 0
    FakeTicker.fail = False
    monkeypatch.setattr(ca.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(ca, "_failed_at", {})
    yield FakeTicker


def test_fetch_actions_parses_and_caches(fake_yf):
    out = ca.fetch_actions("ABCD.JK")
    assert out == {"splits": [{"date": "2026-07-15", "ratio": 5.0}],
                   "dividends": [{"date": "2024-05-02", "amount": 12.5}]}
    assert fake_yf.calls == 1
    # Cache hit: no second download within a week
    assert ca.fetch_actions("abcd.jk") == out
    assert fake_yf.calls == 1
    assert ca.fetch_splits("ABCD.JK") == out["splits"]
    # After the TTL it is fetched again
    ca.fetch_actions("ABCD.JK", now=datetime.now() + timedelta(days=8))
    assert fake_yf.calls == 2


def test_fetch_actions_failure_returns_empty(fake_yf):
    fake_yf.fail = True
    assert ca.fetch_actions("FAIL.JK") == {"splits": [], "dividends": []}
    # Backoff: the failed ticker is not retried right away
    assert ca.fetch_actions("FAIL.JK") == {"splits": [], "dividends": []}
    assert fake_yf.calls == 1
    assert ca.splits_near("FAIL.JK", "2026-07-15") is False
    assert ca.needs_refetch("FAIL.JK", "2026-01-01") is False


def test_stale_cache_served_when_refresh_fails(fake_yf):
    ok = ca.fetch_actions("STAL.JK")
    fake_yf.fail = True
    assert ca.fetch_actions("STAL.JK", now=datetime.now() + timedelta(days=30)) == ok


def test_splits_near_and_needs_refetch(fake_yf):
    assert ca.splits_near("SPLT.JK", "2026-07-17")            # 2 days after the split
    assert not ca.splits_near("SPLT.JK", "2026-07-25")
    assert ca.splits_near("SPLT.JK", "2026-07-25", days=10)
    assert not ca.splits_near("SPLT.JK", "not a date")
    # Candle cache written before the split → re-download; after it → fine
    assert ca.needs_refetch("SPLT.JK", "2026-07-01T09:00:00", today=date(2026, 10, 23))
    assert not ca.needs_refetch("SPLT.JK", "2026-07-20", today=date(2026, 10, 23))
    assert not ca.needs_refetch("SPLT.JK", None)
    # Pure variant with a given split list (no lookup)
    calls = fake_yf.calls
    assert ca.needs_refetch("X.JK", "2026-01-01", splits=[{"date": "2026-02-01", "ratio": 2}], today=date(2026, 3, 1))
    assert fake_yf.calls == calls


def test_index_tickers_are_skipped(fake_yf):
    assert ca.fetch_actions("^JKSE") == {"splits": [], "dividends": []}
    assert fake_yf.calls == 0
