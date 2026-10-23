"""Cross-site guard, the shared analysis pipeline, scan finalization and fundamentals caching (offline)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from engine import main
from engine.db import get_fundamentals, get_screener_results, save_screener_result
from engine.screener import fundamentals, pipeline


def test_cross_site_requests_are_refused():
    client = TestClient(main.app)
    evil = {"sec-fetch-site": "cross-site", "origin": "https://evil.example"}
    assert client.get("/api/health", headers=evil).status_code == 403
    assert client.post("/api/settings", json={"model": "x"}, headers=evil).status_code == 403
    assert client.get("/api/health", headers={"sec-fetch-site": "same-origin"}).status_code == 200
    assert client.get("/api/health").status_code == 200          # non-browser clients send no header


def _frame(n=80, last="2026-10-23"):
    dates = pd.bdate_range(end=last, periods=n)
    close = [1000 + i for i in range(n)]
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "open": close, "high": [c + 5 for c in close],
                         "low": [c - 5 for c in close], "close": close, "volume": [1_000_000] * n})


def test_scoring_frame_drops_the_bar_still_trading(monkeypatch):
    df = _frame()
    monkeypatch.setattr(pipeline, "bar_is_final", lambda d, m: False)
    base, live = pipeline.scoring_frame(df, "IDX")
    assert live is True and len(base) == len(df) - 1 and base["date"].iloc[-1] == df["date"].iloc[-2]
    monkeypatch.setattr(pipeline, "bar_is_final", lambda d, m: True)
    base, live = pipeline.scoring_frame(df, "IDX")
    assert live is False and len(base) == len(df)


def test_reading_follows_the_action_status():
    reading = {"stance": "LAYAK_DIPERTIMBANGKAN", "headline": "Setup bagus"}
    out = pipeline.align_reading(reading, {"status": "HINDARI", "reasons": ["Risiko 9% > 6%"]})
    assert out["stance"] == "HINDARI" and out["headline"] == "Risiko 9% > 6%"
    out = pipeline.align_reading(reading, {"status": "TUNGGU", "reasons": ["Likuiditas rendah"]})
    assert out["stance"] == "TUNGGU_PEMICU" and "Likuiditas rendah" in out["headline"]
    out = pipeline.align_reading({"stance": "TUNGGU_PEMICU", "headline": "h"}, {"status": "LAYAK", "reasons": []})
    assert out["stance"] == "LAYAK_DIPERTIMBANGKAN" and "order limit di zona beli" in out["headline"]
    # LAYAK on a stock running without a discount: the headline says to wait for the zone, not "pantau"
    out = pipeline.align_reading({"stance": "PANTAU", "headline": "Tren naik berjalan tanpa diskon — pantau."},
                                 {"status": "LAYAK", "reasons": []})
    assert "jangan dikejar" in out["headline"] and out["base_stance"] == "PANTAU"
    kept = pipeline.align_reading({"stance": "LAYAK_DIPERTIMBANGKAN", "headline": "ok"}, {"status": "LAYAK", "reasons": []})
    assert kept["headline"] == "ok"
    assert reading["stance"] == "LAYAK_DIPERTIMBANGKAN"                 # input not mutated


def test_finalize_ranks_saves_and_drops_stale_rows(monkeypatch):
    monkeypatch.setattr(main.sectors, "annotate", lambda rows, m: None)
    monkeypatch.setattr(main.sectors, "refresh_async", lambda t, m: None)
    monkeypatch.setattr(main.market_breadth, "update_today", lambda m, t: None)
    save_screener_result({"ticker": "OLD.JK", "market": "IDX", "score": 99, "price": 1})
    rows = [{"ticker": "AAA.JK", "market": "IDX", "score": 50, "price": 1, "action": {"status": "TUNGGU"}},
            {"ticker": "BBB.JK", "market": "IDX", "score": 40, "price": 1, "action": {"status": "LAYAK"}}]
    main._finalize_rows(rows, "IDX")
    assert [r["ticker"] for r in rows] == ["BBB.JK", "AAA.JK"] and rows[0]["rank"] == 1
    assert {r["ticker"] for r in get_screener_results("IDX")} == {"AAA.JK", "BBB.JK"}


class _Ticker:
    def __init__(self, info):
        self.info = info


def test_fundamentals_keep_debt_to_equity_as_given(monkeypatch):
    info = {"returnOnEquity": 0.18, "profitMargins": 0.2, "debtToEquity": 32.1, "trailingPE": 12,
            "priceToBook": 2, "marketCap": 1e12}
    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda t: _Ticker(info))
    monkeypatch.setattr("engine.sectors._save", lambda *a, **k: None)
    out = fundamentals.fetch_and_evaluate_financials("ZZDE", "IDX", force_refresh=True)
    assert out["debt_to_equity"] == 32.1


def test_failed_fundamentals_fetch_is_not_cached_as_zeros(monkeypatch):
    monkeypatch.setattr(fundamentals.yf, "Ticker", lambda t: _Ticker({}))
    out = fundamentals.fetch_and_evaluate_financials("ZZNA", "IDX")
    assert out["unavailable"] is True and get_fundamentals("ZZNA.JK") is None
