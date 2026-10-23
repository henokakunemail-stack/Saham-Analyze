"""Live scan progress (owned by: Speed & Feedback).

Contract used by engine.main._run_scan:
    start(market, total)        -- a scan begins over `total` tickers
    tick(ticker, result|None)   -- one ticker finished (None = failed / no data)
    finish(error=None)          -- scan ended (error message if it crashed)
    snapshot() -> dict          -- current state for the API / UI

Besides counters it keeps the result dicts of finished tickers (sorted by score) so the
UI can stream rows into the screener table while a scan is still running, plus a simple
ETA estimate based on the average time per finished ticker.
"""
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_results: List[Dict[str, Any]] = []
_failed_tickers: List[str] = []
_t0: Optional[float] = None
_state: Dict[str, Any] = {
    "active": False, "market": None, "total": 0, "done": 0, "failed": 0,
    "current_ticker": None, "started_at": None, "finished_at": None,
    "elapsed_sec": 0.0, "eta_sec": None, "error": None, "last_error": None,
    "phase": None, "phase_label": None,
}


def start(market: str, total: int) -> None:
    global _t0
    with _lock:
        _results.clear()
        _failed_tickers.clear()
        _t0 = time.monotonic()
        _state.update(active=True, market=market, total=max(int(total or 0), 0), done=0, failed=0,
                      current_ticker=None, started_at=datetime.now().isoformat(), finished_at=None,
                      elapsed_sec=0.0, eta_sec=None, error=None, last_error=None,
                      phase="prepare", phase_label="Menyiapkan berita & data pasar")


def set_phase(code: str, label: str) -> None:
    """What the scan is doing now, shown in the progress bar (so a slow step never looks stuck)."""
    with _lock:
        _state.update(phase=code, phase_label=label)


def tick(ticker: str, result: Optional[Dict[str, Any]]) -> None:
    with _lock:
        _state["done"] += 1
        _state["current_ticker"] = ticker
        if result is None:
            _state["failed"] += 1
            _failed_tickers.append(ticker)
            _state["last_error"] = f"Data {ticker} tidak tersedia atau gagal dianalisis"
        else:
            _results.append(result)
            _results.sort(key=lambda r: r.get("score") or 0, reverse=True)


def finish(error: Optional[str] = None) -> None:
    with _lock:
        _state.update(active=False, finished_at=datetime.now().isoformat(), error=error,
                      elapsed_sec=_elapsed(), eta_sec=0 if error is None else None, phase="done", phase_label=None)
        if error:
            _state["last_error"] = error


def _elapsed() -> float:
    return round(time.monotonic() - _t0, 1) if _t0 is not None else 0.0


def _eta(done: int, total: int, elapsed: float) -> Optional[int]:
    """Seconds left, extrapolated from the average time per finished ticker."""
    if done <= 0 or total <= 0:
        return None
    remaining = max(total - done, 0)
    return int(round(elapsed / done * remaining))


def snapshot(include_results: bool = True) -> Dict[str, Any]:
    with _lock:
        snap = dict(_state)
        if snap["active"]:
            snap["elapsed_sec"] = _elapsed()
            snap["eta_sec"] = _eta(snap["done"], snap["total"], snap["elapsed_sec"])
        total = snap["total"]
        snap["percent"] = round(snap["done"] / total * 100, 1) if total else (100.0 if not snap["active"] else 0.0)
        snap["failed_tickers"] = list(_failed_tickers)
        snap["result_count"] = len(_results)
        if include_results:
            snap["results"] = [dict(r) for r in _results]
        return snap
