"""Coverage & Control: scan universe, market hours, alerts. Offline (temp DB, no network)."""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="saham_universe_")
os.environ.setdefault("SAHAM_DB_PATH", os.path.join(_tmp, "test.db"))
os.environ["SAHAM_DISABLE_AUTOSCAN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from engine import universe, market_hours, notifications  # noqa: E402
from engine.config import DEFAULT_IDX_TICKERS  # noqa: E402
from engine.db import add_watchlist, remove_watchlist, get_watchlist, get_connection, set_setting  # noqa: E402

from engine.config import DB_PATH, BASE_DIR  # noqa: E402

# These tests wipe the watchlist/alerts: refuse to run against the real database
# (e.g. when another test module imported engine before SAHAM_DB_PATH was set).
if (Path(DB_PATH).resolve() == (BASE_DIR / "saham.db").resolve()
        or Path(DB_PATH).resolve() != Path(os.environ["SAHAM_DB_PATH"]).resolve()):
    pytest.skip("engine is bound to the real saham.db; run with SAHAM_DB_PATH set", allow_module_level=True)

WIB = timezone(timedelta(hours=7))


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    for r in get_watchlist():
        remove_watchlist(r["ticker"])
    for m in ("IDX", "US"):
        universe.reset(m)
    market_hours.set_mode("market_hours")
    market_hours._last_ok.clear()
    with get_connection() as conn:
        conn.execute("DELETE FROM app_settings WHERE key LIKE 'autoscan_postclose_%'")
        conn.execute("DELETE FROM app_settings WHERE key LIKE 'autoscan_last_ok_%'")
        conn.commit()
    notifications._ensure_tables()
    with get_connection() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM alert_state")
        conn.commit()
    set_setting(notifications.PREFS_KEY, "{}")
    # Never hit Yahoo: tickers starting with "NO" do not exist, everything else does
    monkeypatch.setattr(universe, "ticker_exists", lambda t, timeout=0: not t.startswith("NO"))
    yield


# ─── Universe ────────────────────────────────────────────────────────────────

def test_default_universe():
    assert universe.get_scan_universe("IDX") == list(DEFAULT_IDX_TICKERS)


def test_merge_watchlist_added_removed_dedupe():
    add_watchlist("bbca", "", "IDX")          # duplicate of a default, unnormalized
    add_watchlist("LUCK.JK", "", "IDX")       # watchlist-only
    add_watchlist("AAPL", "", "US")           # other market
    assert universe.add_ticker("kota", "IDX")["ok"]
    assert universe.remove_ticker("GOTO", "IDX")["ok"]

    u = universe.get_scan_universe("IDX")
    assert "KOTA.JK" in u and "LUCK.JK" in u
    assert "GOTO.JK" not in u
    assert "AAPL" not in u
    assert u.count("BBCA.JK") == 1
    assert len(u) == len(set(u)) == len(DEFAULT_IDX_TICKERS) - 1 + 2


def test_add_validation_and_duplicates():
    assert not universe.add_ticker("NOPE", "IDX")["ok"]          # does not exist
    assert not universe.add_ticker("B@D!", "IDX")["ok"]          # bad format
    assert not universe.add_ticker("BBCA", "IDX")["ok"]          # already a default
    universe.remove_ticker("BBCA", "IDX")
    assert universe.add_ticker("BBCA", "IDX")["ok"]              # re-adding a removed default
    assert "BBCA.JK" in universe.get_scan_universe("IDX")


def test_watchlist_ticker_cannot_be_removed():
    add_watchlist("LUCK.JK", "", "IDX")
    res = universe.remove_ticker("LUCK", "IDX")
    assert "Watchlist" in res["message"]
    assert "LUCK.JK" in universe.get_scan_universe("IDX")


def test_cap_prefers_watchlist_and_user(monkeypatch):
    cap = len(DEFAULT_IDX_TICKERS) + 2
    monkeypatch.setattr(universe, "MAX_UNIVERSE", cap)
    add_watchlist("LUCK.JK", "", "IDX")
    assert universe.add_ticker("KOTA", "IDX")["ok"]             # defaults + 2, at the cap
    assert not universe.add_ticker("BOLT", "IDX")["ok"]         # over the cap
    monkeypatch.setattr(universe, "MAX_UNIVERSE", 10)
    u = universe.get_scan_universe("IDX")
    assert len(u) == 10
    assert u[0] == "LUCK.JK" and u[1] == "KOTA.JK"
    d = universe.describe("IDX")
    assert d["truncated"] and d["total_requested"] == cap


# ─── Market hours ────────────────────────────────────────────────────────────

def _wib(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=WIB)


# 2026-10-19 is a Monday, 2026-10-24 a Saturday
def test_idx_weekday_open_and_before_open():
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 16, 17, 0))    # Friday's closing scan ran
    assert market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 10, 0))
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 8, 59))
    st = market_hours.session_status("IDX", _wib(2026, 10, 19, 8, 0))
    assert not st["is_open"] and "hari ini 09:00" in st["label"]


