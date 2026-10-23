"""OHLCV data-quality checks: clean raw candles before they reach the cache or the indicators.

clean_ohlcv() returns a cleaned DataFrame plus a JSON-serializable quality report.
Exchange-session helpers (last closed session, staleness) also live here so the cache
freshness rule in market_data.py and the staleness in the report use the same clock.
"""
from datetime import datetime, time as dtime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PRICE_COLS = ["open", "high", "low", "close"]
OHLCV_COLS = ["date", "open", "high", "low", "close", "volume"]

# A single bar that moves more than this vs the previous close is suspicious
JUMP_THRESHOLD = 0.35
# ...and if the next bar comes back within this distance of the pre-jump close, it was a bad tick
REVERT_TOLERANCE = 0.10
# Calendar-day gap between consecutive daily bars that counts as missing data.
# IDX closes for ~1.5 weeks around Lebaran (cuti bersama); US holidays never exceed a long weekend.
MAX_GAP_DAYS = {"IDX": 14, "US": 6}

def _zone(name: str, fallback_hours: int):
    # A frozen build without tzdata must not crash on import; fixed offset ignores US DST (1h off)
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=fallback_hours))


# Exchange sessions. Daily bars count as final only some minutes after the official close.
EXCHANGES = {
    "IDX": {"tz": _zone("Asia/Jakarta", 7), "open": dtime(9, 0), "close": dtime(16, 0), "final_after_min": 45},
    "US": {"tz": _zone("America/New_York", -5), "open": dtime(9, 30), "close": dtime(16, 0), "final_after_min": 30},
}


# ---------------------------------------------------------------------------
# Exchange clock
# ---------------------------------------------------------------------------
def exchange_for(ticker: str) -> str:
    t = (ticker or "").upper()
    return "IDX" if t.endswith(".JK") or t == "^JKSE" else "US"


def _now_utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now().astimezone()
    return now if now.tzinfo else now.astimezone()


def last_closed_session(ticker: str, now: Optional[datetime] = None) -> datetime:
    """Aware datetime at which the most recent completed session's daily bar became final.

    Weekends are skipped; exchange holidays are not known, so on a holiday this points at the
    holiday itself (callers treat "fetched after that moment" as fresh, which still works).
    """
    return _last_closed(EXCHANGES[exchange_for(ticker)], now)


def _last_closed(ex: Dict[str, Any], now: Optional[datetime]) -> datetime:
    local = _now_utc(now).astimezone(ex["tz"])
    final_t = (datetime.combine(local.date(), ex["close"]) + timedelta(minutes=ex["final_after_min"])).time()
    d = local.date()
    if local.weekday() >= 5 or local.time() < final_t:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime.combine(d, final_t, tzinfo=ex["tz"])


def is_session_open(ticker: str, now: Optional[datetime] = None) -> bool:
    """True from the open until the daily bar is final (close + settle buffer) on weekdays."""
    ex = EXCHANGES[exchange_for(ticker)]
    local = _now_utc(now).astimezone(ex["tz"])
    if local.weekday() >= 5:
        return False
    final_dt = datetime.combine(local.date(), ex["close"], tzinfo=ex["tz"]) + timedelta(minutes=ex["final_after_min"])
    return datetime.combine(local.date(), ex["open"], tzinfo=ex["tz"]) <= local < final_dt


def bar_is_final(bar_date: Any, market: str = "IDX", now: Optional[datetime] = None) -> Optional[bool]:
    """Is the daily bar dated `bar_date` complete? False while its session is still trading
    (or settling); None when the date is unknown."""
    try:
        ts = pd.Timestamp(bar_date)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts):
        return None
    d = ts.date()
    return d <= _last_closed(EXCHANGES.get(market, EXCHANGES["IDX"]), now).date()


def trading_days_between(last_bar: date, expected: date) -> int:
    """Weekdays in (last_bar, expected]; 0 when the data is up to date."""
    if last_bar >= expected:
        return 0
    return int(np.busday_count(last_bar + timedelta(days=1), expected + timedelta(days=1)))


