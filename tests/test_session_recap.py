"""After-close recap: the last session read against the plan it traded on (offline)."""
import pandas as pd
from fastapi.testclient import TestClient

from engine.screener import session_recap as sr

LV = {"entry_low": 4700, "entry_high": 4790, "recommended_entry": 4740, "stop_loss": 4450,
      "target_tp1": 4910, "target_tp2": 5200, "as_of": "2026-10-22"}


def bar(o, h, lo, c):
    return {"open": o, "high": h, "low": lo, "close": c}


def test_read_bar_outcomes():
    assert sr.read_bar(LV, bar(4800, 4950, 4780, 4940))[:2] == (
        "TP1", "Naik ke TP1 4.910 tanpa turun ke harga beli 4.740 — order limit tidak terisi")
    code, text, filled = sr.read_bar(LV, bar(4800, 4950, 4730, 4940))
    assert code == "TP1" and filled and "harga beli 4.740" in text
    assert sr.read_bar(LV, bar(4800, 5250, 4790, 5200))[0] == "TP2"
    assert sr.read_bar(LV, bar(4800, 4820, 4730, 4760))[:1] + (sr.read_bar(LV, bar(4800, 4820, 4730, 4760))[2],) == ("FILLED", True)
    assert sr.read_bar(LV, bar(4800, 4820, 4760, 4790))[0] == "ZONE"
    assert sr.read_bar(LV, bar(4850, 4880, 4800, 4860))[0] == "ABOVE"
    code, text, filled = sr.read_bar(LV, bar(4760, 4770, 4400, 4420))
    assert code == "STOP" and filled and "kena cut loss" in text
    code, text, filled = sr.read_bar(LV, bar(4400, 4500, 4380, 4480))      # gap under the stop
    assert code == "STOP" and not filled and "rencana batal" in text


def test_plan_list_is_remembered_per_close():
    sr.save_plan_list("IDX", "2026-10-21", ["A.JK"])
    sr.save_plan_list("IDX", "2026-10-22", ["B.JK", "C.JK"])
    sr.save_plan_list("IDX", "2026-10-23", ["D.JK"])
    assert sr.plan_list_before("IDX", "2026-10-23") == ("2026-10-22", ["B.JK", "C.JK"])
    assert sr.plan_list_before("IDX", "2026-10-21") == (None, [])
    for i in range(10):
        sr.save_plan_list("IDX", f"2026-11-{i + 1:02d}", ["X.JK"])
    assert sr.plan_list_before("IDX", "2026-10-23") == (None, [])        # only the last 7 closes are kept


def _df(last):
    n = 80
    dates = pd.bdate_range(end="2026-10-23", periods=n).strftime("%Y-%m-%d")
    rows = [{"date": d, "open": 4800, "high": 4820, "low": 4780, "close": 4800, "volume": 1e6} for d in dates]
    rows[-1].update(last)
    return pd.DataFrame(rows)


def test_recap_orders_rows_and_counts(monkeypatch):
    sr._cache.clear()
    frames = {"TP.JK": _df(bar(4800, 4950, 4780, 4940)), "ABV.JK": _df(bar(4850, 4880, 4800, 4860)),
              "STP.JK": _df(bar(4760, 4770, 4400, 4420))}
    out = sr.recap("IDX", {t: "Top 10" for t in frames}, fetch=lambda t: frames[t],
                   plan_fn=lambda f: dict(LV), final_fn=lambda d: True)
    assert [r["ticker"] for r in out["rows"]] == ["STP.JK", "TP.JK", "ABV.JK"]
    assert out["session_date"] == "2026-10-23" and out["counts"]["TP1"] == 1 and out["filled"] == 1
    assert out["rows"][1]["change_pct"] == round((4940 / 4800 - 1) * 100, 2)


def test_checkpoint_after_close_returns_the_recap(monkeypatch):
    from engine import main
    sr._cache.clear()
    monkeypatch.setattr(main.market_hours, "session_status", lambda m: {"trading_day_live": False, "session": "closed"})
    monkeypatch.setattr(main, "_session_recap", lambda m, ranked, picks: {"session_date": "2026-10-23", "rows": []})
    r = TestClient(main.app).get("/api/plan/checkpoint?market=IDX").json()
    assert r["live"] is False and r["recap"]["session_date"] == "2026-10-23"
