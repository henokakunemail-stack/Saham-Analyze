"""Alert `entry_zone`: live price comes down into the buy zone of today's frozen plan. Offline, temp DB."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from engine import notifications
from engine.db import add_watchlist, get_connection, get_watchlist, remove_watchlist, set_setting

T0 = datetime(2026, 10, 23, 10, 0)


@pytest.fixture(autouse=True)
def clean_state():
    for r in get_watchlist():
        remove_watchlist(r["ticker"])
    notifications._ensure_tables()
    with get_connection() as conn:
        conn.execute("DELETE FROM alerts")
        conn.execute("DELETE FROM alert_state")
        conn.commit()
    set_setting(notifications.PREFS_KEY, "{}")
    yield


def _row(ticker, price=3100, day_low=3050, score=50, frozen=True, as_of="2026-10-22", status=None, **lv_kw):
    levels = {"entry_low": 2930, "entry_high": 3020, "recommended_entry": 2975, "stop_loss": 2790,
              "target_tp1": 3150, "target_tp2": 3300, "as_of": as_of}
    levels.update(lv_kw)
    if frozen:
        levels["frozen"] = True
        levels["live"] = {"price": price, "status": "IN_ZONE" if price <= levels["entry_high"] else "ABOVE_ZONE",
                          "day_low": day_low, "day_high": max(price, day_low),
                          "touched_stop": day_low <= levels["stop_loss"], "touched_tp1": False}
    row = {"ticker": ticker, "market": "IDX", "price": price, "score": score, "verdict": "BULLISH",
           "is_confirmed_breakout": False, "money_flow_status": "NEUTRAL",
           "stop_loss": levels["stop_loss"], "target_tp1": levels["target_tp1"], "levels": levels}
    if status:
        row["action"] = {"status": status, "reasons": [], "gates": {}}
    return row


def _filler(n, score=10):
    """Rows that push other tickers out of the Top 10 (no frozen plan, never alert)."""
    return [_row(f"F{i:02d}.JK", score=score + i, frozen=False) for i in range(n)]


def _entry_alerts():
    return [a for a in notifications.list_alerts()["alerts"] if a["kind"] == "entry_zone"]


def test_kind_is_a_preference():
    assert "entry_zone" in notifications.KINDS
    assert notifications.get_prefs()["kinds"]["entry_zone"] is True


def test_enters_zone_from_above_watchlist():
    add_watchlist("PTBA.JK", "", "IDX")
    rest = _filler(12, score=60)                                  # PTBA is not in the Top 10
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=3100, day_low=3060)] + rest, now=T0)
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=3000, day_low=2990)] + rest,
                                   now=T0 + timedelta(minutes=5))
    assert _entry_alerts() == []                                  # above the zone, then in it but above the buy limit
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2970, day_low=2960)] + rest,
                                   now=T0 + timedelta(minutes=15))
    got = _entry_alerts()
    assert len(got) == 1
    a = got[0]
    assert a["ticker"] == "PTBA.JK" and a["title"] == "PTBA.JK: mencapai harga saran beli"
    assert a["message"] == "Harga 2.970 mencapai harga saran beli 2.975 (zona 2.930–3.020). Cut loss 2.790, TP1 3.150."


def test_intraday_dip_then_bounce_still_fires():
    add_watchlist("PTBA.JK", "", "IDX")
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=3060, day_low=2970)], now=T0)
    msg = _entry_alerts()[0]["message"]
    assert msg.startswith("Harga sempat 2.970 mencapai harga saran beli 2.975 (zona 2.930–3.020), kini 3.060.")


def test_gap_below_stop_does_not_fire():
    add_watchlist("PTBA.JK", "", "IDX")
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2700, day_low=2650)], now=T0)
    # Recovered into the zone after touching the cut loss: plan is void, still no entry alert
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2950, day_low=2650)], now=T0 + timedelta(minutes=15))
    assert _entry_alerts() == []


def test_no_frozen_plan_no_alert():
    add_watchlist("PTBA.JK", "", "IDX")
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2990, frozen=False)], now=T0)
    row = _row("PTBA.JK", price=2970, day_low=2960)
    row["levels"].pop("live")                                     # frozen but no live data
    notifications.on_scan_complete("IDX", [row], now=T0 + timedelta(minutes=15))
    assert _entry_alerts() == []


def test_once_per_plan_and_cooldown():
    add_watchlist("PTBA.JK", "", "IDX")
    in_zone = [_row("PTBA.JK", price=2970, day_low=2960)]
    notifications.on_scan_complete("IDX", in_zone, now=T0)
    notifications.on_scan_complete("IDX", in_zone, now=T0 + timedelta(minutes=15))
    assert len(_entry_alerts()) == 1
    with get_connection() as conn:
        st = conn.execute("SELECT entry_low, entry_high, entry_as_of FROM alert_state WHERE ticker = 'PTBA.JK'").fetchone()
    assert (st["entry_low"], st["entry_high"], st["entry_as_of"]) == (2930, 3020, "2026-10-22")

    # Same plan, later than the cooldown: the plan already alerted, so nothing new
    notifications.on_scan_complete("IDX", in_zone, now=T0 + timedelta(hours=13))
    assert len(_entry_alerts()) == 1

    # A new plan inside the 12h cooldown is held back by the cooldown...
    new_plan = [_row("PTBA.JK", price=2900, day_low=2890, as_of="2026-10-23", entry_low=2880, entry_high=2950,
                     recommended_entry=2910)]
    notifications.on_scan_complete("IDX", new_plan, now=T0 + timedelta(hours=1))
    assert len(_entry_alerts()) == 1
    # ...fires once the cooldown is over, then only once
    notifications.on_scan_complete("IDX", new_plan, now=T0 + timedelta(hours=12, minutes=30))
    notifications.on_scan_complete("IDX", new_plan, now=T0 + timedelta(hours=40))
    got = _entry_alerts()
    assert len(got) == 2 and "2.880–2.950" in got[0]["message"]


def test_hindari_skipped_and_status_appended():
    add_watchlist("PTBA.JK", "", "IDX")
    add_watchlist("ADRO.JK", "", "IDX")
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2970, day_low=2960, status="HINDARI"),
                                           _row("ADRO.JK", price=2970, day_low=2960, status="LAYAK")], now=T0)
    got = _entry_alerts()
    assert [a["ticker"] for a in got] == ["ADRO.JK"]
    assert got[0]["message"].endswith(" Status: LAYAK.")


def test_top10_non_watchlist_fires_but_not_rank_11():
    rows = [_row("TOPX.JK", price=2970, day_low=2960, score=90),
            _row("LOWX.JK", price=2970, day_low=2960, score=5)] + _filler(10, score=20)
    notifications.on_scan_complete("IDX", rows, now=T0)
    assert [a["ticker"] for a in _entry_alerts()] == ["TOPX.JK"]


def test_top10_uses_rank_when_present():
    a = _row("AAAA.JK", price=2970, day_low=2960, score=10)
    a["rank"] = 1                                                 # low score but ranked first
    b = _row("BBBB.JK", price=2970, day_low=2960, score=99)
    b["rank"] = 11
    notifications.on_scan_complete("IDX", [a, b], now=T0)
    assert [x["ticker"] for x in _entry_alerts()] == ["AAAA.JK"]


def test_pref_off_disables_entry_zone():
    add_watchlist("PTBA.JK", "", "IDX")
    notifications.set_prefs(kinds={"entry_zone": False})
    notifications.on_scan_complete("IDX", [_row("PTBA.JK", price=2970, day_low=2960)], now=T0)
    assert _entry_alerts() == []


def test_migrates_old_alert_state(tmp_path, monkeypatch):
    """An alert_state created before entry_zone gains the new columns."""
    from engine import config, db
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE alert_state (market TEXT NOT NULL, ticker TEXT NOT NULL, verdict TEXT,
                        is_confirmed_breakout INTEGER, money_flow_status TEXT, price REAL, stop_loss REAL,
                        target_tp1 REAL, updated_at TEXT, PRIMARY KEY (market, ticker))""")
        conn.execute("INSERT INTO alert_state (market, ticker, price) VALUES ('IDX', 'OLD.JK', 1)")
    monkeypatch.setattr(config, "DB_PATH", path)
    if hasattr(db, "DB_PATH"):
        monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(notifications, "_initialized_for", None)
    with get_connection() as conn:
        if conn.execute("PRAGMA database_list").fetchone()[2] != str(path):
            pytest.skip("get_connection is not bound to config.DB_PATH at call time")
    notifications._ensure_tables()
    notifications._ensure_tables()                                # idempotent
    with sqlite3.connect(path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(alert_state)")}
        assert {"entry_low", "entry_high", "entry_as_of"} <= cols
        assert conn.execute("SELECT price FROM alert_state WHERE ticker = 'OLD.JK'").fetchone()[0] == 1
    monkeypatch.undo()
    notifications._initialized_for = None