def staleness_trading_days(ticker: str, last_bar_date: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    if not last_bar_date:
        return None
    try:
        last = datetime.strptime(str(last_bar_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return trading_days_between(last, last_closed_session(ticker, now).date())


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def _issue(code: str, severity: str, count: int, message: str, dates: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"code": code, "severity": severity, "count": int(count), "message": message, "dates": (dates or [])[:10]}


def _date_labels(dates: pd.Series) -> List[str]:
    return [str(d)[:10] for d in dates]


def clean_ohlcv(df: pd.DataFrame, ticker: str = "", interval: str = "1d") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean an OHLCV frame (date/open/high/low/close/volume) and describe what was wrong with it.

    - rows with NaN or non-positive prices are dropped
    - duplicate dates are collapsed (last one wins)
    - high/low are widened to contain open/close
    - zero-volume bars (holidays, suspensions) are dropped from the output but reported
    - a single-bar jump > 35% that fully reverts the next bar is dropped as a bad tick
    - a jump > 35% that does not revert (likely unadjusted split/rights issue) and long date
      gaps are only reported
    The 'date' column keeps its original type (string, datetime or unix int for intraday).
    """
    issues: List[Dict[str, Any]] = []
    rows_raw = 0 if df is None else int(len(df))
    if df is None or df.empty:
        report = _build_report(ticker, interval, rows_raw, pd.DataFrame(columns=OHLCV_COLS), issues)
        return pd.DataFrame(columns=OHLCV_COLS), report

    out = df.loc[:, [c for c in OHLCV_COLS if c in df.columns]].copy()
    for c in OHLCV_COLS[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce") if c in out.columns else np.nan
    out["volume"] = out["volume"].fillna(0.0)

    # 1. Invalid prices
    bad = out[PRICE_COLS].isna().any(axis=1) | (out[PRICE_COLS] <= 0).any(axis=1)
    if bad.any():
        issues.append(_issue("INVALID_PRICE", "warning", bad.sum(),
                             "Bar dengan harga kosong/nol dibuang", _date_labels(out.loc[bad, "date"])))
        out = out.loc[~bad]

    # 2. Order by time, collapse duplicate timestamps
    is_intraday = interval not in ("1d", "1wk", "1mo")
    sort_key = out["date"] if is_intraday else pd.to_datetime(out["date"].astype(str).str[:10], errors="coerce")
    out = out.assign(_k=sort_key).dropna(subset=["_k"]).sort_values("_k", kind="stable")
    dup = out["_k"].duplicated(keep="last")
    if dup.any():
        issues.append(_issue("DUPLICATE_DATE", "info", dup.sum(),
                             "Tanggal ganda digabung (data terakhir dipakai)", _date_labels(out.loc[dup, "date"])))
        out = out.loc[~dup]

    # 3. High/low must contain open/close
    hi = out[PRICE_COLS].max(axis=1)
    lo = out[PRICE_COLS].min(axis=1)
    fix = (out["high"] < hi) | (out["low"] > lo)
    if fix.any():
        issues.append(_issue("HIGH_LOW_REPAIRED", "info", fix.sum(),
                             "High/low diperbaiki agar mencakup open/close", _date_labels(out.loc[fix, "date"])))
        out["high"] = hi
        out["low"] = lo

    # 4. Zero-volume bars: no trading happened, they distort volume averages and money flow
    zero = out["volume"] <= 0
    if zero.any():
        ratio = zero.mean()
        issues.append(_issue("ZERO_VOLUME", "warning" if ratio > 0.1 else "info", zero.sum(),
                             "Bar tanpa volume (libur/suspensi) tidak dipakai untuk indikator",
                             _date_labels(out.loc[zero, "date"])))
        out = out.loc[~zero]

    # 5. Bad ticks (spike that fully reverts) vs unexplained jumps (likely corporate action)
    out = out.reset_index(drop=True)
    if len(out) >= 3:
        close = out["close"].to_numpy(dtype=float)
        prev, cur, nxt = close[:-2], close[1:-1], close[2:]
        jump = np.abs(cur / prev - 1.0) > JUMP_THRESHOLD
        reverts = np.abs(nxt / prev - 1.0) <= REVERT_TOLERANCE
        tick_idx = np.where(jump & reverts)[0] + 1
        if len(tick_idx):
            issues.append(_issue("BAD_TICK", "warning", len(tick_idx),
                                 "Lonjakan harga satu bar yang langsung kembali (data salah) dibuang",
                                 _date_labels(out.loc[tick_idx, "date"])))
            out = out.drop(index=tick_idx).reset_index(drop=True)

    if len(out) >= 2:
        close = out["close"].to_numpy(dtype=float)
        rel = np.abs(close[1:] / close[:-1] - 1.0)
        jump_idx = np.where(rel > JUMP_THRESHOLD)[0] + 1
        if len(jump_idx):
            issues.append(_issue("PRICE_JUMP", "warning", len(jump_idx),
                                 "Lonjakan harga >35% tanpa pembalikan (kemungkinan split/right issue belum disesuaikan)",
                                 _date_labels(out.loc[jump_idx, "date"])))

    # 6. Missing stretches of daily data
    if not is_intraday and len(out) >= 2:
        max_gap = MAX_GAP_DAYS[exchange_for(ticker)]
        gaps = out["_k"].diff().dt.days
        gap_mask = gaps > max_gap
        if gap_mask.any():
            issues.append(_issue("DATE_GAP", "warning", gap_mask.sum(),
                                 f"Celah data lebih dari {max_gap} hari kalender",
                                 _date_labels(out.loc[gap_mask, "date"])))

    out = out.drop(columns=["_k"]).reset_index(drop=True)
    return out, _build_report(ticker, interval, rows_raw, out, issues)


# ---------------------------------------------------------------------------
# Report & score
# ---------------------------------------------------------------------------
# Per-issue penalty per occurrence and cap (points out of 100)
_PENALTIES = {
    "INVALID_PRICE": (2, 20),
    "DUPLICATE_DATE": (1, 5),
    "HIGH_LOW_REPAIRED": (1, 10),
    "BAD_TICK": (5, 20),
    "PRICE_JUMP": (20, 40),  # an unadjusted split corrupts every indicator
    "DATE_GAP": (3, 15),
}


def _base_score(issues: List[Dict[str, Any]], rows_raw: int, rows_clean: int) -> int:
    score = 100.0
    for it in issues:
        if it["code"] in _PENALTIES:
            per, cap = _PENALTIES[it["code"]]
            score -= min(per * it["count"], cap)
        elif it["code"] == "ZERO_VOLUME" and rows_raw:
            score -= min(100.0 * it["count"] / rows_raw, 15)
        elif it["code"] == "SHORT_HISTORY":
            score -= 30 if rows_clean < 30 else 10
    if rows_clean == 0:
        score = 0
    return int(max(0, min(100, round(score))))


def _staleness_penalty(days: Optional[int]) -> int:
    if days is None or days <= 0:
        return 0
    if days == 1:
        return 5  # often just an exchange holiday
    if days == 2:
        return 15
    if days <= 5:
        return 30
    return 50


def grade_for(score: int) -> str:
    return "GOOD" if score >= 85 else "FAIR" if score >= 60 else "POOR"


def _build_report(ticker: str, interval: str, rows_raw: int, clean: pd.DataFrame, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows_clean = int(len(clean))
    is_daily = interval in ("1d", "1wk", "1mo")
    if is_daily and 0 < rows_clean < 200:
        issues = issues + [_issue("SHORT_HISTORY", "info" if rows_clean >= 30 else "warning", rows_clean,
                                  f"Riwayat hanya {rows_clean} bar; EMA200 & tren jangka panjang kurang akurat")]
    first = str(clean["date"].iloc[0])[:10] if rows_clean and is_daily else None
    last = str(clean["date"].iloc[-1])[:10] if rows_clean and is_daily else None
    report = {
        "ticker": ticker,
        "interval": interval,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "network",
        "rows_raw": rows_raw,
        "rows_clean": rows_clean,
        "first_date": first,
        "last_bar_date": last,
        "issues": issues,
        "base_score": _base_score(issues, rows_raw, rows_clean),
    }
    return with_staleness(report)


def with_staleness(report: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """(Re)compute the time-dependent fields: staleness, final score, grade.

    Stored reports are refreshed through this on read so staleness is always relative to now.
    """
    r = dict(report)
    ticker = r.get("ticker") or ""
    days = staleness_trading_days(ticker, r.get("last_bar_date"), now) if r.get("interval", "1d") == "1d" else None
    r["expected_last_date"] = last_closed_session(ticker, now).date().isoformat() if ticker else None
    r["staleness_trading_days"] = days
    r["is_stale"] = bool(days is not None and days >= 2)
    base = int(r.get("base_score", 0))
    r["score"] = max(0, base - _staleness_penalty(days)) if r.get("rows_clean") else 0
    r["grade"] = grade_for(r["score"])
    return r
