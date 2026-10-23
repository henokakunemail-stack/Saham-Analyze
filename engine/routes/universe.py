"""Coverage & control API: scan universe, market session, auto-scan mode, alerts (owned by: Coverage & Control)."""
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import universe, market_hours, notifications

router = APIRouter()


def _market(market: str) -> str:
    m = (market or "").strip().upper()
    if m not in universe.MARKETS:
        raise HTTPException(status_code=400, detail="market harus IDX atau US")
    return m


class UniversePut(BaseModel):
    added: List[str] = []
    removed_defaults: List[str] = []


class TickerBody(BaseModel):
    ticker: str


class AutoScanBody(BaseModel):
    mode: str


class MarkReadBody(BaseModel):
    ids: Optional[List[int]] = None
    all: bool = False


class AlertPrefsBody(BaseModel):
    kinds: Optional[Dict[str, bool]] = None
    os_toast: Optional[bool] = None


# ─── Universe ────────────────────────────────────────────────────────────────

@router.get("/api/universe")
def get_universe(market: str = "IDX"):
    return universe.describe(_market(market))


@router.put("/api/universe")
def put_universe(body: UniversePut, market: str = "IDX"):
    m = _market(market)
    res = universe.replace(m, body.added, body.removed_defaults)
    return {**universe.describe(m), "rejected": res["rejected"]}


@router.get("/api/universe/validate")
def validate_ticker(ticker: str, market: str = "IDX"):
    return universe.validate_ticker(ticker, _market(market))


@router.post("/api/universe/{market}/tickers")
def add_ticker(market: str, body: TickerBody):
    m = _market(market)
    res = universe.add_ticker(body.ticker, m)
    return {**res, "universe": universe.describe(m)}


@router.delete("/api/universe/{market}/tickers/{ticker}")
def remove_ticker(market: str, ticker: str):
    m = _market(market)
    res = universe.remove_ticker(ticker, m)
    return {**res, "universe": universe.describe(m)}


@router.post("/api/universe/{market}/reset")
def reset_universe(market: str):
    m = _market(market)
    universe.reset(m)
    return universe.describe(m)


# ─── Market session & auto-scan ──────────────────────────────────────────────

@router.get("/api/universe/session")
def get_session(market: Optional[str] = None):
    if market:
        return market_hours.session_status(_market(market))
    return {m: market_hours.session_status(m) for m in universe.MARKETS}


@router.get("/api/universe/autoscan")
def get_autoscan():
    return {"mode": market_hours.get_mode(), "modes": list(market_hours.MODES)}


@router.put("/api/universe/autoscan")
def put_autoscan(body: AutoScanBody):
    try:
        market_hours.set_mode(body.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"mode": market_hours.get_mode(), "modes": list(market_hours.MODES)}


# ─── Alerts ──────────────────────────────────────────────────────────────────

@router.get("/api/alerts")
def list_alerts(limit: int = 50, unread_only: bool = False, since_id: int = 0):
    return notifications.list_alerts(limit=limit, unread_only=unread_only, since_id=since_id)


@router.post("/api/alerts/read")
def mark_alerts_read(body: MarkReadBody):
    n = notifications.mark_read(body.ids, all_=body.all)
    return {"updated": n, "unread_count": notifications.list_alerts(limit=1)["unread_count"]}


@router.delete("/api/alerts")
def clear_alerts():
    return {"deleted": notifications.clear_alerts()}


@router.get("/api/alerts/prefs")
def get_alert_prefs():
    return notifications.get_prefs()


@router.put("/api/alerts/prefs")
def put_alert_prefs(body: AlertPrefsBody):
    return notifications.set_prefs(kinds=body.kinds, os_toast=body.os_toast)
