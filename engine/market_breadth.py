"""Market breadth (owned by: Fase 4 — breadth & sektor).

How healthy is the whole scan universe, day by day, read from the cached daily candles:

    n                  tickers with a bar on that date
    pct_above_ema20    % of tickers whose close is above their EMA20 (EMA50, EMA200 likewise)
    advancers          close > previous close   (decliners: <, unchanged: =)
    new_high_20d       close above every close of the previous 19 sessions (= highest close in 20 sessions)
    new_low_20d        close below every close of the previous 19 sessions
    pct_cmf_pos        % of tickers with Chaikin Money Flow (20) > 0

A ticker only counts towards a percentage once it has enough bars for that indicator (EMA-N needs N bars,
CMF20 and the 20-day high/low need 20), so a freshly listed stock never distorts EMA200 breadth.
Every series is causal (EMA with adjust=False, trailing rolling windows), so the value for a date only uses
candles up to that date — computing the series once per ticker and reading them per date is identical to
recomputing on truncated data (tested in tests/test_breadth_sectors.py).

Stored one row per (market, date) in the module's own table `market_breadth` (metrics as JSON).
Display only for now (Tahap A): nothing here changes scores or market mode.

Entry points:
    compute_for_date(frames, date) -> metrics          frames: {ticker: OHLCV DataFrame}
    backfill(market, tickers, days=120) -> int          rows stored, from cached candles
    update_today(market, tickers) -> metrics | None     recompute the most recent dates (end of a scan)
    compute_today(results, market)                      same, tickers taken from scan rows
    history(market, days=120) -> [{date, ...metrics, ad_line}]
    latest(market) -> {date, ...metrics} | None
    label(metrics) -> "Lemah (28% di atas EMA50)"       classify(metrics) -> {code, text}
"""
import json
import threading
from datetime import date as _date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .db import get_connection, get_candles

EMA_SPANS = (20, 50, 200)
EMA_EPS = 1e-9               # close must beat the EMA by more than float noise to count as above
CMF_WINDOW = 20
HL_WINDOW = 20                # new high / low = extreme close of the last 20 sessions
CANDLE_LIMIT = 400            # bars loaded per ticker (≥ 200 warm-up bars before the oldest backfilled date)
DEFAULT_DAYS = 120
UPDATE_DAYS = 5               # update_today recomputes this many latest dates (fills a missed day or two)
# A date is a real trading date of the universe when at least this share of the best-covered date's tickers
# have a bar on it (drops stray bars, e.g. one ticker with a bar on an exchange holiday)
MIN_DATE_COVERAGE = 0.5

# Plain-language reading of % above EMA50, rounded to a whole percent (checked top-down, first match wins).
# < 30 % is also the Tahap-B candidate threshold for CAUTIOUS mode (RENCANA_5_POIN 6.4).
BREADTH_STRONG = 70.0         # ≥ 70 %  → Kuat
BREADTH_HEALTHY = 50.0        # ≥ 50 %  → Sehat
BREADTH_NEUTRAL = 30.0        # ≥ 30 %  → Netral
BREADTH_WEAK = 15.0           # ≥ 15 %  → Lemah, below → Sangat lemah
LABELS = {
    "STRONG": "Kuat",
    "HEALTHY": "Sehat",
    "NEUTRAL": "Netral",
    "WEAK": "Lemah",
    "VERY_WEAK": "Sangat lemah",
    "NO_DATA": "Belum ada data",
}

_FLAG_FOR_PCT = {"pct_above_ema20": "a20", "pct_above_ema50": "a50", "pct_above_ema200": "a200", "pct_cmf_pos": "cmf"}

_initialized_for: Optional[str] = None
_init_lock = threading.Lock()


