"""Fase 4: market breadth & sector strength (engine/market_breadth.py, engine/sectors.py, routes/market.py)."""
import time

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from engine import db, market_breadth as mb, sectors
from engine.routes import market as market_routes


@pytest.fixture(autouse=True)
def _schema():
    db.init_db()


def _frame(closes, dates, shape="mid"):
    """OHLCV frame; shape 'top' = close at the day's high (CMF +), 'bottom' = at the low (CMF −), 'mid' = middle."""
    c = np.asarray(closes, dtype=float)
    if shape == "top":
        high, low = c, c - 2
    elif shape == "bottom":
        high, low = c + 2, c
    elif shape == "flat":
        high, low = c, c
    else:
        high, low = c + 1, c - 1
    return pd.DataFrame({"date": list(dates), "open": c, "high": high, "low": low, "close": c,
                         "volume": np.full(len(c), 1000.0)})


DATES = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=60)]


# ─── Breadth metrics ─────────────────────────────────────────────────────────

def test_metrics_hand_computed():
    d25 = DATES[:25]
    frames = {
        # strictly rising, close at the high: above EMA20, advancer, 20-day closing high, CMF > 0
        "UP": _frame(range(100, 125), d25, "top"),
        # strictly falling, close at the low: below EMA20, decliner, 20-day closing low, CMF < 0
        "DOWN": _frame(range(200, 175, -1), d25, "bottom"),
        # only 10 bars: unchanged today, too short for EMA20 / CMF / 20-day high-low
        "SHORT": _frame([50.0] * 10, d25[-10:]),
        # last bar the day before: not counted on this date at all
        "STALE": _frame(range(100, 124), d25[:-1], "top"),
    }
    m = mb.compute_for_date(frames, d25[-1])
    assert m == {
        "n": 3,
        "pct_above_ema20": 50.0,     # UP yes, DOWN no, SHORT not eligible
        "pct_above_ema50": None,     # nobody has 50 bars
        "pct_above_ema200": None,
        "advancers": 1, "decliners": 1, "unchanged": 1,
        "new_high_20d": 1, "new_low_20d": 1,
        "pct_cmf_pos": 50.0,         # UP +1, DOWN −1
    }


def test_metrics_ema50_and_ties():
    d60 = DATES[:60]
    frames = {
        "UP60": _frame(range(100, 160), d60, "top"),            # above EMA20 & EMA50
        "FLAT": _frame([100.0] * 60, d60, "flat"),              # close == EMA → not above; equal close → no new high/low
        "DIP": _frame([100.0] * 59 + [99.0], d60),              # one bar below a flat EMA → below, decliner, new low
    }
    m = mb.compute_for_date(frames, d60[-1])
    assert m["n"] == 3
    assert m["pct_above_ema20"] == pytest.approx(33.3)
    assert m["pct_above_ema50"] == pytest.approx(33.3)
    assert m["pct_above_ema200"] is None
    assert (m["advancers"], m["decliners"], m["unchanged"]) == (1, 1, 1)
    assert (m["new_high_20d"], m["new_low_20d"]) == (1, 1)
    # CMF: UP60 at the high (+), FLAT zero range (0 → not > 0), DIP mid-range (0)
    assert m["pct_cmf_pos"] == pytest.approx(33.3)


def test_no_lookahead(make_ohlcv):
    frames = {f"T{i}": make_ohlcv(n=260, seed=i, end="2026-10-23") for i in range(5)}
    series = mb.compute_series(frames)
    day = sorted(series)[-40]
    truncated = {t: f[f["date"] <= day] for t, f in frames.items()}
    assert mb.compute_for_date(truncated, day) == series[day]
    assert mb.compute_for_date(frames, day) == series[day]
    # Wild future data must not change the past
    shocked = {}
    for t, f in frames.items():
        g = f.copy()
        g.loc[g["date"] > day, ["open", "high", "low", "close"]] *= 3
        shocked[t] = g
    assert mb.compute_series(shocked)[day] == series[day]
    assert mb.compute_for_date(shocked, day) == series[day]


