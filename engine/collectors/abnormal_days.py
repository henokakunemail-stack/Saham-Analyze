"""Abnormal trading days: price-limit locks, limit moves, trading halts and corporate actions.

Days that do not reflect normal two-sided trading distort ATR, swing pivots and signals. This
module only labels them (pure functions, no network); callers decide what to do with the labels:

    kinds = classify_bars(df, market)            # one label (or None) per bar, same index as df
    tr = clean_true_range(df, kinds)             # true range with LOCK_*/gap/corp-action bars smoothed
    mask = pivot_mask(kinds)                     # False = bar must not be a swing high/low
    items = recent(df, market, days=20)          # [{date, kind, label}] for the UI, newest last

Labels:
    LOCK_DOWN / LOCK_UP      open = high = low = close (within one tick), >= 3% and >= 2 ticks below/above
                             the previous close
    LIMIT_DOWN / LIMIT_UP    (IDX) close at the day's low/high and |change| >= 90% of the auto-rejection band
    SUSPENSION_GAP           first bar after > 3 trading days without bars (exchange holidays excluded)
    CORP_ACTION              > 35% jump that does not revert, matched by a split or (no split data) > 45%
"""
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

LOCK_DOWN = "LOCK_DOWN"
LOCK_UP = "LOCK_UP"
LIMIT_DOWN = "LIMIT_DOWN"
LIMIT_UP = "LIMIT_UP"
SUSPENSION_GAP = "SUSPENSION_GAP"
CORP_ACTION = "CORP_ACTION"
KINDS = (LOCK_DOWN, LOCK_UP, LIMIT_DOWN, LIMIT_UP, SUSPENSION_GAP, CORP_ACTION)

# Bars whose range is not a real trading range (replaced in clean_true_range)
TR_REPLACE_KINDS = frozenset({LOCK_DOWN, LOCK_UP, SUSPENSION_GAP, CORP_ACTION})
# Bars that must never be swing highs/lows
NO_PIVOT_KINDS = frozenset({LOCK_DOWN, LOCK_UP, CORP_ACTION})

LABELS_IDX = {
    LOCK_DOWN: "ARB (terkunci batas bawah)",
    LOCK_UP: "ARA (terkunci batas atas)",
    LIMIT_DOWN: "Turun ke batas ARB",
    LIMIT_UP: "Naik ke batas ARA",
    SUSPENSION_GAP: "Jeda perdagangan / suspensi",
    CORP_ACTION: "Aksi korporasi (split/right issue?)",
}
LABELS_US = {
    **LABELS_IDX,
    LOCK_DOWN: "Terkunci turun (open=high=low=close)",
    LOCK_UP: "Terkunci naik (open=high=low=close)",
}

# ── BEI auto-rejection bands (cocokkan dengan idx.co.id) ─────────────────────
# (upper bound of the previous close, band). Price band is chosen by the previous close.
# ARA (auto rejection atas) for the regular board: Rp50–200 35%, >200–5.000 25%, >5.000 20%.
ARA_BANDS = ((200, 0.35), (5000, 0.25), (float("inf"), 0.20))
# ARB (auto rejection bawah): BEI has changed this several times (asymmetric 7%→15% after 2020,
# symmetric with ARA later, then a flat 15% from 8 Apr 2025). Table of (effective_from, bands),
# oldest first; the newest entry whose date is <= the bar's date applies. The cached IDX data
# confirms it: close-at-low drops cluster at -20%/-25% in 2024–Q1 2025 and at -15% since Apr 2025.
ARB_BANDS_HISTORY = (
    ("1900-01-01", ARA_BANDS),
    ("2025-04-08", ((200, 0.15), (5000, 0.15), (float("inf"), 0.15))),
)
LIMIT_FRACTION = 0.90   # a move counts as a limit move at >= 90% of the band (ticks round the limit)
# A one-price day (range <= 1 tick) only counts as locked when it also moved meaningfully: quiet
# illiquid days that print one price a tick or two from yesterday are not price-limit locks.
LOCK_MIN_MOVE = 0.03
LOCK_MIN_TICKS = 2

# ── Gaps & corporate actions ─────────────────────────────────────────────────
SUSPENSION_MIN_GAP = 3          # flag when MORE than this many trading days are missing
CORP_JUMP = 0.35                # same threshold as data_quality.JUMP_THRESHOLD
CORP_REVERT_TOLERANCE = 0.10    # next close back within 10% of the pre-jump close = bad tick, not an action
# Without split data a non-reverting jump only counts as a corporate action above this size
# (> any IDX price limit). None = never without a matching split (US: Yahoo split-adjusts its
# history and limit-free moves of 50%+ on earnings are real).
CORP_JUMP_NO_SPLIT = {"IDX": 0.45, "US": None}
SPLIT_WINDOW_DAYS = 3

