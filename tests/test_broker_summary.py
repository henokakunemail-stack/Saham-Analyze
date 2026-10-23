"""Broker registry, bandarmologi math and the proxy/cache path (temp DB, offline)."""
from engine.screener.broker_summary import (
    BROKER_REGISTRY,
    evaluate_bandarmologi,
    fetch_and_evaluate_broker_summary
)
from engine.db import get_cached_broker_summary


def test_registry():
    assert BROKER_REGISTRY["AK"]["type"] == "FOREIGN"
    assert BROKER_REGISTRY["CC"]["type"] == "DOMESTIC_INSTITUTION"
    assert BROKER_REGISTRY["YP"]["type"] == "RETAIL"


def test_bandarmologi_big_accumulation():
    buyers = [
        {"broker": "AK", "name": "UBS", "type": "FOREIGN", "bval": 50_000_000_000, "bvol": 5_000_000},
        {"broker": "BK", "name": "JPMorgan", "type": "FOREIGN", "bval": 30_000_000_000, "bvol": 3_000_000},
        {"broker": "CC", "name": "Mandiri", "type": "DOMESTIC_INSTITUTION", "bval": 20_000_000_000, "bvol": 2_000_000},
    ]
    sellers = [
        {"broker": "YP", "name": "Mirae", "type": "RETAIL", "sval": 15_000_000_000, "svol": 1_500_000},
        {"broker": "XC", "name": "Ajaib", "type": "RETAIL", "sval": 10_000_000_000, "svol": 1_000_000},
        {"broker": "PD", "name": "IPOT", "type": "RETAIL", "sval": 8_000_000_000, "svol": 800_000},
    ]
    res = evaluate_bandarmologi(top_buyers=buyers, top_sellers=sellers, current_price=10000.0)
    assert res["bandar_status"] == "BIG_ACCUM"
    assert res["top3_ratio"] >= 2.0
    assert res["bandar_avg_price"] > 0
    assert res["summary_notes"]


def test_no_provider_key_returns_no_data_and_caches_nothing(monkeypatch):
    from engine.screener import broker_summary
    monkeypatch.setattr(broker_summary, "get_setting", lambda key, default="": "")
    res = fetch_and_evaluate_broker_summary(
        ticker="NOKEY.JK", market="IDX", current_price=10200.0, cmf20=0.22,
        vol_ratio=1.8, change_pct=1.5, vsa_signal="ACCUMULATION"
    )
    assert res["data_available"] is False
    assert not res["top_buyers"]
    assert get_cached_broker_summary("NOKEY.JK") is None


def test_provider_rows_are_evaluated_and_cached(monkeypatch):
    # The session shares one temp DB: use a ticker no other test reads

    from engine.screener import broker_summary
    buyers = [{"broker": b, "name": b, "type": BROKER_REGISTRY.get(b, {}).get("type", "RETAIL"),
               "bval": v * 1e9, "bvol": v * 1e5} for b, v in (("AK", 50), ("BK", 30), ("CC", 20), ("KZ", 10), ("ZP", 5))]
    sellers = [{"broker": b, "name": b, "type": "RETAIL", "sval": v * 1e9, "svol": v * 1e5}
               for b, v in (("YP", 15), ("XC", 10), ("PD", 8), ("CP", 5), ("NI", 3))]
    monkeypatch.setattr(broker_summary, "get_setting", lambda key, default="": "dummy-key")
    monkeypatch.setattr(broker_summary, "fetch_from_sectors_app",
                        lambda t, k: {"top_buyers": buyers, "top_sellers": sellers, "source": "SECTORS_APP"})
    res = fetch_and_evaluate_broker_summary(
        ticker="TQBROKER.JK", market="IDX", current_price=10200.0, cmf20=0.22,
        vol_ratio=1.8, change_pct=1.5, vsa_signal="ACCUMULATION", force_refresh=True
    )
    assert res["data_available"] is True
    assert len(res["top_buyers"]) == 5 and len(res["top_sellers"]) == 5
    assert res["bandar_avg_price"] > 0
    cached = get_cached_broker_summary("TQBROKER.JK")
    assert cached is not None and cached["ticker"] == "TQBROKER.JK"
