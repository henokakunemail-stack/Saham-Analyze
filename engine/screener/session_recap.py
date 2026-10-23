"""What the last session did to the plans that were in force during it (shown after the close).

During the session the checkpoint compares the live price with the plan from the previous close.
After the close the stored plans are already the next session's, so this module rebuilds the plan
the session traded against (the frame without its last bar) and reads that bar against it: did the
price come down to the buy limit, reach TP1/TP2, or hit the cut loss?

The Top 10 of each closing plan is remembered (setting plan_top_<market>) so the recap covers the
list the user actually saw, not the new one built from the close.
"""
import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..db import get_setting, set_setting

KEEP_DAYS = 7
CACHE_SEC = 900
OUTCOME_ORDER = ("STOP", "TP2", "TP1", "FILLED", "ZONE", "ABOVE")

_cache: Dict[Tuple, Tuple[float, Dict[str, Any]]] = {}


def _key(market: str) -> str:
    return f"plan_top_{market}"


def save_plan_list(market: str, plan_date: str, tickers: List[str]) -> None:
    """Remember the Top 10 of a closing plan (keyed by the close the plan was built from)."""
    try:
        stored = json.loads(get_setting(_key(market), "") or "{}")
    except (ValueError, TypeError):
        stored = {}
    stored[plan_date] = list(tickers)
    for d in sorted(stored)[:-KEEP_DAYS]:
        stored.pop(d, None)
    set_setting(_key(market), json.dumps(stored))


def plan_list_before(market: str, session_date: str) -> Tuple[Optional[str], List[str]]:
    """(plan date, tickers) of the latest stored closing plan made before `session_date`."""
    try:
        stored = json.loads(get_setting(_key(market), "") or "{}")
    except (ValueError, TypeError):
        return None, []
    earlier = [d for d in stored if d < session_date]
    if not earlier:
        return None, []
    d = max(earlier)
    return d, list(stored[d])


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") if abs(v) >= 100 else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def read_bar(lv: Dict[str, Any], bar: Dict[str, float]) -> Tuple[str, str, bool]:
    """(outcome code, plain sentence, buy limit reached) for one session bar against a plan."""
    o, h, lo, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
    el, eh, sl = float(lv["entry_low"]), float(lv["entry_high"]), float(lv["stop_loss"])
    tp1, tp2 = float(lv["target_tp1"]), float(lv["target_tp2"])
    rec = float(lv.get("recommended_entry") or eh)
    if o <= sl:
        return "STOP", f"Dibuka {_fmt(o)}, sudah di bawah cut loss {_fmt(sl)} — rencana batal, tidak ada entry", False
    filled = lo <= rec
    if lo <= sl:
        if filled:
            return "STOP", (f"Turun ke harga beli {_fmt(rec)} lalu terus ke cut loss {_fmt(sl)} — "
                            f"posisi yang terbeli kena cut loss"), True
        return "STOP", f"Menyentuh cut loss {_fmt(sl)} — rencana batal", False
    for code, tp, name in (("TP2", tp2, "TP2"), ("TP1", tp1, "TP1")):
        if h >= tp:
            if filled:
                return code, (f"Sempat turun ke harga beli {_fmt(rec)} (terendah {_fmt(lo)}) dan naik ke "
                              f"{name} {_fmt(tp)} — urutan dalam hari tidak diketahui"), True
            return code, (f"Naik ke {name} {_fmt(tp)} tanpa turun ke harga beli {_fmt(rec)} — "
                          f"order limit tidak terisi"), False
    if filled:
        return "FILLED", (f"Harga beli {_fmt(rec)} tercapai (terendah {_fmt(lo)}), tutup {_fmt(c)} — "
                          f"posisi berjalan: cut loss {_fmt(sl)}, TP1 {_fmt(tp1)}"), True
    if lo <= eh:
        return "ZONE", (f"Masuk zona beli (terendah {_fmt(lo)}) tetapi tidak sampai harga beli {_fmt(rec)} — "
                        f"order limit belum terisi"), False
    return "ABOVE", f"Tidak turun ke zona beli (terendah {_fmt(lo)}, zona {_fmt(el)}–{_fmt(eh)}) — tidak ada entry", False


def recap(market: str, picks: Dict[str, str], fetch: Callable[[str], pd.DataFrame],
          plan_fn: Callable[[pd.DataFrame], Dict[str, Any]], final_fn: Callable[[str], Optional[bool]],
          workers: int = 6) -> Dict[str, Any]:
    """Rows for `picks` ({ticker: source}); `plan_fn(frame)` returns the levels a frame produces."""
    from concurrent.futures import ThreadPoolExecutor

    def one(item: Tuple[str, str]) -> Optional[Dict[str, Any]]:
        ticker, source = item
        df = fetch(ticker)
        if df is None or len(df) < 70 or "date" not in df.columns:
            return None
        bar = df.iloc[-1]
        lv = plan_fn(df.iloc[:-1].reset_index(drop=True))
        if not lv or not lv.get("entry_high"):
            return None
        code, text, filled = read_bar(lv, bar)
        prev = float(df["close"].iloc[-2])
        close = float(bar["close"])
        return {"ticker": ticker, "source": source, "outcome": code, "text": text, "filled": filled,
                "session_date": str(bar["date"])[:10], "plan_as_of": lv.get("as_of"),
                "open": float(bar["open"]), "high": float(bar["high"]), "low": float(bar["low"]),
                "close": close, "change_pct": round((close / prev - 1) * 100, 2) if prev else None,
                "entry_low": lv["entry_low"], "entry_high": lv["entry_high"],
                "recommended_entry": lv.get("recommended_entry"), "stop_loss": lv["stop_loss"],
                "target_tp1": lv["target_tp1"], "target_tp2": lv["target_tp2"]}

    key = (market, tuple(sorted(picks.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SEC:
        return hit[1]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [r for r in pool.map(one, picks.items()) if r]
    session_dates = sorted({r["session_date"] for r in rows})
    session_date = session_dates[-1] if session_dates else None
    rows = [r for r in rows if r["session_date"] == session_date]   # a stock without today's bar is not part of it
    rows.sort(key=lambda r: (OUTCOME_ORDER.index(r["outcome"]), r["ticker"]))
    counts = {c: sum(1 for r in rows if r["outcome"] == c) for c in OUTCOME_ORDER}
    out = {"session_date": session_date, "final": final_fn(session_date) if session_date else None,
           "plan_as_of": rows[0]["plan_as_of"] if rows else None, "rows": rows, "counts": counts,
           "filled": sum(1 for r in rows if r["filled"])}
    _cache[key] = (time.time(), out)
    if len(_cache) > 50:
        _cache.clear()
    return out
