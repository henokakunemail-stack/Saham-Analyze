"""Actionability gates: LAYAK / TUNGGU / HINDARI, reasons and the ranking key (offline)."""
import copy

from engine.screener.actionability import assess, rank_key, stock_signal_score


def make_row(**over):
    row = {
        "ticker": "BBCA.JK", "market": "IDX", "verdict": "MILD_BULLISH", "is_speculative": False,
        "market_mode": "NORMAL", "score": 70, "raw_score": 70,
        "pillar_values": {"pullback": 0.6, "trend": 0.5, "money_flow": 0.2, "momentum": 0.1, "setup": 0.1},
        "pullback_state": "PULLBACK_IDEAL",
        "levels": {"risk_pct": 5.0, "risk_reward_ratio": 1.4, "flags": [], "as_of": "2026-10-22"},
        "screen": {"avg_value_20d": 50e9, "illiquid": False, "rs_60d": 8.0, "atr_pct": 2.5},
    }
    for k, v in over.items():
        row[k] = v
    return row


def with_levels(**lv):
    row = make_row()
    row["levels"] = {**row["levels"], **lv}
    return row


def with_screen(**sc):
    row = make_row()
    row["screen"] = {**row["screen"], **sc}
    return row


def test_all_gates_pass_is_layak():
    out = assess(make_row())
    assert out["status"] == "LAYAK"
    assert out["reasons"] == []
    assert set(out["gates"]) == {"market_ok", "signal_ok", "risk_ok", "vol_ok", "liquid_ok", "data_ok"}
    assert all(out["gates"].values())


def test_market_gate():
    crash = assess(make_row(market_mode="CRASH", verdict="NEUTRAL"))
    assert crash["status"] == "TUNGGU" and not crash["gates"]["market_ok"]
    assert "Pasar krisis — tahan pembelian" in crash["reasons"]
    # BEARISH: leaders only (clean uptrend states)
    assert assess(make_row(market_mode="BEARISH"))["gates"]["market_ok"]
    laggard = assess(make_row(market_mode="BEARISH", pullback_state="PULLBACK_DEEP"))
    assert not laggard["gates"]["market_ok"] and laggard["status"] == "TUNGGU"
    assert assess(make_row(market_mode="CAUTIOUS"))["gates"]["market_ok"]
    # Variants used by calibration
    strict = {"blocked_modes": ("CRASH", "BEARISH"), "leaders_only_modes": ()}
    assert not assess(make_row(market_mode="BEARISH"), strict)["gates"]["market_ok"]
    lenient = {"blocked_modes": (), "leaders_only_modes": ("CRASH", "BEARISH")}
    assert assess(make_row(market_mode="CRASH"), lenient)["gates"]["market_ok"]


def test_signal_gate():
    neutral = assess(make_row(verdict="NEUTRAL", score=60))
    assert not neutral["gates"]["signal_ok"] and neutral["status"] == "TUNGGU"
    assert "Belum ada sinyal beli (vonis Netral)" in neutral["reasons"]
    spec = assess(make_row(is_speculative=True))
    assert not spec["gates"]["signal_ok"] and spec["status"] == "TUNGGU"
    assert assess(make_row(verdict="STRONG_BULLISH"))["gates"]["signal_ok"]


def test_signal_raw_basis_ignores_market_brake_but_keeps_stock_caps():
    raw = {"signal_basis": "raw"}
    # Final verdict neutral only because of the market brake: the stock's own score is bullish
    braked = make_row(market_mode="CAUTIOUS", verdict="NEUTRAL", score=60, raw_score=70)
    assert not assess(braked)["gates"]["signal_ok"]
    assert assess(braked, raw)["gates"]["signal_ok"]
    # Overheated uptrend and strong downtrend caps still apply
    ext = make_row(verdict="NEUTRAL", score=64, raw_score=75, pullback_state="UPTREND_EXTENDED")
    assert stock_signal_score(ext) == 64 and not assess(ext, raw)["gates"]["signal_ok"]
    down = make_row(verdict="NEUTRAL", raw_score=72, pillar_values={"trend": -0.6})
    assert stock_signal_score(down) == 55
    out = assess(down, raw)
    assert not out["gates"]["signal_ok"] and "Belum ada sinyal beli (skor saham 55 < 65)" in out["reasons"]