# IDX full-day market closures seen in the cached data (no IDX ticker traded), so long holiday
# blocks such as Lebaran are not reported as suspensions. Cocokkan dengan kalender bursa idx.co.id
# and extend every year; unknown holidays only make a gap one day longer.
IDX_MARKET_HOLIDAYS = frozenset({
    "2023-12-25", "2023-12-26",
    "2024-01-01", "2024-02-08", "2024-02-09", "2024-02-14", "2024-03-11", "2024-03-12", "2024-03-29",
    "2024-04-08", "2024-04-09", "2024-04-10", "2024-04-11", "2024-04-12", "2024-04-15", "2024-05-01",
    "2024-05-09", "2024-05-10", "2024-05-23", "2024-05-24", "2024-06-17", "2024-06-18", "2024-09-16",
    "2024-11-27", "2024-12-25", "2024-12-26", "2024-12-31",
    "2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-03-28", "2025-03-31", "2025-04-01",
    "2025-04-02", "2025-04-03", "2025-04-04", "2025-04-07", "2025-04-18", "2025-05-01", "2025-05-12",
    "2025-05-13", "2025-05-29", "2025-05-30", "2025-06-06", "2025-06-09", "2025-06-27", "2025-08-18",
    "2025-09-05", "2025-12-25", "2025-12-26", "2025-12-31",
    "2026-01-01", "2026-01-16", "2026-02-16", "2026-02-17", "2026-03-18", "2026-03-19", "2026-03-20",
    "2026-03-23", "2026-03-24", "2026-04-03", "2026-05-01", "2026-05-14", "2026-05-15", "2026-05-27",
    "2026-05-28", "2026-06-01", "2026-06-16", "2026-08-17", "2026-08-25",
})

TR_MEAN_WINDOW = 14
HOLIDAY_CACHE_SEC = 600
_holiday_cache: Dict[str, Any] = {"at": 0.0, "value": IDX_MARKET_HOLIDAYS}


def idx_market_holidays() -> frozenset:
    """IDX_MARKET_HOLIDAYS plus every weekday the composite index (^JKSE, cached candles) did not
    trade, so closures after the static list (year-end, next Lebaran) are never read as suspensions."""
    import time
    now = time.monotonic()
    if _holiday_cache["at"] and now - _holiday_cache["at"] < HOLIDAY_CACHE_SEC:
        return _holiday_cache["value"]
    value = IDX_MARKET_HOLIDAYS
    try:
        from ..db import get_candles
        days = sorted({str(b["date"])[:10] for b in (get_candles("^JKSE", limit=1000) or [])})
        if len(days) >= 20:
            have, missing = set(days), set()
            d, end = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
            while d < end:
                if d.weekday() < 5 and d.isoformat() not in have:
                    missing.add(d.isoformat())
                d += timedelta(days=1)
            value = IDX_MARKET_HOLIDAYS | frozenset(missing)
    except Exception:
        pass
    _holiday_cache.update(at=now, value=value)
    return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _band(price: float, bands: Sequence) -> float:
    for limit, pct in bands:
        if price <= limit:
            return pct
    return bands[-1][1]


def ara_band(prev_close: float) -> float:
    return _band(prev_close, ARA_BANDS)


def arb_band(prev_close: float, on: Optional[str] = None) -> float:
    """ARB band for a previous close on a given date (YYYY-MM-DD; None = newest rule)."""
    bands = ARB_BANDS_HISTORY[-1][1]
    if on:
        for start, b in ARB_BANDS_HISTORY:
            if start <= on[:10]:
                bands = b
    return _band(prev_close, bands)


def _dates(df: pd.DataFrame) -> pd.Series:
    """Bar dates as YYYY-MM-DD strings (index aligned with df)."""
    if "date" in df.columns:
        raw = df["date"]
    else:
        raw = pd.Series(df.index, index=df.index)
    parsed = pd.to_datetime(raw.astype(str).str[:10], errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)


def _to_day(value: Any) -> Optional[date]:
    try:
        ts = pd.Timestamp(str(value)[:10])
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts.date()