def _ensure_tables() -> None:
    global _initialized_for
    from .config import DB_PATH
    if _initialized_for == str(DB_PATH):
        return
    with _init_lock:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_breadth (
                    market TEXT NOT NULL,
                    date TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    updated_at TEXT,
                    PRIMARY KEY (market, date)
                )
            """)
            conn.commit()
        _initialized_for = str(DB_PATH)


def _market(market: Optional[str]) -> str:
    return (market or "IDX").strip().upper() or "IDX"


def _date_str(d: Any) -> str:
    if isinstance(d, (datetime, _date, pd.Timestamp)):
        return pd.Timestamp(d).strftime("%Y-%m-%d")
    return str(d)[:10]


# ─── Per-ticker flag series ──────────────────────────────────────────────────

_COLS = ("high", "low", "close", "volume")


def _floats(col: pd.Series) -> np.ndarray:
    try:
        return col.to_numpy(dtype=float)
    except (TypeError, ValueError):
        return pd.to_numeric(col, errors="coerce").to_numpy(dtype=float)


def _prep(df: Optional[pd.DataFrame]) -> Optional[Dict[str, np.ndarray]]:
    """OHLCV frame (a `date` column or a date index) → numpy arrays sorted by date, one bar per date.

    Keys: date ('YYYY-MM-DD' strings), high, low, close, volume. None when there is nothing usable."""
    if df is None or len(df) == 0:
        return None
    raw = df["date"] if "date" in df.columns else pd.Series(df.index)
    if pd.api.types.is_datetime64_any_dtype(raw):
        dates = pd.DatetimeIndex(raw).strftime("%Y-%m-%d").to_numpy(dtype=object)
    else:
        # 'YYYY-MM-DD…' strings (or date/Timestamp objects): a U10 cast keeps just the day
        dates = np.asarray(raw.astype(str), dtype="U10")
    arr = {c: _floats(df[c]) for c in _COLS}
    ok = np.isfinite(arr["close"]) & (arr["close"] > 0)
    if not ok.all():
        dates = dates[ok]
        arr = {c: v[ok] for c, v in arr.items()}
    if not len(dates):
        return None
    dates = dates.astype(str)
    # Sort by date and keep the last bar of a duplicated date
    order = np.argsort(dates, kind="stable")
    dates = dates[order]
    arr = {c: v[order] for c, v in arr.items()}
    keep = np.append(dates[1:] != dates[:-1], True)
    if not keep.all():
        dates = dates[keep]
        arr = {c: v[keep] for c, v in arr.items()}
    arr["date"] = dates
    return arr


def _prior_extreme(x: np.ndarray, window: int, fn) -> np.ndarray:
    """fn (np.max / np.min) over the `window` values BEFORE each position; NaN where not available."""
    out = np.full(len(x), np.nan)
    if len(x) > window:
        win = np.lib.stride_tricks.sliding_window_view(x[:-1], window)
        out[window:] = fn(win, axis=1)
    return out


def _rolling_sum(x: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= window:
        c = np.concatenate([[0.0], np.cumsum(x)])
        out[window - 1:] = c[window:] - c[:-window]
    return out


def _flags(bars: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Per bar: a20/a50/a200/cmf (1/0, NaN = not enough bars yet), chg (sign of the day's move), nh/nl (1/0/NaN)."""
    close, high, low = bars["close"], bars["high"], bars["low"]
    vol = np.nan_to_num(bars["volume"])
    count = np.arange(1, len(close) + 1)
    cs = pd.Series(close)
    out: Dict[str, np.ndarray] = {}

    for span in EMA_SPANS:
        ema = cs.ewm(span=span, adjust=False).mean().to_numpy()
        # Relative tolerance: a flat series' EMA can drift a few ulps below the close
        out[f"a{span}"] = np.where(count >= span, (close > ema * (1 + EMA_EPS)).astype(float), np.nan)

    out["chg"] = np.concatenate([[np.nan], np.sign(np.diff(close))])

    prev_max = _prior_extreme(close, HL_WINDOW - 1, np.max)
    prev_min = _prior_extreme(close, HL_WINDOW - 1, np.min)
    with np.errstate(invalid="ignore"):
        out["nh"] = np.where(np.isnan(prev_max), np.nan, (close > prev_max).astype(float))
        out["nl"] = np.where(np.isnan(prev_min), np.nan, (close < prev_min).astype(float))

    # Chaikin Money Flow, same formula as indicators/money_flow.py (zero range → multiplier 0)
    hl = np.nan_to_num(high - low)
    mfm = np.divide((close - low) - (high - close), hl, out=np.zeros_like(close), where=hl != 0)
    mfv_sum = _rolling_sum(np.nan_to_num(mfm * vol), CMF_WINDOW)
    vol_sum = _rolling_sum(vol, CMF_WINDOW)
    valid = np.isfinite(vol_sum) & (np.nan_to_num(vol_sum) > 0)
    cmf = np.divide(mfv_sum, vol_sum, out=np.zeros_like(close), where=valid)
    out["cmf"] = np.where(valid, (cmf > 0).astype(float), np.nan)
    return out


def _pct(num: float, den: float) -> Optional[float]:
    return round(float(num) / float(den) * 100, 1) if den else None


