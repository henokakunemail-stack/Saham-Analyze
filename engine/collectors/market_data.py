"""Market Data Collector using yfinance with SQLite local caching."""
import logging
import random
import time
import yfinance as yf
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
from ..db import save_candles, get_candles, save_data_quality_report, get_data_quality_report
from .data_quality import clean_ohlcv, last_closed_session, is_session_open

logger = logging.getLogger("saham.market_data")

# Per-request timeout (seconds) and retry policy for yfinance calls
YF_TIMEOUT = 10
YF_RETRIES = 3
YF_BACKOFF = 1.5
INTRADAY_INTERVALS = ["1m", "2m", "5m", "15m", "30m", "60m", "1h"]
# While a session is live the cached daily bar is re-fetched after this many seconds
LIVE_BAR_TTL = 240  # Yahoo lags ~15 min anyway; a 100+ stock scan must not refetch mid-way


class NoDataError(Exception):
    """yfinance answered but returned no rows (bad/delisted ticker, or no bars for the period)."""


def normalize_ticker(ticker: str, market: str = "IDX") -> str:
    ticker = ticker.strip().upper()
    if market == "IDX" and not ticker.endswith(".JK") and not ticker.startswith("^"):
        return f"{ticker}.JK"
    return ticker


def _yf_history(symbol: str, **kwargs) -> pd.DataFrame:
    """yfinance history with a per-call timeout and retry/backoff on network errors.

    Raises NoDataError when Yahoo answers with an empty frame (not retried: it is an answer,
    not a failure) and re-raises the last exception after YF_RETRIES failed attempts.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, YF_RETRIES + 1):
        try:
            hist = yf.Ticker(symbol).history(timeout=YF_TIMEOUT, **kwargs)
            if hist is None or hist.empty:
                raise NoDataError(f"no price data returned for {symbol}")
            return hist
        except NoDataError:
            raise
        except Exception as e:
            last_exc = e
            rate_limited = "rate" in type(e).__name__.lower() or "too many requests" in str(e).lower()
            if attempt < YF_RETRIES:
                delay = YF_BACKOFF * (2 ** (attempt - 1)) * (3 if rate_limited else 1) + random.uniform(0, 0.5)
                logger.warning("yfinance network error for %s (attempt %d/%d): %s; retrying in %.1fs",
                               symbol, attempt, YF_RETRIES, e, delay)
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _parse_updated_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # save_candles writes naive local time
    return dt if dt.tzinfo else dt.astimezone()


def is_daily_cache_fresh(ticker: str, last_updated_at: Optional[str], now: Optional[datetime] = None) -> bool:
    """Whether cached daily candles can be served without hitting yfinance.

    The cache is fresh when it was fetched after the most recent session's bar became final
    (close + settle buffer, in the exchange's own time zone). A bar fetched intraday is therefore
    never served as final after the close, the next morning, or over the weekend. While a session
    is live the partial bar is re-fetched every LIVE_BAR_TTL seconds. If a weekday was an exchange
    holiday, a fetch made after its "close" still counts, so holidays don't cause refetch loops.
    """
    updated = _parse_updated_at(last_updated_at)
    if updated is None:
        return False
    now_aware = (now if (now and now.tzinfo) else (now.astimezone() if now else datetime.now().astimezone()))
    if updated < last_closed_session(ticker, now_aware):
        return False
    if is_session_open(ticker, now_aware):
        return (now_aware - updated).total_seconds() <= LIVE_BAR_TTL
    return True


def _store_report(ticker: str, report: Dict[str, Any], source: str) -> None:
    try:
        report = dict(report, source=source)
        save_data_quality_report(ticker, report)
    except Exception as e:  # reporting must never break data loading
        logger.warning("could not store data-quality report for %s: %s", ticker, e)


def _clean_daily(ticker: str, df: pd.DataFrame, source: str, store: bool = True) -> pd.DataFrame:
    clean, report = clean_ohlcv(df, ticker=ticker, interval="1d")
    if store:
        _store_report(ticker, report, source)
    return clean


def fetch_stock_ohlcv(ticker: str, period: str = "1y", interval: str = "1d", force_refresh: bool = False,
                      fresh_since: Optional[datetime] = None) -> pd.DataFrame:
    """Fetch OHLCV candles, checking SQLite cache first before yfinance network call.

    `fresh_since`: a scan's start time. Bars written by that scan's batch download count as fresh
    for the rest of the scan, so a long scan never re-downloads stocks one by one when the live-bar
    TTL runs out halfway (that cascade made scans take 15+ minutes).

    Returns a DataFrame with date/open/high/low/close/volume (empty on total failure). Daily data
    is cleaned (see data_quality.clean_ohlcv) and a quality report per ticker is stored.
    """
    is_intraday = interval in INTRADAY_INTERVALS

    # ponytail: daily bars cached in SQLite; intraday calls fetch direct from yfinance
    if not is_intraday and not force_refresh:
        cached = get_candles(ticker, limit=260)
        # A cache built from a shorter period must not satisfy a request for longer history
        min_bars = 200 if period in ("1y", "2y", "3y", "5y", "max") else 30
        stamp = _parse_updated_at(cached[-1].get("updated_at")) if cached else None
        this_scan = fresh_since is not None and stamp is not None and stamp >= fresh_since
        if cached and len(cached) >= min_bars and (this_scan or is_daily_cache_fresh(ticker, cached[-1].get("updated_at"))):
            df = pd.DataFrame(cached)
            # Cached rows were cleaned when stored, but older caches predate the checks
            df = _clean_daily(ticker, df, "cache", store=get_data_quality_report(ticker) is None)
            if len(df) >= min_bars:
                df['date'] = pd.to_datetime(df['date'])
                return df

    # Fetch from yfinance
    try:
        effective_period = "5d" if is_intraday else period
        hist = _yf_history(ticker, period=effective_period, interval=interval, auto_adjust=True)

        rows = []
        for index, row in hist.iterrows():
            # Format time: unix timestamp in seconds for intraday, YYYY-MM-DD for daily
            time_val = int(index.timestamp()) if is_intraday else index.strftime("%Y-%m-%d")
            rows.append({
                "date": time_val,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume", 0)
            })
        raw = pd.DataFrame(rows)

        if is_intraday:
            clean, _ = clean_ohlcv(raw, ticker=ticker, interval=interval)
            return clean

        df = _clean_daily(ticker, raw, "network")
        if not df.empty:
            save_candles(ticker, df.to_dict("records"))
        return df
    except NoDataError as e:
        logger.info("No data for %s (%s %s): %s", ticker, period, interval, e)
    except Exception as e:
        logger.error("Network failure fetching %s from yfinance after %d attempts: %s", ticker, YF_RETRIES, e)

    # Fallback to local cache even if slightly old (daily only: daily rows would corrupt an intraday chart)
    if not is_intraday:
        cached = get_candles(ticker, limit=260)
        if cached:
            logger.info("Serving cached candles for %s (last bar %s)", ticker, cached[-1]["date"])
            return _clean_daily(ticker, pd.DataFrame(cached), "cache_fallback")
    return pd.DataFrame()


PREFETCH_BATCH = 50
# After one full download of the day, later scans only need the last few bars
INCREMENTAL_PERIOD = "5d"
FULL_HISTORY_BARS = 200


def _full_refresh_today(cached: List[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """A full download rewrites every bar; an incremental one only the last few. So an older
    bar stamped today means the whole history was refreshed today (dividend adjustments included)."""
    if len(cached) < FULL_HISTORY_BARS:
        return False
    stamp = _parse_updated_at(cached[-30].get("updated_at"))
    return bool(stamp) and stamp.date() == (now or datetime.now().astimezone()).date()


def _download_batch(symbols: List[str], period: str) -> pd.DataFrame:
    return yf.download(symbols, period=period, interval="1d", group_by="ticker", auto_adjust=True,
                       threads=True, progress=False, timeout=YF_TIMEOUT * 3)


def prefetch_daily(tickers: List[str], period: str = "1y", force: bool = False, min_bars: int = 0) -> Dict[str, int]:
    """Refresh many tickers' daily candles with a few batched Yahoo requests instead of one
    request per ticker, so scanning 100+ stocks stays inside Yahoo's rate limits. Tickers whose
    cache is already fresh (and, with `min_bars`, long enough) are skipped; anything that fails
    here is fetched one by one later."""
    full, incremental = [], []
    for t in tickers:
        cached = get_candles(t, limit=max(FULL_HISTORY_BARS, min_bars))
        if (force or not cached or len(cached) < min_bars
                or not is_daily_cache_fresh(t, cached[-1].get("updated_at"))):
            (incremental if not min_bars and _full_refresh_today(cached) else full).append(t)
    saved = 0
    for group, per in ((full, period), (incremental, INCREMENTAL_PERIOD)):
        saved += _download_and_store(group, per, store_report=per == period)
    return {"requested": len(tickers), "downloaded": len(full) + len(incremental),
            "full": len(full), "incremental": len(incremental), "saved": saved}


def _download_and_store(need: List[str], period: str, store_report: bool = True) -> int:
    saved = 0
    for i in range(0, len(need), PREFETCH_BATCH):
        chunk = need[i:i + PREFETCH_BATCH]
        try:
            data = _download_batch(chunk, period)
        except Exception as e:
            logger.warning("batch download failed (%d tickers): %s", len(chunk), e)
            continue
        if data is None or data.empty:
            continue
        for t in chunk:
            try:
                frame = data[t] if isinstance(data.columns, pd.MultiIndex) else data
                frame = frame.dropna(subset=["Close"])
            except KeyError:
                continue
            if frame.empty:
                continue
            raw = pd.DataFrame({
                "date": [ix.strftime("%Y-%m-%d") for ix in frame.index],
                "open": frame["Open"].values, "high": frame["High"].values, "low": frame["Low"].values,
                "close": frame["Close"].values, "volume": frame["Volume"].fillna(0).values,
            })
            # A 5-bar frame says nothing about the history: keep the full download's quality report
            df = _clean_daily(t, raw, "network", store=store_report)
            if not df.empty:
                save_candles(t, df.to_dict("records"))
                saved += 1
    return saved


def fetch_market_indices() -> Dict[str, Dict[str, Any]]:
    """Fetch macro market summary: IHSG, S&P 500, USD/IDR."""
    indices = {
        "IHSG": "^JKSE",
        "S&P 500": "^GSPC",
        "USD/IDR": "USDIDR=X"
    }
    summary = {}
    for label, symbol in indices.items():
        try:
            hist = _yf_history(symbol, period="5d")
            hist = hist[hist["Close"].notna() & (hist["Close"] > 0)]
            if not hist.empty and len(hist) >= 2:
                curr = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                chg_pct = round(((curr - prev) / prev) * 100, 2)
                summary[label] = {
                    "price": round(curr, 2),
                    "change_pct": chg_pct,
                    "symbol": symbol
                }
            elif not hist.empty:
                curr = float(hist["Close"].iloc[-1])
                summary[label] = {
                    "price": round(curr, 2),
                    "change_pct": 0.0,
                    "symbol": symbol
                }
        except Exception as e:
            summary[label] = {"price": 0.0, "change_pct": 0.0, "symbol": symbol, "error": str(e)}
    return summary
