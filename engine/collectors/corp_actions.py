"""Stock splits and dividends from Yahoo, cached weekly in this module's own SQLite table.

    fetch_actions(ticker) -> {"splits": [{"date", "ratio"}], "dividends": [{"date", "amount"}]}
    fetch_splits(ticker)  -> [{"date", "ratio"}]
    splits_near(ticker, date, days=3) -> bool
    needs_refetch(ticker, cached_since_date) -> bool   (a split after the candle cache was written)

Never raises: on a network/parse failure the last cached answer (however old) is returned, or an
empty one; a failed ticker is not retried for FAIL_BACKOFF so a scan never waits on Yahoo twice.
Table corp_actions_cache is created on first use (like notifications._ensure_tables).
"""
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from ..db import get_connection

logger = logging.getLogger("saham.corp_actions")

CACHE_TTL = timedelta(days=7)
YF_TIMEOUT = 5            # seconds; one attempt only (actions are a nice-to-have, never block a scan)
FAIL_BACKOFF = 3600.0     # seconds before a failed ticker is tried again in this process

_init_lock = threading.Lock()
_initialized_for: Optional[str] = None
_failed_at: Dict[str, float] = {}


def _empty() -> Dict[str, List[Dict[str, Any]]]:
    return {"splits": [], "dividends": []}


def _ensure_tables() -> None:
    global _initialized_for
    from ..config import DB_PATH
    if _initialized_for == str(DB_PATH):
        return
    with _init_lock:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corp_actions_cache (
                    ticker TEXT PRIMARY KEY,
                    splits TEXT,
                    dividends TEXT,
                    fetched_at TEXT NOT NULL
                )
            """)
            conn.commit()
        _initialized_for = str(DB_PATH)


def _norm(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _day(value: Any) -> Optional[date]:
    try:
        ts = pd.Timestamp(str(value)[:10])
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts.date()


def _load(ticker: str) -> Optional[Dict[str, Any]]:
    _ensure_tables()
    with get_connection() as conn:
        row = conn.execute("SELECT splits, dividends, fetched_at FROM corp_actions_cache WHERE ticker = ?",
                           (ticker,)).fetchone()
    if not row:
        return None
    try:
        return {"splits": json.loads(row["splits"] or "[]"), "dividends": json.loads(row["dividends"] or "[]"),
                "fetched_at": row["fetched_at"]}
    except (ValueError, TypeError):
        return None


def _save(ticker: str, actions: Dict[str, List[Dict[str, Any]]], now: datetime) -> None:
    _ensure_tables()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO corp_actions_cache (ticker, splits, dividends, fetched_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                splits=excluded.splits, dividends=excluded.dividends, fetched_at=excluded.fetched_at
        """, (ticker, json.dumps(actions["splits"]), json.dumps(actions["dividends"]), now.isoformat()))
        conn.commit()


def _series_to_records(frame: pd.DataFrame, column: str, key: str) -> List[Dict[str, Any]]:
    if frame is None or column not in getattr(frame, "columns", []):
        return []
    out = []
    for idx, val in frame[column].items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v and v == v:  # non-zero, not NaN
            out.append({"date": pd.Timestamp(idx).strftime("%Y-%m-%d"), key: round(v, 6)})
    return sorted(out, key=lambda r: r["date"])


def _download(ticker: str) -> Dict[str, List[Dict[str, Any]]]:
    """Splits/dividends via yfinance (the same history call Ticker.actions makes, with a timeout)."""
    t = yf.Ticker(ticker)
    hist = t.history(period="max", interval="1d", actions=True, auto_adjust=False, timeout=YF_TIMEOUT)
    frame = hist if hist is not None and any(c in hist.columns for c in ("Stock Splits", "Dividends")) else t.actions
    return {"splits": _series_to_records(frame, "Stock Splits", "ratio"),
            "dividends": _series_to_records(frame, "Dividends", "amount")}


def fetch_actions(ticker: str, force: bool = False, now: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
    """{"splits": [{"date": "YYYY-MM-DD", "ratio": float}], "dividends": [{"date", "amount"}]}, oldest first.

    Served from the weekly cache when fresh; never raises."""
    ticker = _norm(ticker)
    if not ticker or ticker.startswith("^"):
        return _empty()
    now = now or datetime.now()
    cached = None
    try:
        cached = _load(ticker)
        if cached and not force:
            fetched = datetime.fromisoformat(cached["fetched_at"])
            if now - fetched < CACHE_TTL:
                return {"splits": cached["splits"], "dividends": cached["dividends"]}
    except Exception as e:
        logger.warning("corp_actions cache read failed for %s: %s", ticker, e)

    stale = {"splits": cached["splits"], "dividends": cached["dividends"]} if cached else _empty()
    if not force and time.monotonic() - _failed_at.get(ticker, -FAIL_BACKOFF) < FAIL_BACKOFF:
        return stale
    try:
        actions = _download(ticker)
    except Exception as e:
        _failed_at[ticker] = time.monotonic()
        logger.warning("corp_actions fetch failed for %s: %s", ticker, e)
        return stale
    _failed_at.pop(ticker, None)
    try:
        _save(ticker, actions, now)
    except Exception as e:
        logger.warning("corp_actions cache write failed for %s: %s", ticker, e)
    return actions


def fetch_splits(ticker: str) -> List[Dict[str, Any]]:
    return fetch_actions(ticker)["splits"]


def splits_near(ticker: str, when: Any, days: int = 3, splits: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Was there a split within ±days calendar days of `when`? (`splits` skips the lookup.)"""
    d = _day(when)
    if d is None:
        return False
    for s in fetch_splits(ticker) if splits is None else splits:
        sd = _day(s.get("date") if isinstance(s, dict) else s)
        if sd is not None and abs((sd - d).days) <= days:
            return True
    return False


def needs_refetch(ticker: str, cached_since_date: Any, splits: Optional[List[Dict[str, Any]]] = None,
                  today: Optional[date] = None) -> bool:
    """True when a split took effect after the candle cache was written (`cached_since_date`, e.g. the
    oldest candles.updated_at): those cached bars are then on the pre-split scale and the whole
    history must be downloaded again."""
    since = _day(cached_since_date)
    if since is None:
        return False
    today = today or date.today()
    for s in fetch_splits(ticker) if splits is None else splits:
        sd = _day(s.get("date") if isinstance(s, dict) else s)
        if sd is not None and since < sd <= today:
            return True
    return False