def _aggregate(dates: np.ndarray, flags: Dict[str, np.ndarray]) -> Dict[str, Dict[str, Any]]:
    """Flattened ticker-bars (parallel arrays) → {date: metrics}, one bincount per metric."""
    if dates is None or not len(dates):
        return {}
    days, inv = np.unique(dates, return_inverse=True)
    k = len(days)

    def total(x: np.ndarray) -> np.ndarray:
        return np.bincount(inv, weights=np.nan_to_num(np.asarray(x, dtype=float)), minlength=k)

    def counted(x: np.ndarray) -> np.ndarray:
        return np.bincount(inv, weights=np.isfinite(x).astype(float), minlength=k)

    n = np.bincount(inv, minlength=k)
    chg = flags["chg"]
    with np.errstate(invalid="ignore"):
        adv, dec, unch = total(chg > 0), total(chg < 0), total(chg == 0)
    pct = {key: (total(flags[col]), counted(flags[col])) for key, col in _FLAG_FOR_PCT.items()}
    nh, nl = total(flags["nh"]), total(flags["nl"])
    out: Dict[str, Dict[str, Any]] = {}
    for i, d in enumerate(days):
        m: Dict[str, Any] = {"n": int(n[i])}
        for key in ("pct_above_ema20", "pct_above_ema50", "pct_above_ema200"):
            m[key] = _pct(pct[key][0][i], pct[key][1][i])
        m.update({
            "advancers": int(adv[i]),
            "decliners": int(dec[i]),
            "unchanged": int(unch[i]),
            "new_high_20d": int(nh[i]),
            "new_low_20d": int(nl[i]),
            "pct_cmf_pos": _pct(pct["pct_cmf_pos"][0][i], pct["pct_cmf_pos"][1][i]),
        })
        out[str(d)] = m
    return out


def _empty_metrics() -> Dict[str, Any]:
    return {"n": 0, "pct_above_ema20": None, "pct_above_ema50": None, "pct_above_ema200": None,
            "advancers": 0, "decliners": 0, "unchanged": 0, "new_high_20d": 0, "new_low_20d": 0,
            "pct_cmf_pos": None}


def _concat(parts: List[Tuple[np.ndarray, Dict[str, np.ndarray]]]):
    dates = np.concatenate([p[0] for p in parts])
    flags = {k: np.concatenate([p[1][k] for p in parts]) for k in parts[0][1]}
    return dates, flags


def compute_for_date(frames: Dict[str, pd.DataFrame], date: Any) -> Dict[str, Any]:
    """Breadth metrics for one date, using only candles up to and including that date.

    A ticker counts only when it has a bar exactly on `date` (no bar = suspended / not listed yet).
    """
    day = _date_str(date)
    parts = []
    for df in (frames or {}).values():
        bars = _prep(df)
        if bars is None:
            continue
        upto = int(np.searchsorted(bars["date"], day, side="right"))
        if upto == 0 or bars["date"][upto - 1] != day:
            continue
        bars = {c: v[:upto] for c, v in bars.items()}
        f = _flags(bars)
        parts.append((bars["date"][-1:], {c: v[-1:] for c, v in f.items()}))
    if not parts:
        return _empty_metrics()
    return _aggregate(*_concat(parts)).get(day, _empty_metrics())


def compute_series(frames: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    """Metrics for every trading date in the frames (vectorized: series computed once per ticker)."""
    parts = []
    for df in (frames or {}).values():
        bars = _prep(df)
        if bars is not None:
            parts.append((bars["date"], _flags(bars)))
    if not parts:
        return {}
    by_date = _aggregate(*_concat(parts))
    if not by_date:
        return {}
    best = max(m["n"] for m in by_date.values())
    return {d: m for d, m in by_date.items() if m["n"] >= best * MIN_DATE_COVERAGE}


# ─── Storage ─────────────────────────────────────────────────────────────────

def load_frames(tickers: Iterable[str], limit: int = CANDLE_LIMIT) -> Dict[str, pd.DataFrame]:
    frames: Dict[str, pd.DataFrame] = {}
    for t in dict.fromkeys(t for t in (tickers or []) if t):
        try:
            rows = get_candles(t, limit=limit)
        except Exception as e:
            print(f"[Breadth] candles for {t} unavailable: {e}")
            continue
        if rows:
            frames[t] = pd.DataFrame(rows)
    return frames


def _store(market: str, by_date: Dict[str, Dict[str, Any]]) -> int:
    if not by_date:
        return 0
    _ensure_tables()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO market_breadth (market, date, metrics, updated_at) VALUES (?, ?, ?, ?)",
            [(market, d, json.dumps(m), now) for d, m in sorted(by_date.items())],
        )
        conn.commit()
    return len(by_date)