def test_datetime_index_frames(make_ohlcv):
    f = make_ohlcv(n=60, seed=3, end="2026-10-23")
    g = f.set_index(pd.to_datetime(f["date"])).drop(columns=["date"])
    assert mb.compute_for_date({"A": g}, "2026-10-23") == mb.compute_for_date({"A": f}, "2026-10-23")


def test_backfill_history_ad_line_and_latest(make_ohlcv):
    frames = {f"T{i}": make_ohlcv(n=200, seed=10 + i, end="2026-10-23") for i in range(4)}
    stored = mb.backfill("T_HIST", list(frames), days=30, frames=frames)
    assert stored == 30
    hist = mb.history("T_HIST", 30)
    assert len(hist) == 30
    assert [h["date"] for h in hist] == sorted(h["date"] for h in hist)
    running = 0
    for h in hist:
        running += h["advancers"] - h["decliners"]
        assert h["ad_line"] == running
    series = mb.compute_series(frames)
    assert {k: v for k, v in hist[-1].items() if k not in ("date", "ad_line")} == series[hist[-1]["date"]]
    last = mb.latest("T_HIST")
    assert last["date"] == hist[-1]["date"] and last["pct_above_ema50"] == hist[-1]["pct_above_ema50"]
    assert len(mb.history("T_HIST", 10)) == 10
    assert mb.history("T_HIST", 10)[-1]["date"] == hist[-1]["date"]


def test_update_today(make_ohlcv):
    frames = {f"T{i}": make_ohlcv(n=200, seed=20 + i, end="2026-10-22") for i in range(3)}
    # Empty table → full default backfill
    out = mb.update_today("T_UPD", list(frames), frames=frames)
    assert out["date"] == "2026-10-22"
    assert len(mb.history("T_UPD", 500)) == mb.DEFAULT_DAYS
    # A new session arrives → stored, nothing else lost
    more = {t: pd.concat([f, f.tail(1).assign(date="2026-10-23")], ignore_index=True) for t, f in frames.items()}
    out = mb.update_today("T_UPD", list(more), frames=more)
    assert out["date"] == "2026-10-23"
    hist = mb.history("T_UPD", 500)
    assert hist[-1]["date"] == "2026-10-23" and len(hist) == mb.DEFAULT_DAYS + 1
    assert hist[-1]["unchanged"] == 3  # the copied bar closed flat
    assert mb.update_today("T_NONE", [], frames={}) is None


def test_stray_dates_dropped(make_ohlcv):
    frames = {f"T{i}": make_ohlcv(n=60, seed=30 + i, end="2026-10-23") for i in range(4)}
    stray = frames["T0"].copy()
    stray = pd.concat([stray, stray.tail(1).assign(date="2026-10-25")], ignore_index=True)  # a Sunday bar
    frames["T0"] = stray
    assert "2026-10-25" not in mb.compute_series(frames)


def test_label_thresholds():
    assert mb.label({"pct_above_ema50": 28.0}) == "Lemah (28% di atas EMA50)"
    cases = [(85, "STRONG"), (70, "STRONG"), (69.4, "HEALTHY"), (50, "HEALTHY"), (49.4, "NEUTRAL"),
             (30, "NEUTRAL"), (29.6, "NEUTRAL"), (29.4, "WEAK"), (15, "WEAK"), (14.4, "VERY_WEAK"), (0, "VERY_WEAK")]
    for pct, code in cases:
        assert mb.classify({"pct_above_ema50": pct})["code"] == code, pct
    assert mb.classify({"pct_above_ema50": 29.6})["text"] == "Netral (30% di atas EMA50)"
    assert mb.classify(None) == {"code": "NO_DATA", "text": "Belum ada data"}
    assert mb.classify({"pct_above_ema50": None})["code"] == "NO_DATA"