def test_idx_weekend():
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 23, 17, 0))
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 24, 11, 0))
    st = market_hours.session_status("IDX", _wib(2026, 10, 24, 11, 0))
    assert st["phase"] == "weekend" and "Senin 09:00" in st["label"]
    # Friday evening -> Monday
    assert "Senin 09:00" in market_hours.session_status("IDX", _wib(2026, 10, 23, 20, 0))["label"]


def test_idx_post_close_scan_once():
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 19, 16, 10))                    # last intraday scan
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 16, 40))  # close not final yet
    assert market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 16, 55))      # one closing scan
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 19, 16, 56))
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 17, 0))   # not twice
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 18, 0))   # evening
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 20, 16, 10))
    assert market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 20, 16, 55))      # next day again


def test_missed_closing_scan_is_caught_up_late_at_night():
    # the app was closed at 16:50 and opened at 21:00: the closing plan is still missing
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 19, 15, 0))
    assert market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 21, 0))
    market_hours.mark_scan_done("IDX", _wib(2026, 10, 19, 21, 1))
    assert not market_hours.should_auto_scan_now("IDX", _wib(2026, 10, 19, 23, 0))
    st = market_hours.session_status("IDX", _wib(2026, 10, 19, 18, 0))
    assert "besok 09:00" in st["label"]


def test_us_session_and_modes():
    ny_open = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)   # 10:00 EDT
    ny_night = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
    market_hours.mark_scan_done("US", datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc))  # Friday close done
    assert market_hours.should_auto_scan_now("US", ny_open)
    assert not market_hours.should_auto_scan_now("US", ny_night)
    market_hours.set_mode("always")
    assert market_hours.should_auto_scan_now("US", ny_night)
    market_hours.set_mode("off")
    assert not market_hours.should_auto_scan_now("US", ny_open)


