"""Speed & feedback API: live scan progress (owned by: Speed & Feedback)."""
from fastapi import APIRouter, Query

from .. import scan_progress

router = APIRouter()


@router.get("/api/screener/progress")
def get_scan_progress(include_results: bool = Query(True, description="Include partial results of finished tickers")):
    """Live scan state: counts, ETA, last error and (optionally) partial results sorted by score."""
    return scan_progress.snapshot(include_results=include_results)