# ─── Sectors ─────────────────────────────────────────────────────────────────

def test_map_label():
    assert sectors.map_label("Energy") == "Energi"
    assert sectors.map_label("Financial Services", "Banks - Regional") == "Keuangan"
    assert sectors.map_label("Consumer Defensive") == "Konsumen Primer"
    assert sectors.map_label("Consumer Cyclical") == "Konsumen Non-Primer"
    assert sectors.map_label("Utilities") == "Infrastruktur"
    assert sectors.map_label("Communication Services", "Telecom Services") == "Infrastruktur"
    assert sectors.map_label("Communication Services", "Internet Content & Information") == "Teknologi"
    assert sectors.map_label("Communication Services", "Entertainment") == "Konsumen Non-Primer"
    assert sectors.map_label("Communication Services", "Something New") == "Infrastruktur"
    assert sectors.map_label("Basic Materials", "Coking Coal") == "Energi"
    assert sectors.map_label("Industrials", "Marine Shipping") == "Transportasi & Logistik"
    assert sectors.map_label("Martian Mining") == "Lainnya"
    assert sectors.map_label(None, None) == "Lainnya"


def test_sector_of_cache_and_overrides():
    assert sectors.sector_of("ZZZZ", "IDX") == "Lainnya"            # nothing cached
    sectors._save("ZZZZ.JK", "Healthcare", "Medical Care Facilities", "yahoo")
    assert sectors.sector_of("ZZZZ", "IDX") == "Kesehatan"          # bare IDX code is normalized
    assert sectors.sector_of("ZZZZ.JK", "IDX") == "Kesehatan"
    # Override wins without any Yahoo data, and over an odd Yahoo label
    assert sectors.sector_of("BBCA", "IDX") == "Keuangan"
    sectors._save("TLKM.JK", "Technology", "Software - Application", "yahoo")
    assert sectors.sector_of("TLKM.JK", "IDX") == "Infrastruktur"
    assert sectors.sectors_for(["ADRO", "ZZZZ.JK", "NOPE.JK"], "IDX") == {
        "ADRO": "Energi", "ZZZZ.JK": "Kesehatan", "NOPE.JK": "Lainnya"}


def test_refresh_mocked(monkeypatch):
    calls = []
    answers = {"AAA1.JK": ("Energy", "Thermal Coal"), "BBB1.JK": (None, None), "CCC1.JK": RuntimeError("rate limited")}

    def fake(t):
        calls.append(t)
        a = answers[t]
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(sectors, "_fetch_info", fake)
    tickers = ["AAA1", "BBB1", "CCC1", "BBRI"]  # BBRI is an override → never fetched
    s = sectors.refresh(tickers, "IDX")
    assert sorted(calls) == ["AAA1.JK", "BBB1.JK", "CCC1.JK"]
    assert s == {"requested": 3, "fetched": 2, "unknown": 1, "failed": 1, "timed_out": 0}
    assert sectors.sectors_for(tickers, "IDX") == {"AAA1": "Energi", "BBB1": "Lainnya", "CCC1": "Lainnya", "BBRI": "Keuangan"}
    # Fresh rows are not refetched; the failure is retried
    assert sectors.missing_or_stale(tickers, "IDX") == ["CCC1.JK"]
    calls.clear()
    sectors.refresh(tickers, "IDX")
    assert calls == ["CCC1.JK"]
    # max_age 0 → everything non-override is stale again
    calls.clear()
    sectors.refresh(tickers, "IDX", max_age_days=0)
    assert sorted(calls) == ["AAA1.JK", "BBB1.JK", "CCC1.JK"]