def test_risk_gate():
    out = assess(with_levels(risk_pct=7.2))
    assert not out["gates"]["risk_ok"] and out["status"] == "TUNGGU"
    assert "Risiko 7,2% > batas 6%" in out["reasons"]
    assert assess(with_levels(risk_pct=6.0))["gates"]["risk_ok"]
    out = assess(with_levels(risk_pct=9.2), {"max_risk_pct": 8.0})
    assert not out["gates"]["risk_ok"] and "Risiko 9,2% > batas 8%" in out["reasons"]
    assert assess(with_levels(risk_pct=7.0), {"max_risk_pct": 8.0})["gates"]["risk_ok"]
    no_plan = make_row(levels=None)
    out = assess(no_plan)
    assert not out["gates"]["risk_ok"] and "Rencana harga belum tersedia" in out["reasons"]


def test_volatility_gate():
    out = assess(with_levels(flags=["wide_stop", "too_volatile"]))
    assert not out["gates"]["vol_ok"] and out["status"] == "TUNGGU"
    assert out["reasons"][0].startswith("Terlalu volatil untuk jarak cut loss ini")
    # tight_room / wide_stop alone are information, not a gate
    assert assess(with_levels(flags=["tight_room", "wide_stop"]))["status"] == "LAYAK"
    assert assess(with_levels(flags=["too_volatile"]), {"require_not_volatile": False})["gates"]["vol_ok"]


def test_liquidity_gate():
    out = assess(with_screen(avg_value_20d=1.5e9))
    assert not out["gates"]["liquid_ok"] and "Kurang likuid (Rp1,5 M/hari)" in out["reasons"]
    assert assess(with_screen(avg_value_20d=2.1e9))["gates"]["liquid_ok"]
    out = assess(with_screen(avg_value_20d=2.1e9), {"min_value_idx": 5e9})
    assert not out["gates"]["liquid_ok"] and "Kurang likuid (Rp2,1 M/hari)" in out["reasons"]
    assert "Kurang likuid (Rp650 jt/hari)" in assess(with_screen(avg_value_20d=6.5e8))["reasons"]
    us = make_row(market="US")
    us["screen"] = {**us["screen"], "avg_value_20d": 15e6}
    out = assess(us)
    assert not out["gates"]["liquid_ok"] and "Kurang likuid (US$15 jt/hari)" in out["reasons"]
    us["screen"]["avg_value_20d"] = 25e6
    assert assess(us)["gates"]["liquid_ok"]


def test_data_gate_and_missing_abnormal_days():
    assert assess(make_row())["gates"]["data_ok"]                       # key missing: no known issue
    assert assess(make_row(abnormal_recent=[]))["gates"]["data_ok"]
    limit = make_row(abnormal_recent=[{"date": "2026-10-21", "kind": "LIMIT_DOWN", "label": "ARB"}])
    out = assess(limit)
    assert not out["gates"]["data_ok"] and out["status"] == "TUNGGU"
    assert "Ada ARB 21 Okt — tunggu stabil" in out["reasons"]
    # Older than 3 trading days (as_of 22 Okt): no longer blocking
    old = make_row(abnormal_recent=[{"date": "2026-10-16", "kind": "LIMIT_DOWN"}])
    assert assess(old)["gates"]["data_ok"]
    # Upper-limit days do not block
    up = make_row(abnormal_recent=[{"date": "2026-10-22", "kind": "LOCK_UP"}])
    assert assess(up)["status"] == "LAYAK"


