"""Actionability: can this plan be executed today? LAYAK / TUNGGU / HINDARI.

The composite score says how good a stock looks; this module says whether the trade plan
built on it passes a few hard checks (market, signal, risk, volatility, liquidity, data).
- HINDARI: a bearish verdict, a live price already under the stop, or a locked limit-down
  (ARB) in the last 3 trading days.
- LAYAK: every gate passes.
- TUNGGU: anything else; the failed gates are the reasons.

Thresholds below were calibrated in-sample and checked once out-of-sample, see
docs/hasil-kalibrasi-fase1.md. R:R is shown but is not a gate: the baseline backtest gave the
same average R in every R:R bucket (docs/hasil-backtest-baseline.md).
"""
from datetime import date as _date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Modes in which nothing is bought: forced selling hits good and bad stocks alike
MARKET_BLOCKED_MODES: Tuple[str, ...] = ("CRASH",)
# Modes in which only leaders may be bought (baseline: BEARISH was the weakest mode, +0.04 R)
MARKET_LEADERS_ONLY_MODES: Tuple[str, ...] = ("BEARISH",)
# A "leader" holds a clean uptrend while the index is weak (same states scoring treats as leaders)
LEADER_STATES: Tuple[str, ...] = ("PULLBACK_IDEAL", "UPTREND_RUNNING")
# "verdict": the final verdict (after the market brake) must be bullish; "raw": the stock's own
# score (raw_score with the stock-specific caps) must reach SIGNAL_MIN_SCORE — the market is
# then judged by market_ok alone instead of twice
SIGNAL_BASIS = "verdict"
# Same line as MILD_BULLISH in scoring.compute_composite_score
SIGNAL_MIN_SCORE = 65
# Calibrated (Fase 1): only a 6 % cap made LAYAK > TUNGGU > HINDARI in-sample; 8 % / 10 % did not
MAX_RISK_PCT = 6.0
# The 8 % cap put the stop inside one day's normal range (redundant while MAX_RISK_PCT < 8, kept
# as a safety net: too_volatile plans always carry ~8 % risk)
REQUIRE_NOT_VOLATILE = True
# 20-day average traded value: below this a retail order moves the price / fills poorly.
# IDX calibrated (Rp2 M won in-sample, Rp5 M was within 0.003 R); US not calibrated (no US run)
MIN_VALUE_IDX = 2e9
MIN_VALUE_US = 20e6
# Minimum reward/risk to TP1 (Rugi : Untung). 0 = no condition. Candidate 1.2 = the existing
# "tight_room" line; under test in docs/hasil-akhir-fase1-5.md
MIN_RR = 0.0
# Abnormal bars that make the last prices unreliable for a fresh entry
DATA_BLOCK_KINDS: Tuple[str, ...] = ("LOCK_DOWN", "LIMIT_DOWN", "SUSPENSION_GAP")
# How many recent trading days an abnormal bar keeps blocking (and a LOCK_DOWN forces HINDARI)
DATA_LOOKBACK_DAYS = 3

BULLISH = ("MILD_BULLISH", "STRONG_BULLISH")
BEARISH = ("MILD_BEARISH", "STRONG_BEARISH")
STATUS_ORDER = {"LAYAK": 0, "TUNGGU": 1, "HINDARI": 2}