def test_refresh_never_raises_and_async(monkeypatch):
    def boom(t):
        raise OSError("offline")
    monkeypatch.setattr(sectors, "_fetch_info", boom)
    assert sectors.refresh(["QQQ1"], "IDX")["failed"] == 1
    monkeypatch.setattr(sectors, "_fetch_info", lambda t: ("Real Estate", "Real Estate - Development"))
    assert sectors.refresh_async(["QQQ2"], "IDX") is True
    deadline = time.time() + 5
    while sectors.is_refreshing() and time.time() < deadline:
        time.sleep(0.02)
    assert sectors.sector_of("QQQ2", "IDX") == "Properti & Real Estat"


def _row(t, sector, r1, r3, price, ema50, score, status=None):
    row = {"ticker": t, "sector": sector, "price": price, "ema50": ema50, "score": score,
           "screen": {"ret_1m": r1, "ret_3m": r3}}
    if status:
        row["action"] = {"status": status}
    return row


def test_sector_strength_ordering():
    rows = [
        _row("E1", "Energi", 1, 10, 110, 100, 60, "LAYAK"),
        _row("E2", "Energi", 2, 20, 90, 100, 70),
        _row("E3", "Energi", 3, 30, 120, 100, 80, "TUNGGU"),
        _row("K1", "Keuangan", 0, 20, 110, 100, 50, "LAYAK"),
        _row("K2", "Keuangan", 0, 20, 105, 100, 55, "LAYAK"),
        _row("K3", "Keuangan", None, None, 0, 0, 40),           # no data → ignored in medians / breadth
        _row("T1", "Teknologi", -1, -5, 90, 100, 30),
        _row("T2", "Teknologi", 1, 5, 110, 100, 35),
        _row("H1", "Kesehatan", 9, 50, 110, 100, 90),            # single stock: ranked after full sectors
        _row("L1", "Lainnya", 9, 100, 110, 100, 90),
        _row("L2", "Lainnya", 9, 100, 110, 100, 90),
    ]
    out = sectors.sector_strength(rows, "IDX")
    assert [s["sector"] for s in out] == ["Keuangan", "Energi", "Teknologi", "Kesehatan", "Lainnya"]
    assert [s["rank"] for s in out] == [1, 2, 3, 4, None]
    e = out[1]
    assert e == {"sector": "Energi", "count": 3, "median_ret_1m": 2.0, "median_ret_3m": 20.0,
                 "pct_above_ema50": 66.7, "median_score": 70.0, "layak": 1, "tickers": ["E3", "E2", "E1"],
                 "rank": 2}
    k = out[0]
    assert k["count"] == 3 and k["median_ret_3m"] == 20.0 and k["pct_above_ema50"] == 100.0 and k["layak"] == 2
    assert out[2]["median_ret_3m"] == 0.0


def test_sector_strength_uses_lookup_and_annotate():
    sectors._save("ANN1.JK", "Energy", "Thermal Coal", "yahoo")
    sectors._save("ANN2.JK", "Energy", "Oil & Gas E&P", "yahoo")
    sectors._save("ANN3.JK", "Technology", None, "yahoo")
    rows = [{"ticker": t, "price": 100, "ema50": 90, "score": 50, "screen": {"ret_1m": r, "ret_3m": r}}
            for t, r in (("ANN1.JK", 5), ("ANN2.JK", 7), ("ANN3.JK", -3), ("ANN4.JK", 1))]
    strength = sectors.annotate(rows, "IDX")
    assert [(r["sector"], r["sector_rank"]) for r in rows] == [
        ("Energi", 1), ("Energi", 1), ("Teknologi", 2), ("Lainnya", None)]
    assert [s["sector"] for s in strength] == ["Energi", "Teknologi", "Lainnya"]


