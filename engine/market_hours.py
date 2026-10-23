"""Exchange session awareness (owned by: Coverage & Control).

Contract used by engine.main._background_scanner:
    should_auto_scan_now(market) -> bool

Sessions (weekdays only; exchange holidays are not modelled):
    IDX  09:00-16:15 Asia/Jakarta       (incl. post-trading; fallback fixed UTC+7 — exact, no DST)
    US   09:30-16:00 America/New_York   (fallback fixed UTC-5 — one hour off during US DST)
Outside the session one closing scan runs once the day's bar is final (closing_scan_due), so the
next session's plan is built from the final close.

User setting "auto_scan_mode" (JSON string): "market_hours" (default) | "always" | "off".
"""
import json
from datetime import datetime, time as dtime, timedelta, timezone, tzinfo
from typing import Any, Dict, Optional, Tuple

from .db import get_setting, set_setting

MODES = ("market_hours", "always", "off")
DEFAULT_MODE = "market_hours"
MODE_KEY = "auto_scan_mode"

DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

_SESSIONS: Dict[str, Dict[str, Any]] = {
    "IDX": {"tz": "Asia/Jakarta", "fallback_hours": 7, "open": dtime(9, 0), "close": dtime(16, 15),
            "tz_label": "WIB", "name": "BEI"},
    "US": {"tz": "America/New_York", "fallback_hours": -5, "open": dtime(9, 30), "close": dtime(16, 0),
           "tz_label": "ET", "name": "NYSE/Nasdaq"},
}

# BEI trading schedule within the day (Mon-Thu, and Friday's longer lunch break).
# Source: BEI trading hours; update here if the exchange changes them.
_IDX_DAY = {
    "weekday": [("pre_open", (8, 45)), ("session_1", (9, 0)), ("lunch_break", (12, 0)), ("session_2", (13, 30)),
                ("pre_close", (15, 50)), ("post_trading", (16, 0)), ("closed", (16, 15))],
    "friday": [("pre_open", (8, 45)), ("session_1", (9, 0)), ("lunch_break", (11, 30)), ("session_2", (14, 0)),
               ("pre_close", (15, 50)), ("post_trading", (16, 0)), ("closed", (16, 15))],
}
SESSION_NAMES = {
    "pre_open": "Pra-pembukaan", "session_1": "Sesi 1", "lunch_break": "Jeda siang", "session_2": "Sesi 2",
    "pre_close": "Pra-penutupan (lelang)", "post_trading": "Pasca-penutupan", "closed": "Tutup", "regular": "Sesi reguler",
}
# Sessions where prices move (the plan's live position is meaningful)
TRADING_SESSIONS = ("session_1", "lunch_break", "session_2", "pre_close", "regular")


def idx_session(local: datetime) -> Tuple[str, Optional[datetime], Optional[str]]:
    """(current part of the BEI day, when it ends, what comes next) for a WIB datetime."""
    if local.weekday() >= 5:
        return "closed", None, None
    plan = _IDX_DAY["friday" if local.weekday() == 4 else "weekday"]
    current = "closed"
    for i, (name, (h, m)) in enumerate(plan):
        start = local.replace(hour=h, minute=m, second=0, microsecond=0)
        if local < start:
            return current, start, name
        current = name
    return "closed", None, None


def _market(market: str) -> str:
    m = (market or "IDX").strip().upper()
    return m if m in _SESSIONS else "IDX"


def _zone(market: str) -> Tuple[tzinfo, bool]:
    """Return (tzinfo, is_fallback). tzdata can be missing in a frozen Windows build."""
    s = _SESSIONS[_market(market)]
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(s["tz"]), False
    except Exception:
        return timezone(timedelta(hours=s["fallback_hours"])), True


def _local_now(market: str, now: Optional[datetime]) -> datetime:
    tz, _ = _zone(market)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        now = now.astimezone()  # naive = machine local time
    return now.astimezone(tz)


def get_mode() -> str:
    raw = get_setting(MODE_KEY, "")
    try:
        val = json.loads(raw) if raw else DEFAULT_MODE
    except (ValueError, TypeError):
        val = raw
    return val if val in MODES else DEFAULT_MODE


def set_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    set_setting(MODE_KEY, json.dumps(mode))
    return mode


def _bounds(market: str, local: datetime) -> Tuple[datetime, datetime]:
    s = _SESSIONS[_market(market)]
    o = local.replace(hour=s["open"].hour, minute=s["open"].minute, second=0, microsecond=0)
    c = local.replace(hour=s["close"].hour, minute=s["close"].minute, second=0, microsecond=0)
    return o, c


def _next_open(market: str, local: datetime) -> datetime:
    o, _ = _bounds(market, local)
    day = o if (local.weekday() < 5 and local < o) else o + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _phase(market: str, local: datetime) -> str:
    """open | closed | weekend"""
    if local.weekday() >= 5:
        return "weekend"
    o, c = _bounds(market, local)
    return "open" if o <= local < c else "closed"


