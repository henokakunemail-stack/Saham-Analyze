"""Track record of AI signal validations.

Every successful "Validasi AI" is stored with the AI's verdict, the engine's own verdict and
plan (entry/stop/TP1) and the price at that moment. After HORIZON trading days the outcome is
measured from the daily candles: return, return vs the index, and whether TP1 or the stop was
hit first. The summary compares the AI's verdicts with the engine's on the same validations,
so it shows whether asking the AI actually adds anything.
"""
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from ..db import get_connection

HORIZON = 10  # trading days
BUY_VERDICTS = ("STRONG_BUY", "SPECULATIVE_BUY")
MIN_SAMPLE = 20  # below this the summary is labelled as too small to judge

_init_lock = threading.Lock()
_initialized_for: Optional[str] = None


def _ensure_table() -> None:
    global _initialized_for
    from ..config import DB_PATH
    if _initialized_for == str(DB_PATH):
        return
    with _init_lock:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    ai_verdict TEXT,
                    confidence INTEGER,
                    bull_trap_risk TEXT,
                    price REAL,
                    engine_score REAL,
                    engine_verdict TEXT,
                    market_mode TEXT,
                    entry_low REAL, entry_high REAL, stop_loss REAL, target_tp1 REAL,
                    ai_levels TEXT,
                    outcome TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_validations_market ON ai_validations(market, trade_date)")
            conn.commit()
        _initialized_for = str(DB_PATH)


def record(ticker: str, market: str, result: Dict[str, Any], composite: Dict[str, Any], price: float,
           provider: str, trade_date: str) -> Optional[int]:
    """Store one successful validation (errors are not recorded)."""
    if not result.get("ok") or not result.get("verdict"):
        return None
    _ensure_table()
    ai_levels = {k: result.get(k) for k in ("entry_zone", "stop_loss", "target_tp1", "target_tp2")}
    try:
        confidence = int(result.get("confidence_score") or 0)
    except (TypeError, ValueError):
        confidence = None
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO ai_validations (created_at, trade_date, ticker, market, provider, model, ai_verdict,
                confidence, bull_trap_risk, price, engine_score, engine_verdict, market_mode,
                entry_low, entry_high, stop_loss, target_tp1, ai_levels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().astimezone().isoformat(timespec="seconds"), trade_date, ticker, market, provider,
              result.get("model_used"), str(result.get("verdict")).strip().upper(), confidence,
              result.get("bull_trap_risk"), float(price or 0), composite.get("score"), composite.get("verdict"),
              composite.get("market_mode"), composite.get("entry_low"), composite.get("entry_high"),
              composite.get("stop_loss"), composite.get("target_tp1"), json.dumps(ai_levels)))
        conn.commit()
        return cur.lastrowid


def measure(row: Dict[str, Any], df: pd.DataFrame, index_df: Optional[pd.DataFrame],
            horizon: int = HORIZON) -> Dict[str, Any]:
    """Outcome of one validation from the candles after its trade date (partial while young)."""
    dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    after = df[dates > row["trade_date"]].head(horizon)
    days = len(after)
    if days == 0 or not row.get("price"):
        return {"days": 0, "final": False}
    price = float(row["price"])
    ret = (float(after["close"].iloc[-1]) / price - 1) * 100
    first_hit = None
    sl, tp1 = row.get("stop_loss"), row.get("target_tp1")
    if sl and tp1:
        for _, bar in after.iterrows():
            if bar["low"] <= sl:          # a bar touching both counts as the stop (conservative)
                first_hit = "SL"
                break
            if bar["high"] >= tp1:
                first_hit = "TP1"
                break
    out = {"days": days, "final": days >= horizon, "return_pct": round(ret, 2), "first_hit": first_hit}
    if index_df is not None and not index_df.empty:
        idates = pd.to_datetime(index_df["date"]).dt.strftime("%Y-%m-%d")
        base = index_df[idates <= row["trade_date"]]
        span = index_df[(idates > row["trade_date"]) & (idates <= after["date"].astype(str).str[:10].iloc[-1])]
        if not base.empty and not span.empty:
            iret = (float(span["close"].iloc[-1]) / float(base["close"].iloc[-1]) - 1) * 100
            out["index_return_pct"] = round(iret, 2)
            out["excess_pct"] = round(ret - iret, 2)
    return out


def _rows(market: str, limit: int = 500) -> List[Dict[str, Any]]:
    _ensure_table()
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM ai_validations WHERE market = ? ORDER BY created_at DESC LIMIT ?",
                           (market, limit))
        return [dict(r) for r in cur.fetchall()]


def _save_outcome(row_id: int, outcome: Dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE ai_validations SET outcome = ? WHERE id = ?", (json.dumps(outcome), row_id))
        conn.commit()


def _group(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r.get(key) or "-", []).append(r)
    out = []
    for name, items in groups.items():
        done = [r["outcome"] for r in items if r.get("outcome") and r["outcome"].get("final")]
        rets = [o["return_pct"] for o in done]
        excess = [o["excess_pct"] for o in done if "excess_pct" in o]
        hits = [o["first_hit"] for o in done if o.get("first_hit")]
        out.append({
            "verdict": name,
            "count": len(items),
            "evaluated": len(done),
            "avg_return_pct": round(sum(rets) / len(rets), 2) if rets else None,
            "avg_excess_pct": round(sum(excess) / len(excess), 2) if excess else None,
            "win_rate_pct": round(100 * sum(1 for x in rets if x > 0) / len(rets), 1) if rets else None,
            "tp1_first_pct": round(100 * hits.count("TP1") / len(hits), 1) if hits else None,
        })
    return sorted(out, key=lambda g: -g["count"])


def summary(market: str, load_df, index_df: Optional[pd.DataFrame], horizon: int = HORIZON) -> Dict[str, Any]:
    """Grouped results by AI verdict and by engine verdict, plus the latest validations.

    `load_df(ticker)` returns that ticker's daily candles. Final outcomes are stored once;
    younger validations are measured on the fly so their progress is visible."""
    rows = _rows(market)
    # One validation per ticker, day and model counts (repeat clicks would inflate the sample)
    seen, unique = set(), []
    for r in rows:
        k = (r["ticker"], r["trade_date"], r.get("model"))
        if k not in seen:
            seen.add(k)
            unique.append(r)
    cache: Dict[str, pd.DataFrame] = {}
    for r in unique:
        stored = json.loads(r["outcome"]) if r.get("outcome") else None
        if stored and stored.get("final"):
            r["outcome"] = stored
            continue
        if r["ticker"] not in cache:
            try:
                cache[r["ticker"]] = load_df(r["ticker"])
            except Exception:
                cache[r["ticker"]] = pd.DataFrame()
        df = cache[r["ticker"]]
        r["outcome"] = measure(r, df, index_df, horizon) if not df.empty else {"days": 0, "final": False}
        if r["outcome"].get("final"):
            _save_outcome(r["id"], r["outcome"])
    evaluated = sum(1 for r in unique if r["outcome"].get("final"))
    return {
        "market": market,
        "horizon_days": horizon,
        "total": len(unique),
        "evaluated": evaluated,
        "enough_data": evaluated >= MIN_SAMPLE,
        "min_sample": MIN_SAMPLE,
        "by_ai_verdict": _group(unique, "ai_verdict"),
        "by_engine_verdict": _group(unique, "engine_verdict"),
        "recent": [{k: r.get(k) for k in ("id", "created_at", "trade_date", "ticker", "model", "ai_verdict",
                                           "confidence", "engine_verdict", "engine_score", "price",
                                           "stop_loss", "target_tp1", "outcome")} for r in unique[:30]],
    }
