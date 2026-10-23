"""Entry / cut loss / take profit levels respect exchange ticks and real structure (offline)."""
import math

import numpy as np
import pandas as pd
import pytest

from engine.screener.trade_levels import compute_trade_levels, round_to_tick, tick_size


@pytest.mark.parametrize("price,tick", [(150, 1), (199, 1), (200, 2), (499, 2), (500, 5), (1999, 5),
                                        (2000, 10), (4990, 10), (5000, 25), (23825, 25)])
def test_idx_tick_bands(price, tick):
    assert tick_size(price, "IDX") == tick


def test_round_to_tick_modes_and_boundaries():
    assert round_to_tick(2855.74, "IDX", "down") == 2850
    assert round_to_tick(2855.74, "IDX", "up") == 2860
    assert round_to_tick(3644.83, "IDX", "down") == 3640
    assert round_to_tick(5012.0, "IDX", "down") == 5000
    assert round_to_tick(2001.0, "IDX", "down") == 2000
    assert round_to_tick(1999.0, "IDX", "up") == 2000
    assert round_to_tick(187.456, "US", "down") == 187.45


def _on_tick(v, market="IDX"):
    t = tick_size(v, market)
    return math.isclose(v / t, round(v / t), abs_tol=1e-6)


def frame(path, start=1000.0, seed=1, vol=0.006):
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(np.asarray(path) + rng.normal(0, vol, len(path))))
    open_ = np.concatenate([[start], close[:-1]])
    spread = np.abs(rng.normal(0, vol, len(path))) * close + close * 0.003
    return pd.DataFrame({"date": pd.bdate_range("2025-01-01", periods=len(path)), "open": open_,
                         "high": np.maximum(open_, close) + spread, "low": np.minimum(open_, close) - spread,
                         "close": close, "volume": 1e6})


PATHS = {
    "uptrend_dip": [0.003] * 200 + [-0.004] * 6,
    "downtrend": [-0.003] * 206,
    "range": list(np.sin(np.linspace(0, 12 * np.pi, 206)) * 0.01),
    "extended": [0.002] * 190 + [0.02] * 16,
}


@pytest.mark.parametrize("name", list(PATHS))
@pytest.mark.parametrize("start", [150.0, 450.0, 1400.0, 3000.0, 9000.0])
def test_levels_ordered_and_on_ticks(name, start):
    for seed in range(4):
        lv = compute_trade_levels(frame(PATHS[name], start=start, seed=seed), "IDX")
        assert lv["stop_loss"] < lv["entry_low"] <= lv["recommended_entry"] <= lv["entry_high"] < lv["target_tp1"] < lv["target_tp2"], lv
        assert lv["entry_high"] <= lv["price"] + 1e-9  # never above the market outside a breakout
        for k in ("entry_low", "entry_high", "recommended_entry", "stop_loss", "target_tp1", "target_tp2"):
            assert _on_tick(lv[k]), (k, lv[k])
        risk = lv["recommended_entry"] - lv["stop_loss"]
        assert risk <= 0.08 * lv["recommended_entry"] + tick_size(lv["recommended_entry"]) + 1e-9
        assert lv["risk_per_lot"] == pytest.approx(risk * 100, abs=1)


def test_tp1_is_the_nearest_resistance_not_an_inflated_projection():
    df = frame(PATHS["range"], start=3000.0, seed=2)
    lv = compute_trade_levels(df, "IDX")
    if "projected_tp1" not in lv["flags"]:
        assert lv["tp1_basis"].startswith("resistance ")
    assert lv["risk_reward_ratio"] == pytest.approx(
        (lv["target_tp1"] - lv["recommended_entry"]) / (lv["recommended_entry"] - lv["stop_loss"]), abs=0.01)
    if lv["risk_reward_ratio"] < 1.2:
        assert "tight_room" in lv["flags"]


def test_breakout_entry_retests_broken_level():
    df = frame(PATHS["extended"], start=1000.0, seed=3)
    prev_high = float(df["high"].iloc[-21:-1].max())
    lv = compute_trade_levels(df, "IDX", is_breakout=True, breakout_level=prev_high)
    assert "retest" in lv["entry_basis"]
    assert lv["entry_low"] >= round_to_tick(prev_high, "IDX", "down") - tick_size(prev_high)


def test_us_market_uses_cents():
    lv = compute_trade_levels(frame(PATHS["uptrend_dip"], start=180.0, seed=4), "US")
    assert lv["tick"] == 0.01 and lv["risk_per_lot"] is None
    assert _on_tick(lv["target_tp1"], "US")


def test_basis_names_the_level_actually_used():
    from engine.screener.trade_levels import zone_label
    zone = {"bottom": 1319.0, "top": 1370.0, "items": [
        {"price": 1319.0, "source": "puncak swing"}, {"price": 1370.0, "source": "EMA20"}]}
    assert zone_label(zone, "top") == "1.370 (EMA20)"
    assert zone_label(zone, "bottom") == "1.319 (puncak swing)"


def test_levels_name_the_close_they_stand_on():
    df = frame([0.002] * 160)
    lv = compute_trade_levels(df, "IDX")
    assert lv["as_of"] == str(df["date"].iloc[-1])[:10]
    assert lv["bar_final"] is True            # a 2025 bar is long settled
    assert lv["computed_at"]