_BENCH_SYMBOL = {"IDX": "^JKSE", "US": "^GSPC"}
_LAST_OK_KEY = "autoscan_last_ok_{}"
_last_ok: Dict[str, datetime] = {}


def mark_scan_done(market: str, when: Optional[datetime] = None) -> None:
    """Record a scan that finished successfully (any trigger: auto, manual, Telegram)."""
    market = _market(market)
    when = when or datetime.now().astimezone()
    _last_ok[market] = when
    try:
        set_setting(_LAST_OK_KEY.format(market), json.dumps(when.isoformat()))
    except Exception:
        pass


def _last_ok_scan(market: str) -> Optional[datetime]:
    if market in _last_ok:
        return _last_ok[market]
    try:
        raw = get_setting(_LAST_OK_KEY.format(market), "")
        return datetime.fromisoformat(json.loads(raw)) if raw else None
    except (ValueError, TypeError):
        return None


def closing_scan_due(market: str, now: Optional[datetime] = None) -> bool:
    """No successful scan since the last session's bar became final: the stored plan is not the
    one for the next session. Covers the 16:50 closing scan, a missed/failed one, an app opened
    late at night and weekends. Side-effect free: the scan marks itself done when it succeeds."""
    from .collectors.data_quality import last_closed_session
    final_at = last_closed_session(_BENCH_SYMBOL[_market(market)], _local_now(market, now))
    last = _last_ok_scan(market)
    return last is None or last < final_at


def should_auto_scan_now(market: str, now: Optional[datetime] = None) -> bool:
    try:
        market = _market(market)
        mode = get_mode()
        if mode == "off":
            return False
        if mode == "always":
            return True
        local = _local_now(market, now)
        if _phase(market, local) == "open":
            return True
        return closing_scan_due(market, local)
    except Exception as e:
        print(f"[MarketHours] {e}")
        return False


def _fmt_next(local: datetime, nxt: datetime, tz_label: str) -> str:
    hhmm = nxt.strftime("%H:%M")
    delta_days = (nxt.date() - local.date()).days
    if delta_days == 0:
        when = f"hari ini {hhmm}"
    elif delta_days == 1:
        when = f"besok {hhmm}"
    else:
        when = f"{DAY_NAMES[nxt.weekday()]} {hhmm}"
    return f"{when} {tz_label}"


def session_status(market: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    market = _market(market)
    s = _SESSIONS[market]
    tz, fallback = _zone(market)
    local = _local_now(market, now)
    phase = _phase(market, local)
    o, c = _bounds(market, local)
    nxt = _next_open(market, local)
    is_open = phase == "open"

    session, session_ends, next_session = ("regular" if is_open else "closed"), None, None
    if is_open:
        label = f"Bursa buka · tutup {c.strftime('%H:%M')} {s['tz_label']}"
    else:
        label = f"Bursa tutup · buka lagi {_fmt_next(local, nxt, s['tz_label'])}"
    if market == "IDX":
        session, session_ends, next_session = idx_session(local)
        at = f"{session_ends.strftime('%H:%M')} {s['tz_label']}" if session_ends else ""
        if session == "pre_open":
            label = f"Pra-pembukaan · sesi 1 mulai {at}"
        elif session == "session_1":
            label = f"Sesi 1 · istirahat {at}"
        elif session == "lunch_break":
            label = f"Jeda siang · sesi 2 buka {at}"
        elif session == "session_2":
            label = f"Sesi 2 · pra-penutupan {at}"
        elif session == "pre_close":
            label = f"Pra-penutupan (lelang) · tutup {at}"
        elif session == "post_trading":
            label = f"Bursa tutup · harga penutupan final ±16:45 {s['tz_label']}"

    mode = get_mode()
    if mode == "off":
        auto = "Auto-scan dimatikan"
    elif mode == "always":
        auto = "Auto-scan 24/7"
    elif is_open:
        auto = "Auto-scan aktif selama jam bursa"
    elif closing_scan_due(market, local):
        auto = "Satu scan penutupan akan berjalan"
    else:
        auto = "Auto-scan menunggu bursa buka"

    note = None
    if fallback and market == "US":
        note = "Zona waktu tetap UTC-5 (tzdata tidak tersedia): saat DST jam bisa bergeser 1 jam."
    return {
        "market": market,
        "exchange": s["name"],
        "is_open": is_open,
        "phase": phase,
        "label": label,
        "auto_scan_label": auto,
        "auto_scan_mode": mode,
        "local_time": local.isoformat(timespec="minutes"),
        "open_time": o.strftime("%H:%M"),
        "close_time": c.strftime("%H:%M"),
        "tz_label": s["tz_label"],
        "next_open": nxt.isoformat(timespec="minutes"),
        "tz_fallback": fallback,
        "note": note,
        "holidays_modelled": False,
        # Finer part of the trading day (BEI: sessions 1/2 and the lunch break)
        "session": session,
        "session_name": SESSION_NAMES.get(session, session),
        "session_ends": session_ends.isoformat(timespec="minutes") if session_ends else None,
        "next_session": next_session,
        "trading_day_live": session in TRADING_SESSIONS,
    }