def _split_days(splits: Optional[Iterable[Any]]) -> List[date]:
    """Split dates from [{"date", "ratio"}], plain date strings or datetimes."""
    out: List[date] = []
    for s in splits or []:
        d = _to_day(s.get("date") if isinstance(s, dict) else s)
        if d is not None:
            out.append(d)
    return out


def _missing_trading_days(prev: date, cur: date, holidays: frozenset) -> int:
    """Weekdays strictly between two bar dates that are not known exchange holidays."""
    if cur <= prev:
        return 0
    n = int(np.busday_count(prev + timedelta(days=1), cur))
    if n and holidays:
        d = prev + timedelta(days=1)
        while d < cur:
            if d.weekday() < 5 and d.isoformat() in holidays:
                n -= 1
            d += timedelta(days=1)
    return n


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def classify_bars(df: pd.DataFrame, market: str = "IDX", splits: Optional[Iterable[Any]] = None,
                  holidays: Optional[Iterable[str]] = None) -> pd.Series:
    """One label per bar (None for a normal day); same index as df.

    df: daily OHLCV with date/open/high/low/close(/volume), oldest first (clean_ohlcv output).
    splits: optional split records ({"date", "ratio"} dicts or dates) from corp_actions; None means
        "no split data" (a jump then needs > 45% on IDX to count as a corporate action).
    holidays: YYYY-MM-DD exchange closures excluded from gap counting (default: idx_market_holidays()
        for IDX, none for US).
    When several labels apply the most specific wins: CORP_ACTION > LOCK_* > SUSPENSION_GAP > LIMIT_*.
    """
    # Imported here: trade_levels will import this module (ATR/pivots), a top-level import would cycle
    from ..screener.trade_levels import tick_size

    market = (market or "IDX").upper()
    out = pd.Series([None] * (0 if df is None else len(df)), index=None if df is None else df.index, dtype=object)
    if df is None or len(df) < 2:
        return out

    o = pd.to_numeric(df["open"], errors="coerce").to_numpy(dtype=float)
    h = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    lo = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    c = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    dates = _dates(df).tolist()
    days = [_to_day(d) if d else None for d in dates]
    hol = frozenset(holidays) if holidays is not None else (idx_market_holidays() if market == "IDX" else frozenset())
    split_days = _split_days(splits)
    has_split_data = splits is not None
    no_split_jump = CORP_JUMP_NO_SPLIT.get(market, CORP_JUMP_NO_SPLIT["IDX"])
    eps = 1e-9

    labels: List[Optional[str]] = [None] * len(df)
    for i in range(1, len(df)):
        pc = c[i - 1]
        if not (np.isfinite(pc) and pc > 0 and np.isfinite(c[i]) and c[i] > 0):
            continue
        tick = tick_size(c[i], market)
        chg = c[i] / pc - 1.0

        # Corporate action: big jump that holds on the next bar (a reverting one is a bad tick)
        if abs(chg) > CORP_JUMP:
            reverts = i + 1 < len(df) and np.isfinite(c[i + 1]) and abs(c[i + 1] / pc - 1.0) <= CORP_REVERT_TOLERANCE
            if not reverts:
                near_split = days[i] is not None and any(abs((days[i] - sd).days) <= SPLIT_WINDOW_DAYS
                                                         for sd in split_days)
                big = no_split_jump is not None and abs(chg) > no_split_jump
                if near_split or big:
                    labels[i] = CORP_ACTION
                    continue

        # Locked all day: no range at all, only one price traded
        rng = max(o[i], h[i], lo[i], c[i]) - min(o[i], h[i], lo[i], c[i])
        moved = abs(chg) >= LOCK_MIN_MOVE and abs(c[i] - pc) >= LOCK_MIN_TICKS * tick - eps
        if np.isfinite(rng) and rng <= tick + eps and moved:
            labels[i] = LOCK_DOWN if c[i] < pc else LOCK_UP
            continue

        # Trading halt: bars missing for more than SUSPENSION_MIN_GAP trading days
        if days[i] is not None and days[i - 1] is not None \
                and _missing_trading_days(days[i - 1], days[i], hol) > SUSPENSION_MIN_GAP:
            labels[i] = SUSPENSION_GAP
            continue

        # Closed at the auto-rejection limit (IDX only)
        if market == "IDX":
            if chg < 0 and c[i] - lo[i] <= tick + eps and -chg >= LIMIT_FRACTION * arb_band(pc, dates[i]):
                labels[i] = LIMIT_DOWN
            elif chg > 0 and h[i] - c[i] <= tick + eps and chg >= LIMIT_FRACTION * ara_band(pc):
                labels[i] = LIMIT_UP

    out[:] = labels
    return out


