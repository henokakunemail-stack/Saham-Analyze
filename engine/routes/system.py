"""System / data-quality API (owned by: Technical Quality)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..db import get_data_quality_report, get_data_quality_reports
from ..collectors.data_quality import with_staleness
from ..collectors.market_data import fetch_stock_ohlcv, normalize_ticker

router = APIRouter()


@router.get("/api/system/info")
def get_system_info():
    return {"service": "SAHAM Analytical Engine"}


@router.get("/api/system/data-quality")
def get_data_quality(
    ticker: Optional[str] = Query(None, description="Single ticker, e.g. BBCA or BBCA.JK"),
    market: str = Query("IDX", pattern="^(IDX|US)$"),
    refresh: bool = False,
):
    """Latest OHLCV data-quality report(s). Staleness/score are recomputed against the current time.

    Without ticker: {summary, reports[]} sorted worst score first.
    With ticker: one report (404 if the ticker was never loaded); refresh=true re-downloads first.
    """
    if ticker:
        candidates = [ticker.strip().upper(), normalize_ticker(ticker, market)]
        if refresh:
            fetch_stock_ohlcv(candidates[1], period="1y", force_refresh=True)
        for t in candidates:
            report = get_data_quality_report(t)
            if report:
                return with_staleness(report)
        raise HTTPException(status_code=404, detail=f"Belum ada laporan kualitas data untuk {ticker}")

    reports = sorted((with_staleness(r) for r in get_data_quality_reports()), key=lambda r: (r["score"], r["ticker"]))
    scores = [r["score"] for r in reports]
    return {
        "summary": {
            "tickers": len(reports),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "stale_count": sum(1 for r in reports if r["is_stale"]),
            "poor_count": sum(1 for r in reports if r["grade"] == "POOR"),
            "issue_counts": _issue_counts(reports),
        },
        "reports": reports,
    }


def _issue_counts(reports):
    counts = {}
    for r in reports:
        for it in r.get("issues", []):
            counts[it["code"]] = counts.get(it["code"], 0) + 1
    return counts