def test_concentration():
    lookup = {"A": "Energi", "B": "Energi", "C": "Energi", "D": "Keuangan", "E": "Keuangan",
              "F": "Lainnya", "G": "Lainnya", "H": "Lainnya"}
    tickers = list(lookup)
    assert sectors.concentration(tickers, lookup) == [{"sector": "Energi", "tickers": ["A", "B", "C"]}]
    assert sectors.concentration(tickers, lookup, min_count=2) == [
        {"sector": "Energi", "tickers": ["A", "B", "C"]}, {"sector": "Keuangan", "tickers": ["D", "E"]}]
    assert sectors.concentration(tickers, lookup, include_unknown=True)[1]["sector"] == "Lainnya"
    rows = [{"ticker": t, "sector": s} for t, s in lookup.items()]
    assert sectors.concentration(["A", "B", "C", "D"], rows) == [{"sector": "Energi", "tickers": ["A", "B", "C"]}]
    # Falls back to the cache / overrides when no sector is given
    assert sectors.concentration(["BBCA", "BBRI", "BMRI", "TLKM"], None) == [
        {"sector": "Keuangan", "tickers": ["BBCA", "BBRI", "BMRI"]}]


# ─── Routes ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(market_routes.router)
    return TestClient(app)


def test_breadth_route_backfills_once(api, monkeypatch, make_ohlcv):
    for i, t in enumerate(("RTA", "RTB", "RTC")):
        f = make_ohlcv(n=220, seed=40 + i, end="2026-10-23")
        db.save_candles(t, f.to_dict("records"))
    monkeypatch.setattr(market_routes, "_universe", lambda m: ["RTA", "RTB", "RTC"])
    r = api.get("/api/market/breadth?market=US&days=60")
    assert r.status_code == 200
    body = r.json()
    assert body["market"] == "US"
    assert len(body["history"]) == 60
    assert body["latest"]["date"] == body["history"][-1]["date"] == "2026-10-23"
    assert body["latest"]["n"] == 3
    assert body["label"] == mb.label(body["latest"]) and body["label_code"]
    assert "ad_line" in body["history"][0]
    # History exists now → no second backfill
    monkeypatch.setattr(mb, "backfill", lambda *a, **k: pytest.fail("backfilled twice"))
    assert len(api.get("/api/market/breadth?market=US&days=10").json()["history"]) == 10
    assert api.get("/api/market/breadth?market=US&days=0").status_code == 422


def test_sectors_route(api, monkeypatch):
    sectors._save("RS1.JK", "Energy", "Thermal Coal", "yahoo")
    sectors._save("RS2.JK", "Energy", "Thermal Coal", "yahoo")
    rows = [
        {"ticker": "RS1.JK", "price": 100, "ema50": 90, "score": 60, "screen": {"ret_1m": 2, "ret_3m": 8},
         "action": {"status": "LAYAK"}, "updated_at": "2026-10-23T16:10:00"},
        {"ticker": "RS2.JK", "price": 80, "ema50": 90, "score": 40, "screen": {"ret_1m": -2, "ret_3m": 4},
         "updated_at": "2026-10-23T16:05:00"},
        {"ticker": "RS3.JK", "price": 50, "ema50": 40, "score": 70, "screen": {"ret_1m": 1, "ret_3m": 1},
         "updated_at": "2026-10-23T16:00:00"},
    ]
    monkeypatch.setattr(market_routes, "get_screener_results", lambda m: rows)
    started = []
    monkeypatch.setattr(sectors, "refresh_async", lambda t, m, *a, **k: started.append(list(t)) or True)
    body = api.get("/api/market/sectors?market=idx").json()
    assert body["market"] == "IDX"
    assert body["updated_at"] == "2026-10-23T16:10:00"
    assert started == [["RS3.JK"]] and body["missing"] == 1 and body["refreshing"] is True
    en = body["sectors"][0]
    assert en["sector"] == "Energi" and en["rank"] == 1 and en["count"] == 2 and en["layak"] == 1
    assert en["median_ret_3m"] == 6.0 and en["pct_above_ema50"] == 50.0
    assert body["sectors"][-1]["sector"] == "Lainnya" and body["sectors"][-1]["rank"] is None