def test_hindari_precedence():
    bear = assess(make_row(verdict="MILD_BEARISH", score=40))
    assert bear["status"] == "HINDARI" and bear["reasons"][0] == "Vonis Tekanan jual — sinyal jual"
    below = with_levels(live={"status": "BELOW_STOP"})
    out = assess(below)
    assert out["status"] == "HINDARI" and out["reasons"][0].startswith("Harga sudah di bawah cut loss")
    locked = make_row(abnormal_recent=[{"date": "2026-10-20", "kind": "LOCK_DOWN"},
                                       {"date": "2026-10-01", "kind": "LOCK_UP"}])
    out = assess(locked)
    assert out["status"] == "HINDARI" and "Ada ARB 20 Okt — tunggu stabil" in out["reasons"]
    # Even when every other gate fails, HINDARI wins over TUNGGU
    worst = make_row(verdict="STRONG_BEARISH", market_mode="CRASH")
    worst["screen"] = {"avg_value_20d": 1e8}
    assert assess(worst)["status"] == "HINDARI"


def test_no_date_falls_back_to_last_three_entries():
    row = make_row(abnormal_recent=[{"date": f"2026-09-{d:02d}", "kind": k}
                                    for d, k in ((1, "LOCK_DOWN"), (10, "LOCK_UP"), (11, "LOCK_UP"), (12, "LOCK_UP"))])
    row["levels"] = {k: v for k, v in row["levels"].items() if k != "as_of"}
    assert assess(row)["status"] == "LAYAK"                     # the LOCK_DOWN is the 4th newest
    row["abnormal_recent"].append({"date": "2026-09-13", "kind": "SUSPENSION_GAP"})
    out = assess(row)
    assert out["status"] == "TUNGGU" and "Ada suspensi 13 Sep — tunggu stabil" in out["reasons"]


def test_rank_key_ordering():
    layak_low = make_row(ticker="A", raw_score=66, score=66)
    layak_high = make_row(ticker="B", raw_score=80, score=70)
    tunggu_top = make_row(ticker="C", raw_score=95, score=90, verdict="NEUTRAL")
    hindari = make_row(ticker="D", raw_score=99, score=40, verdict="MILD_BEARISH")
    # Ties on raw_score: score, then R:R, then liquidity decide
    tie_a = make_row(ticker="E", raw_score=70, score=68)
    tie_b = make_row(ticker="F", raw_score=70, score=68)
    tie_b["levels"] = {**tie_b["levels"], "risk_reward_ratio": 2.0}
    tie_c = copy.deepcopy(tie_a)
    tie_c["ticker"] = "G"
    tie_c["screen"]["avg_value_20d"] = 90e9
    rows = [hindari, tunggu_top, layak_low, tie_a, layak_high, tie_b, tie_c]
    order = [r["ticker"] for r in sorted(rows, key=rank_key)]
    assert order == ["B", "F", "G", "E", "A", "C", "D"]
    # A precomputed action wins; missing numbers sort last within their status
    pre = make_row(ticker="H", action={"status": "HINDARI"})
    blank = make_row(ticker="I", raw_score=None, score=None)
    assert [r["ticker"] for r in sorted([pre, blank, layak_low], key=rank_key)] == ["A", "I", "H"]



def test_plan_whose_target_is_already_hit_today_waits():
    out = assess(with_levels(frozen=True, live={"status": "AT_TP1", "price": 1}))
    assert out["status"] == "TUNGGU" and "TP1" in out["reasons"][0]
    assert assess(with_levels(frozen=True, live={"status": "IN_ZONE", "price": 1}))["status"] == "LAYAK"


def test_rank_puts_plans_missed_today_below_buyable_ones():
    from engine.screener.actionability import rank_key

    def row(t, raw, live_status=None, touched_stop=False):
        lv = {"risk_pct": 5, "risk_reward_ratio": 1.5, "flags": []}
        if live_status:
            lv.update(frozen=True, live={"status": live_status, "touched_stop": touched_stop})
        return {"ticker": t, "raw_score": raw, "score": raw, "action": {"status": "TUNGGU"}, "levels": lv}

    rows = [row("RAN", 90, "AT_TP1"), row("BROKE", 88, "BELOW_STOP", True), row("ZONE", 70, "IN_ZONE"),
            row("ABOVE", 75, "ABOVE_ZONE"), row("CLOSED", 72)]
    assert [r["ticker"] for r in sorted(rows, key=rank_key)] == ["ABOVE", "CLOSED", "ZONE", "RAN", "BROKE"]
