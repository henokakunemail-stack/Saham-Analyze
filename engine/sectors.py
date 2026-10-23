"""Sectors (owned by: Fase 4 — breadth & sektor).

Yahoo Finance sector/industry per ticker, cached weekly in the module's own table `ticker_sectors`
(the raw Yahoo strings are stored; the Indonesian label is mapped at read time, so editing
engine/data/sector_map.json takes effect without refetching). Lookup order for a label:

    overrides[ticker] → industries[Yahoo industry] → sectors[Yahoo sector] → "Lainnya"

Entry points:
    sector_of(ticker, market) -> label                   one ticker (one DB read)
    sectors_for(tickers, market) -> {ticker: label}      bulk (one DB read)
    missing_or_stale(tickers, market, max_age_days) -> [ticker]
    refresh(tickers, market, max_age_days=7) -> summary  fetch Yahoo info for missing/stale tickers; never raises
    refresh_async(tickers, market)                       same, in a background thread (one at a time)
    sector_strength(results, market) -> [{sector, count, median_ret_1m, ..., rank}]
    annotate(results, market) -> strength list           adds row["sector"], row["sector_rank"] in place
    concentration(tickers, results_or_lookup, min_count=3) -> [{sector, tickers}]

Display only for now (Tahap A): nothing here changes scores.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from functools import lru_cache
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .config import BASE_DIR, get_resource_path
from .db import get_connection
from .collectors.market_data import normalize_ticker

UNKNOWN = "Lainnya"
MAX_AGE_DAYS = 7
MAX_WORKERS = 4                 # Yahoo .info is heavy and rate limited: keep the pool small
REFRESH_BUDGET_SEC = 120.0      # stop waiting for the whole batch after this long (stragglers are dropped)
MIN_RANK_COUNT = 2              # sectors with fewer stocks are ranked after the others (a median of one is noise)

# Fallback when sector_map.json is missing (e.g. not bundled in a frozen build)
_FALLBACK_MAP = {
    "unknown": UNKNOWN,
    "sectors": {
        "Energy": "Energi", "Basic Materials": "Barang Baku", "Industrials": "Perindustrian",
        "Consumer Defensive": "Konsumen Primer", "Consumer Cyclical": "Konsumen Non-Primer",
        "Healthcare": "Kesehatan", "Financial Services": "Keuangan", "Real Estate": "Properti & Real Estat",
        "Technology": "Teknologi", "Communication Services": "Infrastruktur", "Utilities": "Infrastruktur",
    },
    "industries": {},
    "overrides": {},
}

_initialized_for: Optional[str] = None
_init_lock = threading.Lock()
_refresh_lock = threading.Lock()


def _ensure_tables() -> None:
    global _initialized_for
    from .config import DB_PATH
    if _initialized_for == str(DB_PATH):
        return
    with _init_lock:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticker_sectors (
                    ticker TEXT PRIMARY KEY,
                    sector TEXT,
                    industry TEXT,
                    source TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
        _initialized_for = str(DB_PATH)


def _market(market: Optional[str]) -> str:
    return (market or "IDX").strip().upper() or "IDX"


def _norm(ticker: str, market: str) -> str:
    return normalize_ticker(str(ticker), _market(market))


# ─── Map ─────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_map() -> Dict[str, Any]:
    for path in (get_resource_path("engine/data/sector_map.json"), BASE_DIR / "data" / "sector_map.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("sectors"), dict):
                data.setdefault("industries", {})
                data.setdefault("overrides", {})
                data.setdefault("unknown", UNKNOWN)
                return data
        except (OSError, ValueError):
            continue
    print("[Sectors] sector_map.json not found, using the built-in map")
    return _FALLBACK_MAP


def map_label(yahoo_sector: Optional[str], yahoo_industry: Optional[str] = None,
              ticker: Optional[str] = None) -> str:
    """Indonesian label for Yahoo's sector/industry (override by ticker first)."""
    m = load_map()
    if ticker and ticker in m["overrides"]:
        return m["overrides"][ticker]
    if yahoo_industry and yahoo_industry in m["industries"]:
        return m["industries"][yahoo_industry]
    if yahoo_sector and yahoo_sector in m["sectors"]:
        return m["sectors"][yahoo_sector]
    return m.get("unknown") or UNKNOWN


# ─── Cache ───────────────────────────────────────────────────────────────────

