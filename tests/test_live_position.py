"""Today's price against a frozen plan: far-above detection, ranking tiers, the live reading overlay."""
from engine.screener.actionability import rank_key, today_tier
from engine.screener.pipeline import live_reading
from engine.screener.trade_levels import plan_position

LV = {"entry_low": 4700, "entry_high": 4790, "recommended_entry": 4740, "stop_loss": 4450,
      "target_tp1": 4910, "target_tp2": 5200, "atr14": 100.0}


def test_far_above_zone_is_flagged_and_measured():
    near = plan_position(LV, 4850, high=4860, low=4800)        # 0.6 ATR above the zone
    assert near["status"] == "ABOVE_ZONE" and not near["far_above"] and near["dist_atr"] == 0.6
    assert near["buyable_today"] is True
    far = plan_position(LV, 4900, high=4905, low=4880)         # 1.1 ATR above, still under TP1
    assert far["status"] == "ABOVE_ZONE" and far["far_above"] and "1.1×ATR" in far["label"]
    assert far["buyable_today"] is True
    assert plan_position(LV, 4750, high=4760, low=4740)["dist_atr"] == 0.0


def test_buyable_today_false_once_the_plan_is_settled():
    assert plan_position(LV, 4940, high=4950, low=4900)["buyable_today"] is False     # at TP1
    assert plan_position(LV, 4400, high=4500, low=4390)["buyable_today"] is False     # below stop
    dipped = plan_position(LV, 4750, high=4760, low=4440)                             # touched the stop, came back
    assert dipped["touched_stop"] and dipped["buyable_today"] is False


def _row(t, raw, live=None):
    lv = {**LV, "risk_pct": 5, "risk_reward_ratio": 1.5, "flags": []}
    if live:
        lv.update(frozen=True, live=live)
    return {"ticker": t, "raw_score": raw, "score": raw, "action": {"status": "TUNGGU"}, "levels": lv}


def test_rank_tiers_follow_executability_today():
    rows = [_row("ATTP", 95, plan_position(LV, 4940, 4950, 4900)),
            _row("FAR", 94, plan_position(LV, 4900, 4905, 4880)),
            _row("NEAR", 70, plan_position(LV, 4850, 4860, 4800)),
            _row("ZONE", 65, plan_position(LV, 4750, 4760, 4740)),
            _row("FRESH", 60)]                                     # closing scan: no live data
    assert [today_tier(r["levels"]) for r in rows] == [2, 1, 0, 0, 0]
    assert [r["ticker"] for r in sorted(rows, key=rank_key)] == ["NEAR", "ZONE", "FRESH", "FAR", "ATTP"]


def test_live_reading_overrides_yesterdays_trigger_text():
    base = {"stance": "TUNGGU_PEMICU", "headline": "Pullback sehat dan pemicu sudah muncul.", "triggers": []}
    at_tp = live_reading(base, {**LV, "frozen": True, "live": plan_position(LV, 4940, 4950, 4900)})
    assert at_tp["stance"] == "LEWAT" and "TP1" in at_tp["headline"] and at_tp["base_stance"] == "TUNGGU_PEMICU"
    broken = live_reading(base, {**LV, "frozen": True, "live": plan_position(LV, 4400, 4500, 4390)})
    assert broken["stance"] == "BATAL"
    far = live_reading(base, {**LV, "frozen": True, "live": plan_position(LV, 4900, 4905, 4880)})
    assert far["stance"] == "JANGAN_KEJAR" and "1.1×ATR" in far["headline"]
    # inside the zone, or after the close (plan not frozen): the reading is untouched
    assert live_reading(base, {**LV, "frozen": True, "live": plan_position(LV, 4750, 4760, 4740)}) is base
    assert live_reading(base, {**LV, "live": plan_position(LV, 4940, 4950, 4900)}) is base
    assert base["stance"] == "TUNGGU_PEMICU"
