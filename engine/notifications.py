"""Alerts after each scan (owned by: Coverage & Control).

Contract used by engine.main._run_scan:
    on_scan_complete(market, results) -- called after every successful scan; must not raise

Each scan is compared with the previous one (table alert_state, one row per market+ticker):
    breakout       new confirmed breakout
    strong_bullish verdict upgraded to STRONG_BULLISH
    stop_loss      watchlist stock fell through the previous scan's stop_loss
    target_hit     watchlist stock reached the previous scan's target_tp1
    outflow        watchlist stock's money flow flipped to STRONG_OUTFLOW
    entry_zone     watchlist / Top 10 stock's live price came down into the buy zone of its frozen plan
                   (levels.frozen + levels.live, see screener/trade_levels.plan_position); once per plan
A ticker seen for the first time only records state (no alert flood on first scan), except entry_zone,
which reads the live position against today's plan and remembers the plan it alerted on
(alert_state.entry_low/entry_high/entry_as_of).
Preferences in app_settings "alert_prefs": {"kinds": {kind: bool}, "os_toast": bool}.
"""
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .db import get_connection, get_setting, set_setting, get_watchlist
from .collectors.market_data import normalize_ticker

KINDS: Dict[str, str] = {
    "breakout": "Breakout terkonfirmasi",
    "strong_bullish": "Naik ke STRONG BULLISH",
    "stop_loss": "Watchlist tembus Stop Loss",
    "target_hit": "Watchlist capai Target TP1",
    "outflow": "Watchlist: uang keluar masif",
    "entry_zone": "Harga masuk zona beli",
}
# Off unless the user turns them on: they fire for every scanned stock, and a fresh breakout /
# verdict upgrade is a chase signal the pullback strategy does not act on (54 breakout alerts in
# two days in one real install — noise that buries the alerts that matter)
DEFAULT_OFF = ("breakout", "strong_bullish")
PREFS_KEY = "alert_prefs"
COOLDOWN = timedelta(hours=12)  # same ticker+kind is not repeated within this window
MAX_ALERTS_KEPT = 300
ENTRY_TOP_N = 10  # entry_zone also watches today's Top N (besides the watchlist)
# Columns added after the first release of alert_state (migrated in _ensure_tables)
_STATE_EXTRA_COLS = {"entry_low": "REAL", "entry_high": "REAL", "entry_as_of": "TEXT"}

_init_lock = threading.Lock()
_initialized_for: Optional[str] = None


