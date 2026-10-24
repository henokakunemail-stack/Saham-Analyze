"""Live track record (Part 4): verdict rules fixed in advance, pooling per rules version, alerts once."""
from datetime import datetime, timedelta

from engine.screener import track_record as tr


def test_judge_needs_min_trades():
    v = tr.judge([1.0] * (tr.MIN_TRADES - 1))
    assert v["code"] == "BELUM_CUKUP"
    assert v["n"] == tr.MIN_TRADES - 1
    assert "belum bisa disimpulkan" in v["text"]
    empty = tr.judge([])
    assert empty["code"] == "BELUM_CUKUP" and empty["mean_r"] is None and empty["ci90"] is None


def test_judge_losing():
    v = tr.judge([-1.0] * 20 + [0.2] * 20)
    assert v["code"] == "MERUGI"
    assert v["ci90"][1] < 0


def test_judge_below_expectation():
    # mean ~ +0.05, spread small enough that the upper bound stays under 0.36
    v = tr.judge([0.5, -0.4] * 20)
    assert v["code"] == "DI_BAWAH_HARAPAN"
    assert 0 <= v["ci90"][1] < tr.EXPECTED_R


def test_judge_proven_positive():
    v = tr.judge([1.0, 0.2] * 20)
    assert v["code"] == "TERBUKTI_POSITIF"
    assert v["ci90"][0] > 0


def test_judge_consistent_but_uncertain():
    v = tr.judge([2.5, -1.5] * 15)  # mean +0.5, wide spread, n = 30
    assert v["code"] == "SESUAI_BELUM_PASTI"
    lo, hi = v["ci90"]
    assert lo <= 0 and hi >= tr.EXPECTED_R


def test_build_pools_only_current_rules():
    snaps = {
        "2026-10-27": [{"ticker": "AAA", "rules_version": "v2"}, {"ticker": "OLD", "rules_version": ""}],
        "2026-10-28": [{"ticker": "BBB", "rules_version": "v2"}, {"ticker": "CCC", "rules_version": "v2"}],
    }
    seen = []

    def evaluate(items):
        seen.extend(x["ticker"] for x in items)
        status = {"AAA": ("HIT_TP1", 1.2), "BBB": ("STOPPED_OUT", -1.0), "CCC": ("WAITING_ENTRY", None)}
        return {"items": [{"ticker": x["ticker"], "status": status[x["ticker"]][0],
                           "r_multiple": status[x["ticker"]][1]} for x in items]}

    out = tr.build(["2026-10-28", "2026-10-27"], snapshot=lambda d: snaps[d], evaluate=evaluate, rules_version="v2")
    assert sorted(seen) == ["AAA", "BBB", "CCC"]
    assert out["older_rules_predictions"] == 1
    assert out["predictions"] == 3 and out["filled"] == 2 and out["closed"] == 2 and out["waiting"] == 1
    assert out["win_pct"] == 50.0 and out["profit_factor"] == 1.2
    assert out["since"] == "2026-10-27"
    assert out["verdict"]["code"] == "BELUM_CUKUP"
    assert [t["ticker"] for t in out["trades"]] == ["BBB", "AAA"]


def test_rules_version_saved_and_endpoint(client):
    from engine.db import save_prediction_snapshot, get_prediction_snapshot
    from engine.screener.actionability import RULES_VERSION
    item = {"ticker": "TRK1.JK", "score": 70, "verdict": "BUY", "price": 1000, "recommended_entry": 990,
            "target_tp1": 1100, "target_tp2": 1200, "stop_loss": 940, "risk_reward_ratio": 2.0,
            "entry_low": 980, "entry_high": 1000, "atr14": 30}
    save_prediction_snapshot([item], market="IDX", snapshot_date="2020-01-06", rules_version=RULES_VERSION)
    rows = get_prediction_snapshot("2020-01-06", market="IDX")
    assert rows and rows[0]["rules_version"] == RULES_VERSION

    r = client.get("/api/predictions/track-record?market=IDX")
    assert r.status_code == 200
    body = r.json()
    assert body["market"] == "IDX" and body["rules_version"] == RULES_VERSION
    assert body["verdict"]["code"] in tr.VERDICTS
    assert body["verdict"]["expected_r"] == tr.EXPECTED_R
    save_prediction_snapshot([], market="IDX", snapshot_date="2020-01-06")


def test_on_track_record_alerts_once():
    from engine import notifications
    bad = tr.judge([-1.0] * 40)
    good = tr.judge([1.0, 0.2] * 20)
    assert notifications.on_track_record("US", good) is None          # good: no alert
    first = notifications.on_track_record("US", bad)
    assert first is not None and first["kind"] == "track_record"
    assert notifications.on_track_record("US", bad) is None           # same state: silent
    assert notifications.on_track_record("US", good) is None
    later = datetime.now() + timedelta(days=7)                        # past the alert cooldown
    assert notifications.on_track_record("US", bad, now=later) is not None  # turned bad again


def test_weekly_telegram_includes_live_record():
    from engine.telegram import messages
    track = {"verdict": tr.judge([1.0] * 5)}
    text = messages.weekly({"total_predictions": 3, "hit_tp1_count": 1}, ["2026-10-30", "2026-10-26"], "IDX", track)
    assert "Rekam jejak nyata aturan sekarang" in text and "Belum cukup data" in text
    empty = messages.weekly({}, [], "IDX", track)
    assert "Belum cukup data" in empty
    assert "Rekam jejak nyata" not in messages.weekly({}, [], "IDX")