def test_tz_fallback(monkeypatch):
    import zoneinfo
    def boom(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(zoneinfo, "ZoneInfo", boom)
    st = market_hours.session_status("IDX", _wib(2026, 10, 19, 10, 0))
    assert st["tz_fallback"] and st["is_open"]


# ─── Alerts ──────────────────────────────────────────────────────────────────

def _res(ticker, **kw):
    base = {"ticker": ticker, "market": "IDX", "price": 1000, "score": 60, "verdict": "BULLISH",
            "is_confirmed_breakout": False, "money_flow_status": "NEUTRAL", "stop_loss": 950, "target_tp1": 1100}
    base.update(kw)
    return base


def test_alert_detection_between_two_scans():
    notifications.set_prefs(kinds={"breakout": True, "strong_bullish": True})   # off by default
    add_watchlist("LUCK.JK", "", "IDX")
    add_watchlist("KOTA.JK", "", "IDX")
    add_watchlist("BOLT.JK", "", "IDX")
    first = [_res("BBCA.JK"), _res("BBRI.JK"), _res("LUCK.JK"), _res("KOTA.JK"), _res("BOLT.JK"), _res("NOWL.JK")]
    notifications.on_scan_complete("IDX", first)
    assert notifications.list_alerts()["alerts"] == []          # first scan only records state

    second = [
        _res("BBCA.JK", is_confirmed_breakout=True),
        _res("BBRI.JK", verdict="STRONG_BULLISH"),
        _res("LUCK.JK", price=940),                              # below previous SL 950
        _res("KOTA.JK", price=1120),                             # above previous TP1 1100
        _res("BOLT.JK", money_flow_status="STRONG_OUTFLOW"),
        _res("NOWL.JK", price=900, money_flow_status="STRONG_OUTFLOW"),  # not on watchlist
        _res("NEWX.JK", is_confirmed_breakout=True),             # new ticker: no previous state
    ]
    notifications.on_scan_complete("IDX", second)
    got = {(a["ticker"], a["kind"]) for a in notifications.list_alerts()["alerts"]}
    assert got == {("BBCA.JK", "breakout"), ("BBRI.JK", "strong_bullish"), ("LUCK.JK", "stop_loss"),
                   ("KOTA.JK", "target_hit"), ("BOLT.JK", "outflow")}

    # Same transition again (flapping) inside the cooldown does not duplicate
    notifications.on_scan_complete("IDX", first)
    notifications.on_scan_complete("IDX", second)
    assert len(notifications.list_alerts()["alerts"]) == 5


def test_chase_alerts_are_off_by_default():
    prefs = notifications.get_prefs()["kinds"]
    assert prefs["breakout"] is False and prefs["strong_bullish"] is False
    assert prefs["entry_zone"] and prefs["stop_loss"] and prefs["target_hit"] and prefs["outflow"]
    notifications.on_scan_complete("IDX", [_res("BBCA.JK")])
    notifications.on_scan_complete("IDX", [_res("BBCA.JK", is_confirmed_breakout=True, verdict="STRONG_BULLISH")])
    assert notifications.list_alerts()["alerts"] == []


def test_alert_prefs_and_never_raises():
    notifications.set_prefs(kinds={"breakout": False, "strong_bullish": True})
    notifications.on_scan_complete("IDX", [_res("BBCA.JK")])
    notifications.on_scan_complete("IDX", [_res("BBCA.JK", is_confirmed_breakout=True, verdict="STRONG_BULLISH")])
    kinds = [a["kind"] for a in notifications.list_alerts()["alerts"]]
    assert kinds == ["strong_bullish"]
    notifications.on_scan_complete("IDX", None)                  # garbage in, no exception
    notifications.on_scan_complete("IDX", [{"bad": 1}, "x"])


# ─── API ─────────────────────────────────────────────────────────────────────

def test_api_endpoints():
    from engine.main import app
    c = TestClient(app)

    r = c.get("/api/universe", params={"market": "IDX"})
    assert r.status_code == 200 and r.json()["limit"] == universe.MAX_UNIVERSE

    r = c.post("/api/universe/IDX/tickers", json={"ticker": "kota"}).json()
    assert r["ok"] and "KOTA.JK" in r["universe"]["tickers"]
    assert not c.post("/api/universe/IDX/tickers", json={"ticker": "NOPE"}).json()["ok"]
    r = c.delete("/api/universe/IDX/tickers/GOTO.JK").json()
    assert r["ok"] and "GOTO.JK" not in r["universe"]["tickers"]
    r = c.put("/api/universe", params={"market": "IDX"}, json={"added": ["KOTA", "BOLT", "NOXX"], "removed_defaults": []}).json()
    assert "BOLT.JK" in r["tickers"] and len(r["rejected"]) == 1
    assert c.post("/api/universe/IDX/reset").json()["tickers"] == list(DEFAULT_IDX_TICKERS)
    assert c.get("/api/universe", params={"market": "XX"}).status_code == 400

    s = c.get("/api/universe/session").json()
    assert set(s) == {"IDX", "US"} and "label" in s["IDX"]
    assert c.put("/api/universe/autoscan", json={"mode": "off"}).json()["mode"] == "off"
    assert c.put("/api/universe/autoscan", json={"mode": "bogus"}).status_code == 400

    notifications.set_prefs(kinds={"breakout": True})
    notifications.on_scan_complete("IDX", [_res("BBCA.JK")])
    notifications.on_scan_complete("IDX", [_res("BBCA.JK", is_confirmed_breakout=True)])
    a = c.get("/api/alerts").json()
    assert a["unread_count"] == 1 and a["latest_id"] == a["alerts"][0]["id"]
    assert c.get("/api/alerts", params={"since_id": a["latest_id"]}).json()["alerts"] == []
    assert c.post("/api/alerts/read", json={"ids": [a["alerts"][0]["id"]]}).json()["unread_count"] == 0
    p = c.put("/api/alerts/prefs", json={"kinds": {"outflow": False}, "os_toast": False}).json()
    assert p["kinds"]["outflow"] is False and p["kinds"]["breakout"] is True
    assert c.delete("/api/alerts").json()["deleted"] == 1


def test_idx_sessions_and_friday_lunch_break():
    def sess(d, h, mi):
        return market_hours.session_status("IDX", _wib(2026, 10, d, h, mi))
    assert sess(19, 8, 50)["session"] == "pre_open"
    assert sess(19, 10, 0)["session"] == "session_1" and "istirahat 12:00" in sess(19, 10, 0)["label"]
    lunch = sess(19, 12, 30)
    assert lunch["session"] == "lunch_break" and "sesi 2 buka 13:30" in lunch["label"] and lunch["trading_day_live"]
    assert sess(19, 14, 0)["session"] == "session_2"
    assert sess(19, 15, 55)["session"] == "pre_close"
    # Friday 2026-10-23: lunch 11:30-14:00
    assert sess(23, 11, 45)["session"] == "lunch_break" and "14:00" in sess(23, 11, 45)["label"]
    assert sess(23, 13, 45)["session"] == "lunch_break"
    assert sess(23, 14, 5)["session"] == "session_2"
    assert sess(24, 10, 0)["session"] == "closed" and not sess(24, 10, 0)["trading_day_live"]


def test_checkpoint_waits_outside_trading_hours(monkeypatch):
    from fastapi.testclient import TestClient
    from engine import main
    monkeypatch.setattr(main.market_hours, "session_status", lambda m: {"trading_day_live": False, "session": "closed"})
    r = TestClient(main.app).get("/api/plan/checkpoint?market=IDX").json()
    assert r["live"] is False and r["rows"] == [] and "sesi berikutnya" in r["message"]


def test_closing_scan_starts_after_the_close_is_final():
    from engine.collectors.data_quality import bar_is_final
    for d in (19, 23):  # Monday and Friday
        assert bar_is_final(f"2026-10-{d}", "IDX", _wib(2026, 10, d, 16, 44)) is False
        assert bar_is_final(f"2026-10-{d}", "IDX", _wib(2026, 10, d, 16, 45)) is True
