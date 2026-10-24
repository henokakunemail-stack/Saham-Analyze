"""Market breadth & sector strength API (Fase 4, display only)."""
import threading
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from .. import market_breadth, sectors
from ..db import get_screener_results

router = APIRouter()

MARKETS = ("IDX", "US")
_backfill_lock = threading.Lock()


def _market(market: str) -> str:
    m = (market or "IDX").strip().upper()
    return m if m in MARKETS else "IDX"


def _universe(market: str) -> List[str]:
    from ..universe import get_scan_universe
    return get_scan_universe(market)


@router.get("/api/market/breadth")
def get_breadth(market: str = "IDX", days: int = Query(market_breadth.DEFAULT_DAYS, ge=1, le=400)):
    market = _market(market)
    hist = market_breadth.history(market, days)
    if not hist:
        # First call: build the history from cached candles (one at a time; a few seconds)
        with _backfill_lock:
            hist = market_breadth.history(market, days)
            if not hist:
                try:
                    market_breadth.backfill(market, _universe(market), days=max(days, market_breadth.DEFAULT_DAYS))
                except Exception as e:
                    print(f"[Breadth] backfill failed: {e}")
                hist = market_breadth.history(market, days)
    last = market_breadth.latest(market)
    reading = market_breadth.classify(last)
    return {"market": market, "latest": last, "label": reading["text"], "label_code": reading["code"],
            "history": hist}


@router.get("/api/market/sectors")
def get_sectors(market: str = "IDX"):
    market = _market(market)
    rows = get_screener_results(market)
    tickers = [r["ticker"] for r in rows if r.get("ticker")]
    refreshing = False
    missing: List[str] = []
    try:
        missing = sectors.missing_or_stale(tickers, market)
        if missing:
            refreshing = sectors.refresh_async(missing, market) or sectors.is_refreshing()
    except Exception as e:
        print(f"[Sectors] refresh check failed: {e}")
    lookup = sectors.sectors_for(tickers, market)
    strength = sectors.sector_strength(rows, market, lookup)
    updated = max((str(r.get("updated_at") or "") for r in rows), default="") or None
    body: Dict[str, Any] = {"market": market, "sectors": strength, "updated_at": updated,
                            "missing": len(missing), "refreshing": bool(refreshing)}
    return body


@router.get("/api/data/health")
def get_data_health(market: str = "IDX"):
    """Data health of the latest scan: fresh / late / failed downloads / low quality (Bagian 5).
    Before the first scan with this build, it is rebuilt from the stored rows (failed downloads unknown)."""
    from ..collectors.data_quality import with_staleness
    from ..db import get_data_quality_report
    from ..screener import data_health
    market = _market(market)
    stored = data_health.load(market)
    if stored:
        return stored
    rows = get_screener_results(market=market)
    if not rows:
        return {"market": market, "available": False}
    out = data_health.summarize(market, [r["ticker"] for r in rows], rows,
                                lambda t: with_staleness(rep) if (rep := get_data_quality_report(t)) else None)
    out["rebuilt"] = True
    return out