def _cached_rows(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    _ensure_tables()
    if not tickers:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with get_connection() as conn:
        for i in range(0, len(tickers), 500):
            chunk = tickers[i:i + 500]
            q = f"SELECT * FROM ticker_sectors WHERE ticker IN ({','.join('?' * len(chunk))})"
            for r in conn.execute(q, chunk).fetchall():
                out[r["ticker"]] = dict(r)
    return out


def _save(ticker: str, sector: Optional[str], industry: Optional[str], source: str) -> None:
    _ensure_tables()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO ticker_sectors (ticker, sector, industry, source, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET sector=excluded.sector, industry=excluded.industry,
                source=excluded.source, updated_at=excluded.updated_at
        """, (ticker, sector, industry, source, datetime.now().isoformat()))
        conn.commit()


def sectors_for(tickers: Iterable[str], market: str = "IDX") -> Dict[str, str]:
    """{ticker (as given): Indonesian label} from cache + overrides; unknown → "Lainnya"."""
    given = [t for t in (tickers or []) if t]
    norm = {t: _norm(t, market) for t in given}
    try:
        rows = _cached_rows(sorted(set(norm.values())))
    except Exception as e:
        print(f"[Sectors] cache read failed: {e}")
        rows = {}
    out: Dict[str, str] = {}
    for t, n in norm.items():
        r = rows.get(n) or {}
        out[t] = map_label(r.get("sector"), r.get("industry"), n)
    return out


def sector_of(ticker: str, market: str = "IDX") -> str:
    return sectors_for([ticker], market).get(ticker, UNKNOWN)


def missing_or_stale(tickers: Iterable[str], market: str = "IDX", max_age_days: float = MAX_AGE_DAYS) -> List[str]:
    """Normalized tickers without a cached row, or with one older than max_age_days (overrides never need Yahoo)."""
    overrides = load_map()["overrides"]
    norm = [n for n in dict.fromkeys(_norm(t, market) for t in (tickers or []) if t) if n not in overrides]
    rows = _cached_rows(norm)
    cutoff = datetime.now() - timedelta(days=max_age_days)
    out = []
    for n in norm:
        r = rows.get(n)
        try:
            fresh = r is not None and datetime.fromisoformat(r["updated_at"]) >= cutoff
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            out.append(n)
    return out


# ─── Yahoo refresh ───────────────────────────────────────────────────────────

def _fetch_info(ticker: str) -> Tuple[Optional[str], Optional[str]]:
    """(sector, industry) from Yahoo. Raises on network/parse failure."""
    import yfinance as yf
    info = yf.Ticker(ticker).info or {}
    sector = (info.get("sector") or info.get("sectorDisp") or "").strip() or None
    industry = (info.get("industry") or info.get("industryDisp") or "").strip() or None
    return sector, industry


def refresh(tickers: Iterable[str], market: str = "IDX", max_age_days: float = MAX_AGE_DAYS,
            budget_sec: float = REFRESH_BUDGET_SEC) -> Dict[str, Any]:
    """Fetch Yahoo sector/industry for missing or stale tickers. Never raises; failures are skipped
    (retried next time). A ticker Yahoo answers for without a sector is cached as unknown for a week."""
    summary = {"requested": 0, "fetched": 0, "unknown": 0, "failed": 0, "timed_out": 0}
    try:
        todo = missing_or_stale(tickers, market, max_age_days)
    except Exception as e:
        print(f"[Sectors] refresh skipped: {e}")
        return summary
    summary["requested"] = len(todo)
    if not todo:
        return summary
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="sectors")
    futures = {pool.submit(_fetch_info, t): t for t in todo}
    done = set()
    try:
        for fut in as_completed(futures, timeout=budget_sec):
            t = futures[fut]
            done.add(t)
            try:
                sector, industry = fut.result()
            except Exception as e:
                summary["failed"] += 1
                print(f"[Sectors] {t}: {e}")
                continue
            try:
                _save(t, sector, industry, "yahoo")
            except Exception as e:
                summary["failed"] += 1
                print(f"[Sectors] could not cache {t}: {e}")
                continue
            summary["fetched"] += 1
            if not sector:
                summary["unknown"] += 1
    except FutureTimeout:
        summary["timed_out"] = len(todo) - len(done)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return summary


def refresh_async(tickers: Iterable[str], market: str = "IDX", max_age_days: float = MAX_AGE_DAYS) -> bool:
    """Start refresh() in a daemon thread unless one is already running. Returns True when started."""
    if not _refresh_lock.acquire(blocking=False):
        return False
    tickers = list(tickers or [])

    def run():
        try:
            refresh(tickers, market, max_age_days)
        finally:
            _refresh_lock.release()

    try:
        threading.Thread(target=run, name="sectors-refresh", daemon=True).start()
    except Exception:
        _refresh_lock.release()
        return False
    return True


def is_refreshing() -> bool:
    return _refresh_lock.locked()


# ─── Sector strength & concentration ─────────────────────────────────────────

def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _med(values: List[Optional[float]], digits: int = 2) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(float(median(vals)), digits) if vals else None


def _row_sector(row: Dict[str, Any], lookup: Dict[str, str]) -> str:
    return row.get("sector") or lookup.get(row.get("ticker"), UNKNOWN) or UNKNOWN


def strength_key(s: Dict[str, Any]) -> tuple:
    """Ranking composite (best first): known sector, ≥ MIN_RANK_COUNT stocks, then median 3-month return,
    then % above EMA50 (breadth), then median 1-month return; missing values sort last."""
    def desc(v):
        return (v is None, -(v or 0.0))
    return (s["sector"] == UNKNOWN, s["count"] < MIN_RANK_COUNT,
            desc(s.get("median_ret_3m")), desc(s.get("pct_above_ema50")), desc(s.get("median_ret_1m")), s["sector"])


def sector_strength(results: List[Dict[str, Any]], market: str = "IDX",
                    lookup: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Per sector: count, median_ret_1m/3m (%), pct_above_ema50 (price > row ema50), median_score,
    layak (rows with action.status == "LAYAK"), tickers (best score first), rank 1..N ("Lainnya": rank None, last).

    Rows: {ticker, price, score, ema50, screen{ret_1m, ret_3m}, action{status}?, sector?}. A row's own
    `sector` wins; otherwise `lookup` (ticker → label) or the cache is used."""
    rows = [r for r in (results or []) if isinstance(r, dict) and r.get("ticker")]
    if lookup is None:
        need = [r["ticker"] for r in rows if not r.get("sector")]
        lookup = sectors_for(need, market) if need else {}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(_row_sector(r, lookup), []).append(r)

    out: List[Dict[str, Any]] = []
    for sector, members in groups.items():
        screens = [m.get("screen") or {} for m in members]
        ema_pairs = [(_num(m.get("price")), _num(m.get("ema50"))) for m in members]
        ema_pairs = [(p, e) for p, e in ema_pairs if p and e and p > 0 and e > 0]
        members_sorted = sorted(members, key=lambda m: -(_num(m.get("score")) or 0.0))
        out.append({
            "sector": sector,
            "count": len(members),
            "median_ret_1m": _med([_num(s.get("ret_1m")) for s in screens]),
            "median_ret_3m": _med([_num(s.get("ret_3m")) for s in screens]),
            "pct_above_ema50": round(sum(p > e for p, e in ema_pairs) / len(ema_pairs) * 100, 1) if ema_pairs else None,
            "median_score": _med([_num(m.get("score")) for m in members], 1),
            "layak": sum(1 for m in members if ((m.get("action") or {}).get("status") == "LAYAK")),
            "tickers": [m["ticker"] for m in members_sorted],
        })
    out.sort(key=strength_key)
    rank = 0
    for s in out:
        if s["sector"] == UNKNOWN:
            s["rank"] = None
        else:
            rank += 1
            s["rank"] = rank
    return out


def annotate(results: List[Dict[str, Any]], market: str = "IDX") -> List[Dict[str, Any]]:
    """Add `sector` and `sector_rank` to each scan row in place; returns the sector_strength list."""
    rows = [r for r in (results or []) if isinstance(r, dict) and r.get("ticker")]
    try:
        lookup = sectors_for([r["ticker"] for r in rows], market)
        for r in rows:
            r["sector"] = lookup.get(r["ticker"], UNKNOWN)
        strength = sector_strength(rows, market, lookup)
        ranks = {s["sector"]: s["rank"] for s in strength}
        for r in rows:
            r["sector_rank"] = ranks.get(r["sector"])
        return strength
    except Exception as e:
        print(f"[Sectors] annotate failed: {e}")
        return []


def concentration(tickers: Iterable[str],
                  results_or_sector_lookup: Union[List[Dict[str, Any]], Dict[str, str], None] = None,
                  min_count: int = 3, market: str = "IDX", include_unknown: bool = False) -> List[Dict[str, Any]]:
    """Sectors holding ≥ min_count of `tickers` (e.g. Top 10 or watchlist), most crowded first.

    Second argument: scan rows (their `sector`, else the cache), a {ticker: label} dict, or None (cache).
    "Lainnya" is left out unless include_unknown — a pile of unclassified stocks is not a concentration."""
    given = list(dict.fromkeys(t for t in (tickers or []) if t))
    src = results_or_sector_lookup
    lookup: Dict[str, str] = {}
    if isinstance(src, dict):
        lookup = dict(src)
    elif isinstance(src, list):
        lookup = {r["ticker"]: r["sector"] for r in src if isinstance(r, dict) and r.get("ticker") and r.get("sector")}
    missing = [t for t in given if t not in lookup]
    if missing:
        lookup.update(sectors_for(missing, market))
    groups: Dict[str, List[str]] = {}
    for t in given:
        groups.setdefault(lookup.get(t) or UNKNOWN, []).append(t)
    out = [{"sector": s, "tickers": ts} for s, ts in groups.items()
           if len(ts) >= min_count and (include_unknown or s != UNKNOWN)]
    out.sort(key=lambda g: (-len(g["tickers"]), g["sector"]))
    return out