VERDICT_LABELS = {
    "STRONG_BULLISH": "Naik kuat", "MILD_BULLISH": "Naik awal", "NEUTRAL": "Netral",
    "MILD_BEARISH": "Tekanan jual", "STRONG_BEARISH": "Distribusi",
}
MODE_LABELS = {"CRASH": "krisis", "BEARISH": "bearish", "CAUTIOUS": "waspada", "NORMAL": "normal"}
ABNORMAL_LABELS = {"LOCK_DOWN": "ARB", "LIMIT_DOWN": "ARB", "SUSPENSION_GAP": "suspensi"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def default_config() -> Dict[str, Any]:
    """Current thresholds as one dict (calibration passes variants of it to assess)."""
    return {
        "blocked_modes": MARKET_BLOCKED_MODES,
        "leaders_only_modes": MARKET_LEADERS_ONLY_MODES,
        "leader_states": LEADER_STATES,
        "signal_basis": SIGNAL_BASIS,
        "signal_min_score": SIGNAL_MIN_SCORE,
        "max_risk_pct": MAX_RISK_PCT,
        "require_not_volatile": REQUIRE_NOT_VOLATILE,
        "min_value_idx": MIN_VALUE_IDX,
        "min_value_us": MIN_VALUE_US,
        "min_rr": MIN_RR,
        "data_block_kinds": DATA_BLOCK_KINDS,
        "data_lookback_days": DATA_LOOKBACK_DAYS,
    }


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _id(v: float, decimals: int = 1) -> str:
    """Indonesian number format: 9.2 -> "9,2", 8.0 -> "8"."""
    s = f"{v:.{decimals}f}".rstrip("0").rstrip(".") if decimals else f"{v:.0f}"
    return s.replace(".", ",")


def _money(v: float, market: str) -> str:
    if market == "US":
        return f"US${_id(v / 1e6)} jt/hari"
    if v >= 1e12:
        return f"Rp{_id(v / 1e12)} T/hari"
    if v >= 1e9:
        return f"Rp{_id(v / 1e9)} M/hari"
    return f"Rp{_id(v / 1e6)} jt/hari"


def _day_label(d: str) -> str:
    try:
        dt = _date.fromisoformat(str(d)[:10])
        return f"{dt.day} {MONTHS[dt.month - 1]}"
    except ValueError:
        return str(d)[:10]


def _ref_date(row: Dict[str, Any]) -> Optional[str]:
    """Newest bar the row knows about: today's live bar during the session (so a lock today
    counts), else the plan's own date."""
    lv = row.get("levels") or {}
    live_date = (lv.get("live") or {}).get("date")
    dates = [str(v)[:10] for v in (live_date, lv.get("as_of"), row.get("as_of"), row.get("date")) if v]
    return max(dates) if dates else None


def recent_abnormal(row: Dict[str, Any], kinds: Tuple[str, ...], days: int = DATA_LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """Abnormal bars of the given kinds in the last `days` trading days (newest first).

    abnormal_recent lists only abnormal bars, so "recent" is measured in business days from the
    plan's own date (levels.as_of); without a date the last `days` entries are used."""
    items = [a for a in (row.get("abnormal_recent") or []) if isinstance(a, dict) and a.get("date")]
    items.sort(key=lambda a: str(a["date"])[:10], reverse=True)
    ref = _ref_date(row)
    if ref:
        try:
            items = [a for a in items
                     if 0 <= int(np.busday_count(str(a["date"])[:10], ref)) < days]
        except ValueError:
            items = items[:days]
    else:
        items = items[:days]
    return [a for a in items if a.get("kind") in kinds]


def stock_signal_score(row: Dict[str, Any]) -> Optional[float]:
    """raw_score with the stock-specific caps from scoring (not the market brake)."""
    raw = _num(row.get("raw_score"))
    if raw is None:
        return None
    if row.get("pullback_state") == "UPTREND_EXTENDED":
        raw = min(raw, 64.0)
    trend = _num((row.get("pillar_values") or {}).get("trend"))
    if trend is not None and trend <= -0.5:
        raw = min(raw, 55.0)
    return raw


def assess(row: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Status, Indonesian reasons and pass/fail per gate for one scan result row."""
    cfg = default_config()
    if config:
        cfg.update(config)
    market = row.get("market") or "IDX"
    mode = row.get("market_mode") or "NORMAL"
    verdict = row.get("verdict") or "NEUTRAL"
    lv = row.get("levels") or {}
    screen = row.get("screen") or {}
    flags = lv.get("flags") or []
    leader = row.get("pullback_state") in cfg["leader_states"]
    gates: Dict[str, bool] = {}
    reasons: List[str] = []

    # ── Market ──────────────────────────────────────────────────────────────
    mode_label = MODE_LABELS.get(mode, mode.lower())
    if mode in cfg["blocked_modes"]:
        gates["market_ok"] = False
        reasons.append(f"Pasar {mode_label} — tahan pembelian")
    elif mode in cfg["leaders_only_modes"] and not leader:
        gates["market_ok"] = False
        reasons.append(f"Pasar {mode_label} — hanya untuk saham pemimpin tren")
    else:
        gates["market_ok"] = True

    # ── Signal ──────────────────────────────────────────────────────────────
    speculative = bool(row.get("is_speculative"))
    if cfg["signal_basis"] == "raw" and verdict not in BEARISH:
        own = stock_signal_score(row)
        if own is None:  # rows without raw_score fall back to the verdict
            signal = verdict in BULLISH
        else:
            signal = own >= cfg["signal_min_score"]
    else:
        own = None
        signal = verdict in BULLISH
    gates["signal_ok"] = signal and not speculative
    if speculative:
        reasons.append("Saham spekulatif (rugi/utang tinggi)")
    elif not signal:
        if own is not None:
            reasons.append(f"Belum ada sinyal beli (skor saham {own:.0f} < {cfg['signal_min_score']})")
        else:
            reasons.append(f"Belum ada sinyal beli (vonis {VERDICT_LABELS.get(verdict, verdict)})")

    # ── Risk to the stop ────────────────────────────────────────────────────
    risk = _num(lv.get("risk_pct"))
    gates["risk_ok"] = risk is not None and risk <= cfg["max_risk_pct"]
    if risk is None:
        reasons.append("Rencana harga belum tersedia")
    elif not gates["risk_ok"]:
        reasons.append(f"Risiko {_id(risk)}% > batas {_id(cfg['max_risk_pct'])}%")

    # ── Room to the first target vs the risk ────────────────────────────────
    min_rr = float(cfg.get("min_rr") or 0)
    if min_rr > 0:
        rr = _num(lv.get("risk_reward_ratio"))
        gates["room_ok"] = rr is not None and rr >= min_rr
        if not gates["room_ok"]:
            reasons.append(f"Ruang ke TP1 sempit (Rugi : Untung 1 : {_id(rr) if rr is not None else '-'}, "
                           f"minimal 1 : {_id(min_rr)})")

    # ── Volatility vs stop distance ─────────────────────────────────────────
    gates["vol_ok"] = not (cfg["require_not_volatile"] and "too_volatile" in flags)
    if not gates["vol_ok"]:
        atr_pct = _num(screen.get("atr_pct"))
        reasons.append("Terlalu volatil untuk jarak cut loss ini"
                       + (f" (gerak harian ±{_id(atr_pct)}%)" if atr_pct else ""))

    # ── Liquidity ───────────────────────────────────────────────────────────
    value = _num(screen.get("avg_value_20d"))
    min_value = cfg["min_value_us"] if market == "US" else cfg["min_value_idx"]
    gates["liquid_ok"] = value is not None and value >= min_value
    if value is None:
        reasons.append("Likuiditas belum diketahui")
    elif not gates["liquid_ok"]:
        reasons.append(f"Kurang likuid ({_money(value, market)})")

    # ── Data (abnormal bars; missing abnormal_recent = no known issue) ──────
    bad = recent_abnormal(row, tuple(cfg["data_block_kinds"]), cfg["data_lookback_days"])
    gates["data_ok"] = not bad
    if bad:
        a = bad[0]
        reasons.append(f"Ada {ABNORMAL_LABELS.get(a.get('kind'), a.get('kind'))} {_day_label(a['date'])} — tunggu stabil")

    # ── Status ──────────────────────────────────────────────────────────────
    live = (lv.get("live") or {}).get("status")
    locked = bool(recent_abnormal(row, ("LOCK_DOWN",), cfg["data_lookback_days"]))
    news_risk = str(row.get("catalyst") or "").startswith("RISK:")
    if news_risk:
        reasons.insert(0, f"Berita risiko: {str(row['catalyst'])[5:].strip()} — hindari sampai jelas")
    if verdict in BEARISH or live == "BELOW_STOP" or locked or news_risk:
        status = "HINDARI"
        if verdict in BEARISH:
            # Lead with the verdict itself: it is the reason for HINDARI
            reasons = [r for r in reasons if not r.startswith("Belum ada sinyal beli")]
            reasons.insert(0, f"Vonis {VERDICT_LABELS.get(verdict, verdict)} — sinyal jual")
        if live == "BELOW_STOP":
            reasons.insert(0, "Harga sudah di bawah cut loss — rencana batal")
    elif live in ("AT_TP1", "AT_TP2"):
        # Intraday only (the backtest has no live bar): the target of today's plan is already
        # reached, so there is no reward room left to buy into
        status = "TUNGGU"
        reasons.insert(0, "Harga sudah menyentuh TP1 hari ini — tunggu rencana baru setelah penutupan")
    elif all(gates.values()):
        status = "LAYAK"
    else:
        status = "TUNGGU"
    return {"status": status, "reasons": reasons, "gates": gates}


# Besides the status, the rank asks whether the plan is worth an order from where the price is
# (the live price during the session, the close the plan was built from otherwise):
#   0 entry within NEAR_ATR of the price and TP1 still above it
#   1 entry 0.5–1 ATR below the price (backtest: the limit fills ~40 % of the time vs ~77 % when
#     ≤ 0.25 ATR) or TP1 already at/under the price (no room left — logic, small backtest sample)
#   2 more than FAR_ABOVE_ATR above the zone: a limit order is unlikely to fill soon
#   3 target already reached or cut loss broken today: the plan is over
# Evidence: docs/hasil-akhir-fase1-5.md ("Peringkat").
MISSED_TODAY = ("AT_TP1", "AT_TP2", "BELOW_STOP")
NEAR_ATR = 0.5
FAR_ABOVE_ATR = 1.0


def today_tier(levels: Dict[str, Any]) -> int:
    live = levels.get("live") if levels.get("frozen") else None
    ref = None
    if isinstance(live, dict):
        if live.get("status") in MISSED_TODAY or live.get("touched_stop"):
            return 3
        ref = _num(live.get("price"))
    if ref is None:
        ref = _num(levels.get("price"))
    atr, eh, tp1 = _num(levels.get("atr14")), _num(levels.get("entry_high")), _num(levels.get("target_tp1"))
    if ref is None or not eh:
        return 0
    dist = (ref - eh) / atr if atr and ref > eh else 0.0
    if dist > FAR_ABOVE_ATR:
        return 2
    if dist > NEAR_ATR or (tp1 and ref >= tp1):
        return 1
    return 0


def missed_today(levels: Dict[str, Any]) -> bool:
    return today_tier(levels) == 2


def rank_key(row: Dict[str, Any]) -> tuple:
    """Ascending sort key: status (LAYAK first), today_tier (plan still executable today first),
    then raw_score, score, R:R, liquidity (high first)."""
    action = row.get("action") or {}
    status = action.get("status") or assess(row)["status"]
    lv = row.get("levels") or {}
    screen = row.get("screen") or {}

    def neg(v: Any) -> float:
        f = _num(v)
        return -f if f is not None else float("inf")

    raw = row.get("raw_score")
    return (STATUS_ORDER.get(status, 3), today_tier(lv), neg(raw if raw is not None else row.get("score")), neg(row.get("score")),
            neg(lv.get("risk_reward_ratio")), neg(screen.get("avg_value_20d")))
