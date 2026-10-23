"""Executable-plan simulation: fill at the entry limit first, then stop or target (offline)."""
from engine.screener.plan_sim import simulate_plan, summarize_sims
from engine.screener.predictions import evaluate_item, summarize_evaluations

PLAN = {"recommended_entry": 950, "entry_low": 925, "entry_high": 980, "stop_loss": 870,
        "target_tp1": 1040, "target_tp2": 1280}


def bars(*ohlc, start=1):
    return [{"date": f"2026-11-{start + i:02d}", "open": o, "high": h, "low": lo, "close": c}
            for i, (o, h, lo, c) in enumerate(ohlc)]


def test_never_reaching_the_limit_is_not_filled():
    b = bars(*[(1000, 1020, 990, 1010)] * 5)
    out = simulate_plan(PLAN, b)
    assert out["status"] == "NOT_FILLED" and not out["filled"] and not out["touched_zone"]
    assert simulate_plan(PLAN, b[:3])["status"] == "PENDING"


def test_fill_then_target():
    b = bars((1000, 1005, 945, 960), (960, 1000, 955, 990), (990, 1045, 985, 1030))
    out = simulate_plan(PLAN, b, after_tp1="exit")
    assert out["filled"] and out["fill_price"] == 950 and out["days_to_fill"] == 1
    assert out["status"] == "HIT_TP1" and out["exit_price"] == 1040
    assert out["r"] == round((1040 - 950) / (950 - 870), 3)


def test_gap_below_limit_fills_at_open_and_stop_first():
    b = bars((940, 945, 930, 935), (900, 905, 860, 870))
    out = simulate_plan(PLAN, b)
    assert out["fill_price"] == 940
    assert out["status"] == "STOPPED_OUT" and out["exit_price"] == 870   # open 900 > stop: exit at the stop
    gap = simulate_plan(PLAN, bars((940, 945, 930, 935), (850, 860, 840, 845)))
    assert gap["exit_price"] == 850                                     # gap below the stop: exit at the open


def test_opening_below_the_stop_before_filling_cancels_the_plan():
    out = simulate_plan(PLAN, bars((1000, 1000, 990, 995), (860, 870, 850, 860)))
    assert out["status"] == "CANCELLED" and not out["filled"]


def test_bar_touching_both_counts_as_stop_and_fill_bar_ignores_tp():
    out = simulate_plan(PLAN, bars((960, 1050, 940, 1000)))           # fill bar reaches TP1: not counted
    assert out["status"] == "IN_PROGRESS"
    both = simulate_plan(PLAN, bars((960, 970, 945, 950), (950, 1050, 860, 900)))
    assert both["status"] == "STOPPED_OUT"


def test_expiry_and_summary():
    b = bars((955, 960, 948, 955), *[(955, 990, 940, 960)] * 10)
    out = simulate_plan(PLAN, b, horizon=10)
    assert out["status"] == "EXPIRED" and out["exit_price"] == 960
    s = summarize_sims([out, {"status": "NOT_FILLED", "filled": False},
                        simulate_plan(PLAN, bars((1000, 1005, 945, 960), (960, 1045, 955, 1030)), after_tp1="exit")])
    assert s["decided"] == 3 and s["filled"] == 2 and s["fill_rate_pct"] == 66.7
    assert s["win_rate_pct"] == 50.0 and s["hit_tp1"] == 1


def test_prediction_with_entry_zone_is_evaluated_as_a_plan():
    item = {"ticker": "VICI.JK", "snapshot_date": "2026-10-31", "price_at_prediction": 1000, **PLAN}
    candles = [{"date": "2026-10-31", "open": 990, "high": 1010, "low": 985, "close": 1000}] + \
        bars(*[(1000, 1020, 990, 1010)] * 5)
    ev = evaluate_item(item, candles, horizon=10)
    assert ev["plan_checked"] and ev["status"] == "NOT_FILLED" and ev["return_pct"] == 0.0
    # half sold at TP1, the other half stopped at the buy price
    filled = evaluate_item(item, candles[:1] + bars((1000, 1005, 945, 960), (960, 1045, 955, 1030),
                                                    (1000, 1000, 940, 945)), horizon=10)
    assert filled["status"] == "HIT_TP1" and filled["fill_price"] == 950 and filled["r_multiple"] > 0
    summ = summarize_evaluations([ev, filled], 10)
    assert summ["not_filled_count"] == 1 and summ["win_rate_pct"] == 100.0 and summ["fill_rate_pct"] == 50.0


def test_old_snapshot_without_zone_keeps_the_legacy_rule():
    item = {"ticker": "BBCA.JK", "snapshot_date": "2026-10-31", "price_at_prediction": 1000,
            "stop_loss": 900, "target_tp1": 1100, "target_tp2": 1200, "recommended_entry": 0}
    ev = evaluate_item(item, bars((1000, 1110, 990, 1100)), horizon=10)
    assert ev["plan_checked"] is False and ev["status"] == "HIT_TP1"


def test_tp1_exits_and_a_later_tp2_does_not_upgrade_the_trade():
    # fill, TP1, then a drop through the stop, then TP2: the old simulator counted this as TP2
    b = bars((1000, 1005, 945, 960), (960, 1045, 955, 1030), (1000, 1000, 860, 870), (900, 1300, 900, 1290))
    out = simulate_plan(PLAN, b, after_tp1="exit")
    assert out["status"] == "HIT_TP1" and out["exit_price"] == 1040 and out["bars_held"] == 2
    # default policy: the half kept after TP1 is stopped at the buy price, never upgraded past the stop
    out = simulate_plan(PLAN, b)
    assert out["status"] == "HIT_TP1" and out["exit_price"] == (1040 + 950) / 2


def test_gap_above_tp1_sells_at_the_open():
    out = simulate_plan(PLAN, bars((1000, 1005, 945, 960), (1060, 1070, 1050, 1065)), after_tp1="exit")
    assert out["status"] == "HIT_TP1" and out["exit_price"] == 1060
    still_open = simulate_plan(PLAN, bars((1000, 1005, 945, 960), (1060, 1070, 1050, 1065)))
    assert still_open["status"] == "IN_PROGRESS" and still_open["open_r"] > 0   # second half still running


def test_half_breakeven_policy():
    tp1_then_be = bars((1000, 1005, 945, 960), (960, 1045, 955, 1030), (1000, 1000, 940, 945))
    out = simulate_plan(PLAN, tp1_then_be, after_tp1="half_breakeven")
    assert out["status"] == "HIT_TP1" and out["exit_price"] == (1040 + 950) / 2
    tp1_then_tp2 = bars((1000, 1005, 945, 960), (960, 1045, 955, 1030), (1100, 1290, 1090, 1280))
    out = simulate_plan(PLAN, tp1_then_tp2, after_tp1="half_breakeven")
    assert out["status"] == "HIT_TP2" and out["exit_price"] == (1040 + 1280) / 2
    # the stop is never moved before TP1
    stopped = simulate_plan(PLAN, bars((1000, 1005, 945, 960), (950, 960, 860, 870)), after_tp1="half_breakeven")
    assert stopped["status"] == "STOPPED_OUT"