def backfill(market: str, tickers: Iterable[str], days: int = DEFAULT_DAYS,
             frames: Optional[Dict[str, pd.DataFrame]] = None) -> int:
    """Compute and store the last `days` trading dates from cached candles. Returns rows stored."""
    market = _market(market)
    series = compute_series(frames if frames is not None else load_frames(tickers))
    keep = sorted(series)[-max(1, int(days)):]
    return _store(market, {d: series[d] for d in keep})


def _stored_dates(market: str) -> List[str]:
    _ensure_tables()
    with get_connection() as conn:
        rows = conn.execute("SELECT date FROM market_breadth WHERE market = ? ORDER BY date", (market,)).fetchall()
    return [r["date"] for r in rows]


def update_today(market: str, tickers: Iterable[str],
                 frames: Optional[Dict[str, pd.DataFrame]] = None) -> Optional[Dict[str, Any]]:
    """End-of-scan hook: store the newest dates (backfills everything when the table is still empty).

    Returns the latest metrics with their date, or None when there are no candles. Never raises.
    """
    try:
        market = _market(market)
        series = compute_series(frames if frames is not None else load_frames(tickers))
        if not series:
            return None
        stored = _stored_dates(market)
        dates = sorted(series)
        if not stored:
            keep = dates[-DEFAULT_DAYS:]
        else:
            # Everything after the last stored date, plus the last few (today's bar may still have been live)
            keep = [d for d in dates if d > stored[-1]] + dates[-UPDATE_DAYS:]
        _store(market, {d: series[d] for d in set(keep)})
        last = dates[-1]
        return {"date": last, **series[last]}
    except Exception as e:
        print(f"[Breadth] update_today failed: {e}")
        return None


def compute_today(results: List[Dict[str, Any]], market: str) -> Optional[Dict[str, Any]]:
    """Same as update_today, with the tickers taken from scan result rows."""
    tickers = [r.get("ticker") for r in (results or []) if isinstance(r, dict) and r.get("ticker")]
    return update_today(market, tickers)


def history(market: str, days: int = DEFAULT_DAYS) -> List[Dict[str, Any]]:
    """Oldest → newest. `ad_line` = cumulative (advancers − decliners) from the first returned date."""
    _ensure_tables()
    market = _market(market)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, metrics FROM market_breadth WHERE market = ? ORDER BY date DESC LIMIT ?",
            (market, max(1, int(days))),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    ad = 0
    for r in reversed(rows):
        try:
            m = json.loads(r["metrics"] or "{}")
        except ValueError:
            continue
        ad += int(m.get("advancers") or 0) - int(m.get("decliners") or 0)
        out.append({"date": r["date"], **m, "ad_line": ad})
    return out


def latest(market: str) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    with get_connection() as conn:
        r = conn.execute(
            "SELECT date, metrics, updated_at FROM market_breadth WHERE market = ? ORDER BY date DESC LIMIT 1",
            (_market(market),),
        ).fetchone()
    if not r:
        return None
    try:
        return {"date": r["date"], **json.loads(r["metrics"] or "{}"), "updated_at": r["updated_at"]}
    except ValueError:
        return None


# ─── Plain-language reading ──────────────────────────────────────────────────

def classify(metrics: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """{code, text} from % above EMA50, e.g. {"WEAK", "Lemah (28% di atas EMA50)"}."""
    p = (metrics or {}).get("pct_above_ema50")
    if p is None:
        return {"code": "NO_DATA", "text": LABELS["NO_DATA"]}
    p = round(float(p))  # classify the number that is shown, so "30%" never reads as Lemah
    if p >= BREADTH_STRONG:
        code = "STRONG"
    elif p >= BREADTH_HEALTHY:
        code = "HEALTHY"
    elif p >= BREADTH_NEUTRAL:
        code = "NEUTRAL"
    elif p >= BREADTH_WEAK:
        code = "WEAK"
    else:
        code = "VERY_WEAK"
    return {"code": code, "text": f"{LABELS[code]} ({p}% di atas EMA50)"}


def label(metrics: Optional[Dict[str, Any]]) -> str:
    return classify(metrics)["text"]