def _ensure_tables() -> None:
    global _initialized_for
    from .config import DB_PATH
    if _initialized_for == str(DB_PATH):
        return
    with _init_lock:
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_state (
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    verdict TEXT,
                    is_confirmed_breakout INTEGER,
                    money_flow_status TEXT,
                    price REAL,
                    stop_loss REAL,
                    target_tp1 REAL,
                    updated_at TEXT,
                    PRIMARY KEY (market, ticker)
                )
            """)
            have = {r[1] for r in conn.execute("PRAGMA table_info(alert_state)").fetchall()}
            for col, typ in _STATE_EXTRA_COLS.items():
                if col not in have:
                    conn.execute(f"ALTER TABLE alert_state ADD COLUMN {col} {typ}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    market TEXT,
                    ticker TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT,
                    message TEXT,
                    is_read INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker_kind ON alerts(ticker, kind, created_at)")
            conn.commit()
        _initialized_for = str(DB_PATH)


# ─── Preferences ─────────────────────────────────────────────────────────────

def get_prefs() -> Dict[str, Any]:
    try:
        raw = json.loads(get_setting(PREFS_KEY, "") or "{}")
    except (ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    kinds_raw = raw.get("kinds") if isinstance(raw.get("kinds"), dict) else {}
    return {
        "kinds": {k: bool(kinds_raw.get(k, k not in DEFAULT_OFF)) for k in KINDS},
        "os_toast": bool(raw.get("os_toast", False)),
        "labels": dict(KINDS),
    }


def set_prefs(kinds: Optional[Dict[str, bool]] = None, os_toast: Optional[bool] = None) -> Dict[str, Any]:
    cur = get_prefs()
    if kinds:
        for k, v in kinds.items():
            if k in KINDS:
                cur["kinds"][k] = bool(v)
    if os_toast is not None:
        cur["os_toast"] = bool(os_toast)
    set_setting(PREFS_KEY, json.dumps({"kinds": cur["kinds"], "os_toast": cur["os_toast"]}))
    return get_prefs()


# ─── Detection (pure) ────────────────────────────────────────────────────────

def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def entry_reached(lv: Dict[str, Any], live: Dict[str, Any], status: Optional[str] = None) -> bool:
    """The buy limit (recommended entry — what the backtest fills at) was reached today, the price
    is still above the cut loss and the stop was not touched. Shared by the in-app bell and Telegram."""
    if status == "HINDARI" or live.get("touched_stop") or live.get("status") == "BELOW_STOP":
        return False
    limit = _f(lv.get("recommended_entry")) or _f(lv.get("entry_high"))
    low = live.get("day_low")
    return low is not None and _f(low) <= limit and _f(live.get("price")) > _f(lv.get("stop_loss"))


def _fmt_price(v: float, market: str) -> str:
    from .telegram.messages import num   # one number format app-wide (IDX "3.150", US "12,50")
    return num(v, market)


def detect_alerts(
    market: str,
    results: List[Dict[str, Any]],
    prev_state: Dict[str, Dict[str, Any]],
    watchlist: set,
) -> List[Dict[str, Any]]:
    """Compare a scan with the previous state. Returns alert dicts (ticker, kind, title, message)."""
    out: List[Dict[str, Any]] = []
    for r in results:
        t = r.get("ticker")
        prev = prev_state.get(t) if t else None
        if not prev:
            continue
        price = _f(r.get("price"))
        verdict = r.get("verdict") or ""
        flow = r.get("money_flow_status") or ""
        score = r.get("score")

        if r.get("is_confirmed_breakout") and not prev.get("is_confirmed_breakout"):
            out.append({"ticker": t, "kind": "breakout", "title": f"{t}: breakout terkonfirmasi",
                        "message": f"Harga {_fmt_price(price, market)} menembus resisten dengan konfirmasi volume (skor {score})."})

        if verdict == "STRONG_BULLISH" and prev.get("verdict") != "STRONG_BULLISH":
            out.append({"ticker": t, "kind": "strong_bullish", "title": f"{t}: naik ke STRONG BULLISH",
                        "message": f"Verdict berubah dari {prev.get('verdict') or '-'} ke STRONG_BULLISH (skor {score})."})

        if t in watchlist and price > 0:
            prev_price = _f(prev.get("price"))
            sl = _f(prev.get("stop_loss"))
            tp1 = _f(prev.get("target_tp1"))
            # Today's high/low of a frozen plan catch touches between two scans (5 min apart)
            live = ((r.get("levels") or {}).get("live") or {}) if (r.get("levels") or {}).get("frozen") else {}
            if sl > 0 and (prev_price > sl >= price or (live.get("touched_stop") and prev_price > sl)):
                out.append({"ticker": t, "kind": "stop_loss", "title": f"{t}: tembus Stop Loss",
                            "message": f"Harga {_fmt_price(price, market)} (terendah hari ini {_fmt_price(_f(live.get('day_low')) or price, market)}) "
                                       f"menyentuh stop loss {_fmt_price(sl, market)}. Pertimbangkan cut loss."})
            if tp1 > 0 and (prev_price < tp1 <= price or (live.get("touched_tp1") and prev_price < tp1)):
                out.append({"ticker": t, "kind": "target_hit", "title": f"{t}: capai Target TP1",
                            "message": f"Harga {_fmt_price(price, market)} (tertinggi hari ini {_fmt_price(_f(live.get('day_high')) or price, market)}) "
                                       f"mencapai target TP1 {_fmt_price(tp1, market)}. Jual separuh & naikkan cut loss ke harga beli, sisanya incar TP2."})
            if flow == "STRONG_OUTFLOW" and prev.get("money_flow_status") != "STRONG_OUTFLOW":
                out.append({"ticker": t, "kind": "outflow", "title": f"{t}: uang keluar masif",
                            "message": "Aliran dana berbalik menjadi STRONG_OUTFLOW (distribusi). Waspadai tekanan jual."})
    return out


def _same_price(a: Any, b: Any) -> bool:
    fa, fb = _f(a), _f(b)
    return fa > 0 and fb > 0 and abs(fa - fb) <= max(abs(fa), abs(fb)) * 1e-6


def _top_n(results: List[Dict[str, Any]], n: int = ENTRY_TOP_N) -> set:
    """Today's Top N: by `rank` when the scan wrote one, else by score."""
    ranked = [r for r in results if isinstance(r.get("rank"), int) and not isinstance(r.get("rank"), bool)]
    if ranked:
        return {r["ticker"] for r in ranked if 1 <= r["rank"] <= n}
    by_score = sorted(results, key=lambda r: _f(r.get("score")), reverse=True)
    return {r["ticker"] for r in by_score[:n]}


