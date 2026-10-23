"""Scan universe (owned by: Coverage & Control).

Contract used by engine.main._run_scan:
    get_scan_universe(market) -> list of tickers to scan

The universe of a market = default list (minus the defaults the user removed)
+ tickers the user added + every watchlist ticker of that market, normalized,
de-duplicated and capped at MAX_UNIVERSE to protect the yfinance quota.
When the cap bites, watchlist and user-added tickers win over defaults.

Persisted per market in app_settings under "universe_<MARKET>" as JSON:
    {"added": ["ABCD.JK", ...], "removed_defaults": ["GOTO.JK", ...]}
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Dict, List, Optional, Tuple

from .config import DEFAULT_IDX_TICKERS, DEFAULT_US_TICKERS
from .db import get_setting, set_setting, get_watchlist, get_candles
from .collectors.market_data import normalize_ticker

MAX_UNIVERSE = 200  # daily candles are fetched in batches (market_data.prefetch_daily)
MARKETS = ("IDX", "US")
VALIDATE_TIMEOUT_SEC = 8.0

_IDX_RE = re.compile(r"^[A-Z0-9]{2,6}\.JK$")
_US_RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


def _market(market: str) -> str:
    m = (market or "IDX").strip().upper()
    return m if m in MARKETS else "IDX"


def _setting_key(market: str) -> str:
    return f"universe_{_market(market)}"


def default_tickers(market: str) -> List[str]:
    return list(DEFAULT_IDX_TICKERS if _market(market) == "IDX" else DEFAULT_US_TICKERS)


def _dedupe(items: List[str]) -> List[str]:
    seen, out = set(), []
    for t in items:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_config(market: str) -> Dict[str, List[str]]:
    market = _market(market)
    try:
        raw = json.loads(get_setting(_setting_key(market), "") or "{}")
    except (ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    added = [normalize_ticker(str(t), market) for t in raw.get("added", []) if str(t).strip()]
    removed = [normalize_ticker(str(t), market) for t in raw.get("removed_defaults", []) if str(t).strip()]
    return {"added": _dedupe(added), "removed_defaults": _dedupe(removed)}


def save_config(market: str, added: List[str], removed_defaults: List[str]) -> None:
    market = _market(market)
    defaults = set(default_tickers(market))
    added_n = _dedupe([normalize_ticker(t, market) for t in added if t and t.strip()])
    removed_n = _dedupe([normalize_ticker(t, market) for t in removed_defaults if t and t.strip()])
    cfg = {
        # A ticker that is a default never needs to sit in "added"
        "added": [t for t in added_n if t not in defaults],
        "removed_defaults": [t for t in removed_n if t in defaults],
    }
    set_setting(_setting_key(market), json.dumps(cfg))


def _row_market(row: Dict[str, Any]) -> str:
    m = (row.get("market") or "").strip().upper()
    if m in MARKETS:
        return m
    return "IDX" if str(row.get("ticker", "")).upper().endswith(".JK") else "US"


def watchlist_tickers(market: str) -> List[str]:
    market = _market(market)
    try:
        rows = get_watchlist()
    except Exception as e:
        print(f"[Universe] watchlist read failed: {e}")
        return []
    return _dedupe([
        normalize_ticker(str(r["ticker"]), market)
        for r in rows
        if r.get("ticker") and _row_market(r) == market
    ])


def _merge(market: str) -> Tuple[List[str], List[str]]:
    """Return (capped universe, full uncapped list) in priority order."""
    market = _market(market)
    cfg = load_config(market)
    removed = set(cfg["removed_defaults"])
    defaults = [t for t in default_tickers(market) if t not in removed]
    full = _dedupe(watchlist_tickers(market) + cfg["added"] + defaults)
    return full[:MAX_UNIVERSE], full


def get_scan_universe(market: str) -> List[str]:
    try:
        return _merge(market)[0]
    except Exception as e:
        # Never break a scan over settings trouble: fall back to the built-in list
        print(f"[Universe] falling back to defaults: {e}")
        return default_tickers(market)


def describe(market: str) -> Dict[str, Any]:
    """Everything the settings UI needs for one market."""
    market = _market(market)
    cfg = load_config(market)
    tickers, full = _merge(market)
    wl = set(watchlist_tickers(market))
    added = set(cfg["added"])
    removed = set(cfg["removed_defaults"])
    in_scan = set(tickers)

    items = []
    for t in full:
        sources = []
        if t in wl:
            sources.append("watchlist")
        if t in added:
            sources.append("user")
        if t in set(default_tickers(market)):
            sources.append("default")
        items.append({"ticker": t, "sources": sources, "scanned": t in in_scan})

    return {
        "market": market,
        "tickers": tickers,
        "items": items,
        "defaults": [{"ticker": t, "removed": t in removed} for t in default_tickers(market)],
        "added": cfg["added"],
        "removed_defaults": cfg["removed_defaults"],
        "watchlist": sorted(wl),
        "count": len(tickers),
        "total_requested": len(full),
        "limit": MAX_UNIVERSE,
        "truncated": len(full) > MAX_UNIVERSE,
    }


# ─── Validation ──────────────────────────────────────────────────────────────

def format_ok(ticker: str, market: str) -> bool:
    return bool((_IDX_RE if _market(market) == "IDX" else _US_RE).match(ticker))


def _yf_has_data(ticker: str) -> bool:
    import yfinance as yf
    df = yf.Ticker(ticker).history(period="5d", interval="1d")
    return df is not None and not df.empty


def ticker_exists(ticker: str, timeout: float = VALIDATE_TIMEOUT_SEC) -> Optional[bool]:
    """True/False when we know, None when the check timed out or the network failed."""
    try:
        if get_candles(ticker, limit=1):
            return True
    except Exception:
        pass
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return bool(pool.submit(_yf_has_data, ticker).result(timeout=timeout))
    except FutureTimeout:
        return None
    except Exception as e:
        print(f"[Universe] validate {ticker} failed: {e}")
        return None
    finally:
        pool.shutdown(wait=False)


def validate_ticker(raw: str, market: str) -> Dict[str, Any]:
    market = _market(market)
    raw = (raw or "").strip().upper()
    if not raw or raw.startswith("^"):
        return {"ok": False, "ticker": raw, "message": "Kode saham tidak valid."}
    ticker = normalize_ticker(raw, market)
    if not format_ok(ticker, market):
        hint = "contoh: BBCA atau BBCA.JK" if market == "IDX" else "contoh: AAPL atau BRK-B"
        return {"ok": False, "ticker": ticker, "message": f"Format kode tidak dikenali ({hint})."}
    exists = ticker_exists(ticker)
    if exists is None:
        return {"ok": False, "ticker": ticker,
                "message": "Tidak bisa memeriksa kode ke Yahoo Finance (timeout/jaringan). Coba lagi."}
    if not exists:
        return {"ok": False, "ticker": ticker, "message": f"{ticker} tidak ditemukan di Yahoo Finance."}
    return {"ok": True, "ticker": ticker, "message": f"{ticker} valid."}


# ─── Mutations used by the API ───────────────────────────────────────────────

def add_ticker(raw: str, market: str) -> Dict[str, Any]:
    market = _market(market)
    ticker = normalize_ticker((raw or "").strip().upper() or "-", market)
    cfg = load_config(market)
    _, full = _merge(market)

    if ticker in default_tickers(market) and ticker in cfg["removed_defaults"]:
        # Re-adding a removed default needs no network check
        cfg["removed_defaults"].remove(ticker)
        save_config(market, cfg["added"], cfg["removed_defaults"])
        return {"ok": True, "ticker": ticker, "message": f"{ticker} dikembalikan ke daftar scan."}
    if ticker in full:
        return {"ok": False, "ticker": ticker, "message": f"{ticker} sudah ada di daftar scan."}
    if len(full) >= MAX_UNIVERSE:
        return {"ok": False, "ticker": ticker,
                "message": f"Batas {MAX_UNIVERSE} saham tercapai. Hapus beberapa saham dulu."}

    check = validate_ticker(raw, market)
    if not check["ok"]:
        return check
    save_config(market, cfg["added"] + [check["ticker"]], cfg["removed_defaults"])
    return {"ok": True, "ticker": check["ticker"], "message": f"{check['ticker']} ditambahkan ke daftar scan."}


def remove_ticker(raw: str, market: str) -> Dict[str, Any]:
    market = _market(market)
    ticker = normalize_ticker(raw, market)
    cfg = load_config(market)
    changed = False
    if ticker in cfg["added"]:
        cfg["added"].remove(ticker)
        changed = True
    if ticker in default_tickers(market) and ticker not in cfg["removed_defaults"]:
        cfg["removed_defaults"].append(ticker)
        changed = True
    if changed:
        save_config(market, cfg["added"], cfg["removed_defaults"])
    if ticker in watchlist_tickers(market):
        return {"ok": changed, "ticker": ticker,
                "message": f"{ticker} ada di Watchlist dan tetap di-scan. Hapus dari Watchlist untuk berhenti memindainya."}
    if not changed:
        return {"ok": False, "ticker": ticker, "message": f"{ticker} tidak ada di daftar scan."}
    return {"ok": True, "ticker": ticker, "message": f"{ticker} dihapus dari daftar scan."}


def reset(market: str) -> None:
    save_config(market, [], [])


def replace(market: str, added: List[str], removed_defaults: List[str]) -> Dict[str, Any]:
    """PUT semantics: newly added tickers are validated, the rest stored as given."""
    market = _market(market)
    current = load_config(market)
    known = set(current["added"]) | set(default_tickers(market)) | set(watchlist_tickers(market))
    final_added, rejected = [], []
    for raw in _dedupe([str(t).strip().upper() for t in added if str(t).strip()]):
        t = normalize_ticker(raw, market)
        if t in known:
            final_added.append(t)
            continue
        check = validate_ticker(raw, market)
        if check["ok"]:
            final_added.append(check["ticker"])
        else:
            rejected.append(check)
    removed = [normalize_ticker(t, market) for t in removed_defaults if str(t).strip()]
    full_len = len(_dedupe(watchlist_tickers(market) + final_added
                           + [t for t in default_tickers(market) if t not in set(removed)]))
    if full_len > MAX_UNIVERSE:
        rejected.append({"ok": False, "ticker": "",
                         "message": f"Total {full_len} melebihi batas {MAX_UNIVERSE}; kelebihan tidak akan di-scan."})
    save_config(market, final_added, removed)
    return {"rejected": rejected}