def test_bar_is_final_follows_the_exchange_clock():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from engine.collectors.data_quality import bar_is_final
    wib = ZoneInfo("Asia/Jakarta")
    wed = "2026-10-21"
    assert bar_is_final(wed, "IDX", datetime(2026, 10, 21, 14, 0, tzinfo=wib)) is False   # session live
    assert bar_is_final(wed, "IDX", datetime(2026, 10, 21, 16, 20, tzinfo=wib)) is False  # still settling
    assert bar_is_final(wed, "IDX", datetime(2026, 10, 21, 17, 0, tzinfo=wib)) is True
    assert bar_is_final("2026-10-23", "IDX", datetime(2026, 10, 24, 10, 0, tzinfo=wib)) is True  # Fri bar on Sat
    assert bar_is_final(None, "IDX") is None


def test_plan_is_frozen_while_the_session_trades(monkeypatch):
    from engine.indicators import technical
    from engine.collectors import data_quality
    df = frame([0.002] * 160)
    final_plan = technical.compute_technical_indicators(df.iloc[:-1], "IDX")["levels"]
    # Pretend today's (last) bar is still trading
    today = str(df["date"].iloc[-1])[:10]
    monkeypatch.setattr(data_quality, "bar_is_final", lambda d, m="IDX", now=None: str(d)[:10] != today)
    tech = technical.compute_technical_indicators(df, "IDX")
    lv = tech["levels"]
    assert lv["frozen"] is True and lv["as_of"] == final_plan["as_of"]
    for k in ("entry_low", "entry_high", "stop_loss", "target_tp1", "target_tp2"):
        assert lv[k] == final_plan[k]
    assert lv["live"]["date"] == today and lv["live"]["price"] == round(float(df["close"].iloc[-1]), 2)
    assert tech["entry_low"] == final_plan["entry_low"]


def test_plan_position_follows_the_opening_rules():
    from engine.screener.trade_levels import plan_position
    lv = {"entry_low": 2930, "entry_high": 3020, "stop_loss": 2790, "target_tp1": 3150, "target_tp2": 3400}
    assert plan_position(lv, 3060)["status"] == "ABOVE_ZONE"
    assert plan_position(lv, 2980)["status"] == "IN_ZONE"
    assert plan_position(lv, 2850)["status"] == "TESTING_SUPPORT"
    assert plan_position(lv, 2790)["status"] == "BELOW_STOP"
    assert plan_position(lv, 3160)["status"] == "AT_TP1"
    assert plan_position(lv, 3400)["status"] == "AT_TP2"
    p = plan_position(lv, 2980, high=3155, low=2780)
    assert p["touched_stop"] and p["touched_tp1"]


def test_ladder_and_too_volatile_flag():
    import numpy as np
    df = frame([0.002] * 160)
    lv = compute_trade_levels(df, "IDX")
    lad = lv["ladder"]
    assert set(lad) == {"supports", "resistances"} and len(lad["supports"]) <= 3 and len(lad["resistances"]) <= 3
    assert all(s["price"] < lv["price"] for s in lad["supports"]) and all(r["price"] > lv["price"] for r in lad["resistances"])
    assert all(_on_tick(x["price"]) for x in lad["supports"] + lad["resistances"])
    # a stock moving ~12% a day: the 8% cap leaves the stop inside one ATR
    wild = frame(list(np.random.default_rng(3).normal(0, 0.12, 160)), vol=0.08)
    lw = compute_trade_levels(wild, "IDX")
    assert "wide_stop" in lw["flags"] and "too_volatile" in lw["flags"]
    assert lw["recommended_entry"] - lw["stop_loss"] < lw["atr14"]


def test_target_touched_earlier_today_still_counts():
    from engine.screener.trade_levels import plan_position
    lv = {"entry_low": 366, "entry_high": 376, "stop_loss": 340, "target_tp1": 384, "target_tp2": 408}
    p = plan_position(lv, 382, high=386, low=376)          # SMDR 23 Oct: high 386, now 382
    assert p["status"] == "AT_TP1" and "386" in p["label"] and p["touched_tp1"]
    assert plan_position(lv, 382, high=383, low=376)["status"] == "ABOVE_ZONE"
    assert plan_position(lv, 400, high=410, low=380)["status"] == "AT_TP2"
    # stop touched too: order unknown → judged by the current price, with the stop noted
    both = plan_position(lv, 382, high=386, low=338)
    assert both["status"] == "ABOVE_ZONE" and both["touched_stop"]
    assert plan_position(lv, 339, high=386, low=338)["status"] == "BELOW_STOP"


def test_capped_stop_never_exceeds_the_risk_cap():
    import numpy as np
    for seed in range(40):
        sd = 0.02 + 0.06 * (seed % 4) / 3
        wild = frame(list(np.random.default_rng(seed).normal(0, sd, 160)), start=float(60 + seed * 137), vol=0.05)
        lv = compute_trade_levels(wild, "IDX")
        assert _on_tick(lv["stop_loss"])
        if lv["risk_pct"] > 8.0 + 1e-9:
            # only when the entry zone itself is wider than the cap: one tick under the zone, said so
            assert lv["stop_loss"] == lv["entry_low"] - tick_size(lv["entry_low"], "IDX"), (seed, lv["risk_pct"])
            assert "wide_stop" in lv["flags"] and "lebih lebar dari batas risiko" in lv["stop_basis"]
            assert "dibatasi risiko maks" not in lv["stop_basis"]
