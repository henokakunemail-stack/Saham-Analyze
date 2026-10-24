"""Data health per scan (Bagian 5): how much of the price data behind the list can be trusted.

Yahoo Finance is the only free source that answers automated requests (the IDX site refuses
them), and it occasionally returns nothing for a stock, a late bar, or odd ticks. The app
cannot repair the source; it can count the problems, show them, and hold the status of a stock
whose data is behind (actionability's fresh_ok gate).
"""
import json
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..db import get_setting, set_setting

KEY = "data_health_{}"
LOW_QUALITY = 80          # same line as the warning in the stock detail
MAX_LISTED = 30
SOURCE = {"IDX": "Yahoo Finance (harga tertunda ±10–15 menit saat bursa buka)",
          "US": "Yahoo Finance (harga hampir real-time saat bursa buka)"}
# Issue codes from collectors/data_quality.clean_ohlcv, in words
ISSUE_LABELS = {
    "ZERO_VOLUME": "volume nol", "DATE_GAP": "tanggal bolong", "PRICE_JUMP": "lompatan harga",
    "BAD_TICK": "harga salah sesaat", "INVALID_PRICE": "harga tidak valid", "DUPLICATE_DATE": "tanggal ganda",
    "HIGH_LOW_REPAIRED": "high/low diperbaiki", "SHORT_HISTORY": "riwayat pendek",
}


def _issue_codes(report: Optional[Dict[str, Any]]) -> List[str]:
    return [str(i.get("code")) for i in (report or {}).get("issues") or [] if i.get("code") and i.get("severity") != "info"]


def summarize(market: str, tickers: Iterable[str], rows: List[Dict[str, Any]],
              report_of: Callable[[str], Optional[Dict[str, Any]]], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Counts for one scan. `tickers` = what was asked for, `rows` = what came back analysed,
    `report_of(ticker)` = the stored quality report (with the time-dependent score)."""
    asked = list(dict.fromkeys(tickers))
    got = {r["ticker"] for r in rows if r.get("ticker")}
    failed = [t for t in asked if t not in got]

    stale, unknown, expected = [], 0, Counter()
    for r in rows:
        lag = r.get("data_lag")
        if not lag:
            unknown += 1
            continue
        expected[lag.get("expected")] += 1
        if int(lag.get("days") or 0) > 0:
            stale.append({"ticker": r["ticker"], "days": int(lag["days"]), "last_bar": lag.get("last_bar")})
    stale.sort(key=lambda s: (-s["days"], s["ticker"]))

    low, issues = [], Counter()
    for r in rows:
        rep = report_of(r["ticker"])
        if not rep:
            continue
        codes = _issue_codes(rep)
        issues.update(set(codes))
        score = rep.get("score")
        if score is not None and score < LOW_QUALITY:
            low.append({"ticker": r["ticker"], "score": int(score),
                        "issues": [ISSUE_LABELS.get(c, c.lower()) for c in dict.fromkeys(codes)]})
    low.sort(key=lambda x: (x["score"], x["ticker"]))

    fresh = len(rows) - len(stale) - unknown
    if unknown == len(rows):
        parts = [f"{len(rows)} dari {len(asked)} saham terbaca", "kesegaran diperiksa di scan berikutnya"]
    else:
        parts = [f"{fresh} dari {len(asked)} saham segar"] + ([f"{unknown} belum diperiksa"] if unknown else [])
    if stale:
        parts.append(f"{len(stale)} terlambat")
    if failed:
        parts.append(f"{len(failed)} gagal diunduh")
    if low:
        parts.append(f"{len(low)} kualitas rendah")
    return {
        "market": market,
        "scanned_at": (now or datetime.now()).isoformat(timespec="seconds"),
        "source": SOURCE.get(market, SOURCE["US"]),
        "expected_session": expected.most_common(1)[0][0] if expected else None,
        "asked": len(asked),
        "analysed": len(rows),
        "fresh": fresh,
        "unknown": unknown,
        "stale": stale[:MAX_LISTED],
        "stale_count": len(stale),
        "failed": failed[:MAX_LISTED],
        "failed_count": len(failed),
        "low_quality": low[:MAX_LISTED],
        "low_quality_count": len(low),
        "issues_by_type": {ISSUE_LABELS.get(c, c.lower()): n for c, n in issues.most_common()},
        "ok": not stale and not failed and not low and not unknown,
        "text": "Data: " + " · ".join(parts),
    }


def save(summary: Dict[str, Any]) -> None:
    set_setting(KEY.format(summary["market"]), json.dumps(summary))


def load(market: str) -> Optional[Dict[str, Any]]:
    raw = get_setting(KEY.format(market), "")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def plan_date(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Date of the closing plan a scan produced: the newest final-bar date, provided most rows
    share it. A few stale stocks no longer block the day's snapshot (they are TUNGGU through
    fresh_ok and their older date is ignored); while Yahoo is mid-update (newest date not yet the
    majority) there is no plan date and the next scan records it."""
    dates = [str((r.get("levels") or {}).get("as_of") or "")[:10] for r in rows
             if (r.get("levels") or {}).get("bar_final") and not (r.get("levels") or {}).get("frozen")]
    dates = [d for d in dates if d]
    if not dates:
        return None
    newest = max(dates)
    return newest if dates.count(newest) * 2 > len(dates) else None