def label_for(kind: str, market: str = "IDX") -> str:
    table = LABELS_IDX if (market or "IDX").upper() == "IDX" else LABELS_US
    return table.get(kind, kind)


def recent(df: pd.DataFrame, market: str = "IDX", days: int = 20, splits: Optional[Iterable[Any]] = None,
           kinds: Optional[pd.Series] = None) -> List[Dict[str, str]]:
    """Abnormal days among the last `days` bars as [{date, kind, label}], newest last.

    Pass precomputed `kinds` (from classify_bars on the same df) to avoid classifying twice.
    """
    if df is None or len(df) == 0:
        return []
    if kinds is None:
        kinds = classify_bars(df, market, splits=splits)
    dates = _dates(df).tolist()
    vals = list(kinds)
    start = max(0, len(vals) - max(int(days), 0))
    return [{"date": dates[i] or "", "kind": vals[i], "label": label_for(vals[i], market)}
            for i in range(start, len(vals)) if vals[i]]


def markers(df: pd.DataFrame, market: str = "IDX", kinds: Optional[pd.Series] = None,
            splits: Optional[Iterable[Any]] = None) -> List[Dict[str, str]]:
    """All abnormal bars as chart markers [{time: YYYY-MM-DD, kind, label}], oldest first."""
    return [{"time": it["date"], "kind": it["kind"], "label": it["label"]}
            for it in recent(df, market, days=len(df) if df is not None else 0, splits=splits, kinds=kinds)]


# ---------------------------------------------------------------------------
# Consumers: ATR and swing pivots
# ---------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    """Classic true range (same formula as trade_levels.compute_trade_levels)."""
    high, low = df["high"].astype(float), df["low"].astype(float)
    prev = df["close"].astype(float).shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def clean_true_range(df: pd.DataFrame, kinds: Optional[Sequence[Any]]) -> pd.Series:
    """True range where LOCK_*, SUSPENSION_GAP and CORP_ACTION bars are replaced by the mean TR of
    the previous 14 normal bars (fewer if not available; the bar keeps its slot so ATR's day count
    is unchanged). Without any earlier normal bar the original TR is kept."""
    tr = true_range(df)
    if kinds is None or len(tr) == 0:
        return tr
    flags = np.array([k in TR_REPLACE_KINDS for k in list(kinds)], dtype=bool)
    if len(flags) != len(tr) or not flags.any():
        return tr
    vals = tr.to_numpy(dtype=float).copy()
    normal: List[float] = []
    for i in range(len(vals)):
        if flags[i]:
            window = normal[-TR_MEAN_WINDOW:]
            if window:
                vals[i] = float(np.mean(window))
        elif np.isfinite(vals[i]):
            normal.append(vals[i])
    return pd.Series(vals, index=tr.index)


def pivot_mask(kinds: Optional[Sequence[Any]]) -> np.ndarray:
    """Boolean per bar: False where the bar must not be a swing high/low (LOCK_*, CORP_ACTION)."""
    if kinds is None:
        return np.ones(0, dtype=bool)
    return np.array([k not in NO_PIVOT_KINDS for k in list(kinds)], dtype=bool)


def find_pivots_masked(series: pd.Series, mask: Optional[np.ndarray], kind: str = "high", k: Optional[int] = None) -> List[int]:
    """find_pivots that ignores masked bars: they can neither be a pivot nor block a neighbour
    (a locked low is treated as +inf for 'low', a locked high as -inf for 'high').
    `mask` must line up with `series` (slice it the same way, e.g. mask[-len(series):])."""
    from ..indicators.trend import PIVOT_K, find_pivots
    k = PIVOT_K if k is None else k
    if mask is None or len(mask) != len(series) or mask.all():
        return find_pivots(series, k=k, kind=kind)
    fill = -np.inf if kind == "high" else np.inf
    vals = series.astype(float).to_numpy().copy()
    vals[~mask] = fill
    return [i for i in find_pivots(pd.Series(vals, index=series.index), k=k, kind=kind) if mask[i]]


def summary(kinds: Optional[Sequence[Any]]) -> Dict[str, int]:
    """Count per kind (for data-quality reports)."""
    out = {k: 0 for k in KINDS}
    for k in list(kinds) if kinds is not None else []:
        if k in out:
            out[k] += 1
    return out