def detect_entry_zone(
    market: str,
    results: List[Dict[str, Any]],
    prev_state: Dict[str, Dict[str, Any]],
    watchlist: set,
) -> List[Dict[str, Any]]:
    """Watchlist + Top 10 stocks whose live price came down into the buy zone of today's frozen plan.

    Fires per entry_reached (day low reached the recommended entry, price still above the cut loss,
    cut loss not touched today); skips HINDARI rows and plans already alerted (alert_state keeps the
    last alerted entry_low/entry_high/as_of). Each alert carries "plan" for _save_state."""
    out: List[Dict[str, Any]] = []
    candidates = set(watchlist) | _top_n(results)
    for r in results:
        t = r.get("ticker")
        if t not in candidates:
            continue
        lv = r.get("levels")
        if not isinstance(lv, dict) or not lv.get("frozen"):
            continue
        live = lv.get("live")
        if not isinstance(live, dict):
            continue
        action = r.get("action") if isinstance(r.get("action"), dict) else {}
        status = str(action.get("status") or "").upper()
        if status == "HINDARI":
            continue
        el, eh, sl = _f(lv.get("entry_low")), _f(lv.get("entry_high")), _f(lv.get("stop_loss"))
        price, low = _f(live.get("price")), live.get("day_low")
        if el <= 0 or eh <= 0 or sl <= 0 or price <= 0 or low is None:
            continue
        if not entry_reached(lv, live, status):
            continue
        prev = prev_state.get(t) or {}
        as_of = str(lv.get("as_of") or "")
        if (_same_price(prev.get("entry_low"), el) and _same_price(prev.get("entry_high"), eh)
                and str(prev.get("entry_as_of") or "") == as_of):
            continue  # this plan already produced its alert
        rec = _f(lv.get("recommended_entry")) or eh
        zone = f"{_fmt_price(el, market)}–{_fmt_price(eh, market)}"
        if price <= rec:
            msg = f"Harga {_fmt_price(price, market)} mencapai harga beli (limit) {_fmt_price(rec, market)} (zona {zone})."
        else:
            msg = (f"Harga sempat {_fmt_price(_f(low), market)} mencapai harga beli (limit) {_fmt_price(rec, market)} "
                   f"(zona {zone}), kini {_fmt_price(price, market)}.")
        msg += f" Cut loss {_fmt_price(sl, market)}"
        tp1 = _f(lv.get("target_tp1"))
        msg += f", TP1 {_fmt_price(tp1, market)}." if tp1 > 0 else "."
        if status:
            msg += f" Status: {status}."
        out.append({"ticker": t, "kind": "entry_zone", "title": f"{t}: mencapai harga beli (limit)", "message": msg,
                    "plan": {"entry_low": el, "entry_high": eh, "entry_as_of": as_of}})
    return out


# ─── Storage ─────────────────────────────────────────────────────────────────

def _load_state(market: str) -> Dict[str, Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM alert_state WHERE market = ?", (market,)).fetchall()
    return {r["ticker"]: dict(r) for r in rows}


def _save_state(market: str, results: List[Dict[str, Any]],
                prev_state: Optional[Dict[str, Dict[str, Any]]] = None,
                alerted_plans: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """One row per ticker; the last entry_zone plan is carried over unless a new one was alerted."""
    now = datetime.now().isoformat()
    prev_state = prev_state or {}
    alerted_plans = alerted_plans or {}
    rows = []
    for r in results:
        t = r.get("ticker")
        if not t:
            continue
        plan = alerted_plans.get(t) or prev_state.get(t) or {}
        rows.append((market, t, r.get("verdict"), 1 if r.get("is_confirmed_breakout") else 0,
                     r.get("money_flow_status"), _f(r.get("price")), _f(r.get("stop_loss")),
                     _f(r.get("target_tp1") or r.get("target_tp")), now,
                     plan.get("entry_low"), plan.get("entry_high"), plan.get("entry_as_of")))
    with get_connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO alert_state
                (market, ticker, verdict, is_confirmed_breakout, money_flow_status, price, stop_loss, target_tp1,
                 updated_at, entry_low, entry_high, entry_as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


def _store_alerts(market: str, alerts: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    stored = []
    cutoff = (now - COOLDOWN).isoformat()
    with get_connection() as conn:
        for a in alerts:
            dup = conn.execute(
                "SELECT 1 FROM alerts WHERE ticker = ? AND kind = ? AND created_at >= ? LIMIT 1",
                (a["ticker"], a["kind"], cutoff),
            ).fetchone()
            if dup:
                continue
            cur = conn.execute(
                "INSERT INTO alerts (created_at, market, ticker, kind, title, message, is_read) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (now.isoformat(), market, a["ticker"], a["kind"], a["title"], a["message"]),
            )
            stored.append({**a, "id": cur.lastrowid, "market": market})
        conn.execute(
            "DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY id DESC LIMIT ?)",
            (MAX_ALERTS_KEPT,),
        )
        conn.commit()
    return stored


def _watchlist_set(market: str) -> set:
    out = set()
    for r in get_watchlist():
        t = str(r.get("ticker") or "")
        if not t:
            continue
        m = (r.get("market") or ("IDX" if t.upper().endswith(".JK") else "US")).upper()
        if m == market:
            out.add(normalize_ticker(t, market))
    return out


def on_scan_complete(market: str, results: List[Dict[str, Any]], now: Optional[datetime] = None) -> None:
    try:
        _ensure_tables()
        market = (market or "IDX").upper()
        results = [r for r in (results or []) if isinstance(r, dict) and r.get("ticker")]
        if not results:
            return None
        prev = _load_state(market)
        prefs = get_prefs()
        watchlist = _watchlist_set(market)
        found = detect_alerts(market, results, prev, watchlist)
        found = [a for a in found if prefs["kinds"].get(a["kind"], True)]
        entry = detect_entry_zone(market, results, prev, watchlist) if prefs["kinds"].get("entry_zone", True) else []
        plans = {a["ticker"]: a.pop("plan") for a in entry}
        found += entry
        stored = _store_alerts(market, found, now or datetime.now()) if found else []
        # A plan counts as alerted only once its alert was stored (one held back by the cooldown may fire later)
        alerted_plans = {a["ticker"]: plans[a["ticker"]] for a in stored
                         if a["kind"] == "entry_zone" and a["ticker"] in plans}
        _save_state(market, results, prev, alerted_plans)
        if stored and prefs["os_toast"]:
            _os_toast(stored)
    except Exception as e:
        print(f"[Notifications] on_scan_complete failed: {e}")
    return None


# ─── Queries used by the API ─────────────────────────────────────────────────

def _row(r: Any) -> Dict[str, Any]:
    d = dict(r)
    d["read"] = bool(d.pop("is_read", 0))
    return d


def list_alerts(limit: int = 50, unread_only: bool = False, since_id: int = 0) -> Dict[str, Any]:
    _ensure_tables()
    limit = max(1, min(int(limit), 200))
    q = "SELECT * FROM alerts WHERE id > ?"
    args: List[Any] = [int(since_id or 0)]
    if unread_only:
        q += " AND is_read = 0"
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with get_connection() as conn:
        rows = conn.execute(q, args).fetchall()
        unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE is_read = 0").fetchone()[0]
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM alerts").fetchone()[0]
    return {"alerts": [_row(r) for r in rows], "unread_count": unread, "latest_id": latest}


def mark_read(ids: Optional[List[int]] = None, all_: bool = False) -> int:
    _ensure_tables()
    with get_connection() as conn:
        if all_:
            cur = conn.execute("UPDATE alerts SET is_read = 1 WHERE is_read = 0")
        elif ids:
            marks = ",".join("?" * len(ids))
            cur = conn.execute(f"UPDATE alerts SET is_read = 1 WHERE id IN ({marks})", [int(i) for i in ids])
        else:
            return 0
        conn.commit()
        return cur.rowcount


def clear_alerts() -> int:
    _ensure_tables()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM alerts")
        conn.commit()
        return cur.rowcount


# ─── Optional Windows toast (off by default, fire-and-forget) ────────────────

_PS_TOAST = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$t.Item(0).AppendChild($xml.CreateTextNode($env:SAHAM_TOAST_TITLE)) > $null
$t.Item(1).AppendChild($xml.CreateTextNode($env:SAHAM_TOAST_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def _os_toast(alerts: List[Dict[str, Any]]) -> None:
    if sys.platform != "win32" or not alerts:
        return
    try:
        title = alerts[0]["title"] if len(alerts) == 1 else f"SAHAM: {len(alerts)} alert baru"
        body = alerts[0]["message"] if len(alerts) == 1 else ", ".join(a["title"] for a in alerts[:4])
        env = {**os.environ, "SAHAM_TOAST_TITLE": title[:120], "SAHAM_TOAST_BODY": body[:240]}
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS_TOAST],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[Notifications] OS toast failed: {e}")
