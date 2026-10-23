"""Telegram bot service: scheduled messages, live alerts and group commands.

Runs as one background thread (long polling: no inbound port is needed, so it works the same
on the desktop app and on a Linux server). The engine hands data in through `configure()`
instead of this module importing engine.main, which keeps it testable and import-cycle free.

Schedule (per market in `markets`, default IDX only):
- daily plan: once per final close, after the closing scan (plan for the next session)
- midday check: once per day during the BEI lunch break
- weekly record: after the Friday plan
- alerts: after each scan while the session trades — for the stocks of the last plan sent
  plus the watchlist: entered the buy zone / touched TP1 / touched the cut loss (each once a day)

Only the chat registered in the settings gets answers; any other chat that types /start or /id
is told its chat id so the owner can register it in the app.
"""
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from ..db import get_setting, set_setting
from . import bot_api, messages
from ..notifications import entry_reached
from .bot_api import TelegramError

TOKEN_KEY = "telegram_bot_token"
CONFIG_KEY = "telegram_config"
STATE_KEY = "telegram_state"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "chat_id": None,
    "chat_title": None,
    "markets": ["IDX"],
    "send": {"daily_plan": True, "midday": True, "alerts": True, "weekly": True},
    "commands": True,
}
SEND_GAP_SEC = 1.1         # Telegram allows ~20 messages/minute per group
STALE_SCAN_RETRY_SEC = 3600
DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

_lock = threading.RLock()
# Every read-modify-write of the stored state (sent marks, alerts, poll offset) holds this, so
# the poll thread and the scan thread never overwrite each other's changes or send twice
_state_lock = threading.RLock()
MAX_SCAN_REQUESTS_PER_CLOSE = 2
_providers: Dict[str, Callable[..., Any]] = {}
_status: Dict[str, Any] = {"running": False, "bot_username": None, "last_ok_at": None, "last_error": None,
                           "recent": []}
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_last_send_at = 0.0
_last_scan_request: Dict[str, float] = {}


# ── Settings & state ────────────────────────────────────────────────────────
def get_config() -> Dict[str, Any]:
    try:
        raw = json.loads(get_setting(CONFIG_KEY, "") or "{}")
    except ValueError:
        raw = {}
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG and k != "send"})
    cfg["send"].update({k: bool(v) for k, v in (raw.get("send") or {}).items() if k in cfg["send"]})
    cfg["markets"] = [m for m in cfg.get("markets") or [] if m in ("IDX", "US")] or ["IDX"]
    return cfg


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    clean = get_config()
    clean.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG and k != "send"})
    if isinstance(cfg.get("send"), dict):
        clean["send"].update({k: bool(v) for k, v in cfg["send"].items() if k in clean["send"]})
    set_setting(CONFIG_KEY, json.dumps(clean))
    return get_config()


def get_token() -> str:
    return get_setting(TOKEN_KEY, "")


def set_token(token: str) -> None:
    set_setting(TOKEN_KEY, token.strip())
    with _lock:
        _status["bot_username"] = None


def _state() -> Dict[str, Any]:
    try:
        st = json.loads(get_setting(STATE_KEY, "") or "{}")
    except ValueError:
        st = {}
    st.setdefault("offset", None)
    st.setdefault("sent", {})
    st.setdefault("plan_tickers", {})
    st.setdefault("alerts", {})
    st.setdefault("chats", {})
    return st


def _save_state(st: Dict[str, Any]) -> None:
    # keep the bookkeeping small
    st["sent"] = dict(sorted(st["sent"].items(), key=lambda kv: kv[1])[-80:])
    st["alerts"] = dict(sorted(st["alerts"].items())[-6:])
    set_setting(STATE_KEY, json.dumps(st))


def detected_chats() -> List[Dict[str, Any]]:
    chats = _state()["chats"]
    return sorted(({"id": int(k), **v} for k, v in chats.items()), key=lambda c: -c.get("seen", 0))


def status() -> Dict[str, Any]:
    with _lock:
        return json.loads(json.dumps(_status))


def configure(**providers: Callable[..., Any]) -> None:
    """Engine callbacks: results(market), checkpoint(market), analysis(ticker), session(market),
    history(market), request_scan(market)."""
    _providers.update(providers)


# ── Sending ─────────────────────────────────────────────────────────────────
def _record(kind: str, ok: bool, detail: str = "") -> None:
    with _lock:
        _status["recent"] = ([{"at": datetime.now().astimezone().isoformat(timespec="seconds"), "kind": kind,
                               "ok": ok, "detail": detail[:160]}] + _status["recent"])[:12]
        if ok:
            _status["last_ok_at"] = time.time()
            _status["last_error"] = None
        else:
            _status["last_error"] = detail[:300]


def send(text: str, kind: str = "manual", chat_id: Any = None, reply_to: Optional[int] = None) -> bool:
    global _last_send_at
    token = get_token()
    target = chat_id if chat_id is not None else get_config().get("chat_id")
    if not token or target in (None, ""):
        _record(kind, False, "Token atau grup belum diatur.")
        return False
    wait = SEND_GAP_SEC - (time.time() - _last_send_at)
    if wait > 0:
        time.sleep(wait)
    try:
        bot_api.send_message(token, target, text, reply_to=reply_to)
        _last_send_at = time.time()
        _record(kind, True)
        return True
    except TelegramError as e:
        _record(kind, False, str(e))
        return False


# ── Building blocks ─────────────────────────────────────────────────────────
def _results(market: str) -> List[Dict[str, Any]]:
    fn = _providers.get("results")
    return list(fn(market) or []) if fn else []


def _session(market: str) -> Dict[str, Any]:
    fn = _providers.get("session")
    return fn(market) if fn else {}


def _mode(rows: List[Dict[str, Any]]) -> str:
    return next((r.get("market_mode") for r in rows if r.get("market_mode")), "NORMAL")


def _plan_rows(rows: List[Dict[str, Any]], n: int = 10) -> List[Dict[str, Any]]:
    """The app's own order: `rank` (status first, then raw score) when present, else score."""
    if any(r.get("rank") for r in rows):
        return sorted(rows, key=lambda r: r.get("rank") or 10**6)[:n]
    return sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)[:n]


def _as_of(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Close the stored plans stand on, only when it is final (not a frozen intraday copy)."""
    for r in rows:
        lv = r.get("levels") or {}
        if lv.get("as_of") and not lv.get("frozen") and lv.get("bar_final") is not False:
            return str(lv["as_of"])[:10]
    return None


def _next_session_label(session: Dict[str, Any], as_of: str) -> str:
    try:
        nxt = datetime.fromisoformat(session.get("next_open") or "")
        d = nxt.date()
    except ValueError:
        d = datetime.strptime(as_of, "%Y-%m-%d").date() + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return f"{DAYS[d.weekday()]}, {d.day:02d}/{d.month:02d}/{d.year}"


def _expected_close(market: str) -> Optional[str]:
    fn = _providers.get("expected_close")
    return fn(market) if fn else None


def build_daily_plan(market: str) -> Optional[str]:
    rows = _results(market)
    as_of = _as_of(rows)
    if not rows or not as_of:
        return None
    return messages.daily_plan(_plan_rows(rows), market, as_of, _next_session_label(_session(market), as_of), _mode(rows))


def build_midday(market: str) -> str:
    fn = _providers.get("checkpoint")
    data = fn(market) if fn else {"rows": []}
    s = data.get("session") or _session(market)
    ends = (s.get("session_ends") or "")[11:16]
    note = f"{s.get('session_name', '')}" + (f" · sesi 2 buka {ends} {s.get('tz_label', '')}" if s.get("session") == "lunch_break" and ends else "")
    return messages.midday(data.get("rows") or [], market, datetime.now().strftime("%d/%m/%Y"), note)


def build_weekly(market: str) -> str:
    fn = _providers.get("history")
    summary, dates = fn(market, 7) if fn else ({}, [])
    return messages.weekly(summary or {}, dates or [], market)


# ── Scheduled messages ──────────────────────────────────────────────────────
def tick(now: Optional[datetime] = None) -> None:
    """Send whatever is due. Safe to call often (every poll cycle and after each scan)."""
    cfg = get_config()
    if not cfg["enabled"] or not cfg.get("chat_id") or not get_token():
        return
    scanning = _providers.get("scanning")
    if scanning and scanning():
        return  # rows are being rewritten: the next tick after the scan sends a consistent plan
    with _state_lock:
        _tick(cfg, now or datetime.now())


def _tick(cfg: Dict[str, Any], now: datetime) -> None:
    st = _state()
    changed = False
    for market in cfg["markets"]:
        session = _session(market)
        rows = _results(market)
        as_of = _as_of(rows)
        live = bool(session.get("trading_day_live"))

        if cfg["send"]["daily_plan"] and not live and as_of:
            key = f"plan:{market}:{as_of}"
            expected = _expected_close(market)
            if key not in st["sent"] and (expected is None or as_of >= expected):
                text = messages.daily_plan(_plan_rows(rows), market, as_of,
                                           _next_session_label(session, as_of), _mode(rows))
                if send(text, "daily_plan"):
                    st["sent"][key] = time.time()
                    st["plan_tickers"][market] = {"as_of": as_of, "tickers": [r["ticker"] for r in _plan_rows(rows)]}
                    changed = True
                    if cfg["send"]["weekly"] and datetime.strptime(as_of, "%Y-%m-%d").weekday() == 4:
                        wkey = f"weekly:{market}:{as_of}"
                        if wkey not in st["sent"] and send(build_weekly(market), "weekly"):
                            st["sent"][wkey] = time.time()
            elif expected and as_of < expected and not live:
                _request_scan(market, expected)  # the closing scan was missed (app/server was off)

        if cfg["send"]["midday"] and session.get("session") == "lunch_break":
            key = f"midday:{market}:{now.strftime('%Y-%m-%d')}"
            if key not in st["sent"] and send(build_midday(market), "midday"):
                st["sent"][key] = time.time()
                changed = True
    if changed:
        _save_state(st)


_scan_requests: Dict[str, int] = {}


def _request_scan(market: str, expected: str = "") -> None:
    """At most MAX_SCAN_REQUESTS_PER_CLOSE per expected close: on an exchange holiday the close
    never arrives, and an hourly full scan all weekend helps nobody."""
    fn = _providers.get("request_scan")
    last = _last_scan_request.get(market, 0)
    key = f"{market}:{expected}"
    if fn and time.time() - last > STALE_SCAN_RETRY_SEC and _scan_requests.get(key, 0) < MAX_SCAN_REQUESTS_PER_CLOSE:
        _last_scan_request[market] = time.time()
        _scan_requests[key] = _scan_requests.get(key, 0) + 1
        threading.Thread(target=fn, args=(market,), daemon=True, name=f"tg-scan-{market}").start()


# ── Live alerts ─────────────────────────────────────────────────────────────
def detect_alerts(rows: List[Dict[str, Any]], tracked: List[str], already: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """New (ticker, kind) events for tracked tickers from frozen plans with a live price."""
    out = []
    for r in rows:
        t = r.get("ticker")
        lv = r.get("levels") or {}
        live = lv.get("live")
        if t not in tracked or not lv.get("frozen") or not live:
            continue
        done = set(already.get(t, []))
        if "stop" in done:
            continue
        status = (r.get("action") or {}).get("status")
        kinds = []
        if live.get("touched_stop") or live.get("status") == "BELOW_STOP":
            kinds = ["stop"]
        else:
            entered = entry_reached(lv, live, status) or "entry_zone" in done
            if entered and "entry_zone" not in done:
                kinds.append("entry_zone")
            # TP only for a plan that could have been bought today (not for a stock that just ran)
            if entered and (live.get("touched_tp1") or live.get("status") in ("AT_TP1", "AT_TP2")):
                kinds.append("tp")
        for k in kinds:
            if k not in done:
                out.append({"ticker": t, "kind": k, "live": live, "levels": lv})
    return out


def on_scan_complete(market: str, results: List[Dict[str, Any]], watchlist: Optional[List[str]] = None) -> None:
    try:
        cfg = get_config()
        if not cfg["enabled"] or market not in cfg["markets"] or not cfg.get("chat_id") or not get_token():
            return
        if cfg["send"]["alerts"] and _session(market).get("trading_day_live"):
            with _state_lock:
                _send_alerts(market, results, watchlist)
        tick()
    except Exception as e:  # never break a scan over Telegram
        _record("alerts", False, str(e))


def _send_alerts(market: str, results: List[Dict[str, Any]], watchlist: Optional[List[str]]) -> None:
    st = _state()
    plan = st["plan_tickers"].get(market) or {}
    tracked = list(plan.get("tickers") or [r["ticker"] for r in _plan_rows(results)])
    tracked += [t for t in (watchlist or []) if t not in tracked]
    day_key = f"{market}:{datetime.now().strftime('%Y-%m-%d')}"
    already = st["alerts"].setdefault(day_key, {})
    events = detect_alerts(results, tracked, already)
    if events:
        text = "\n\n".join(messages.alert(e["kind"], e["ticker"], market, e["live"], e["levels"]) for e in events)
        if send(text, "alerts"):
            for e in events:
                already.setdefault(e["ticker"], []).append(e["kind"])
            _save_state(st)


# ── Commands ────────────────────────────────────────────────────────────────
def handle_update(update: Dict[str, Any]) -> None:
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    if not text.startswith("/") or "id" not in chat:
        return
    st = _state()
    st["chats"][str(chat["id"])] = {"title": chat.get("title") or chat.get("username") or chat.get("first_name") or "",
                                    "type": chat.get("type"), "seen": time.time()}
    _save_state(st)

    head, *args = text.split()
    cmd, _, target = head[1:].partition("@")
    me = (_status.get("bot_username") or "").lower()
    if target and me and target.lower() != me:
        return  # addressed to another bot in the group
    cmd = cmd.lower()
    cfg = get_config()
    reply_to = msg.get("message_id")
    if str(chat["id"]) != str(cfg.get("chat_id")):
        if cmd in ("start", "id", "daftar"):
            send(f"Bot SAHAM ini privat.\nID chat ini: <code>{chat['id']}</code>\n"
                 f"Pemilik bisa mendaftarkannya di SAHAM → Pengaturan → Telegram.", "register", chat_id=chat["id"])
        return
    if not cfg.get("commands"):
        return
    send(answer(cmd, args), f"cmd:{cmd}", reply_to=reply_to)


def answer(cmd: str, args: List[str]) -> str:
    market = get_config()["markets"][0]
    if cmd in ("start", "bantuan", "help"):
        return messages.help_text()
    if cmd == "top10":
        rows = _results(market)
        return messages.top10(_plan_rows(rows), market, _mode(rows)) if rows else "Belum ada hasil scan."
    if cmd == "rencana":
        return build_daily_plan(market) or "Rencana untuk sesi berikutnya belum tersedia (menunggu penutupan final)."
    if cmd in ("tengahhari", "cekharga"):
        return build_midday(market)
    if cmd == "rekam":
        return build_weekly(market)
    if cmd == "pasar":
        sessions = {m: _session(m) for m in ("IDX", "US")}
        modes = {m: _mode(_results(m)) for m in ("IDX", "US")}
        return messages.market_status(sessions, modes)
    if cmd == "cek":
        if not args:
            return "Tulis kodenya, contoh: /cek BBCA"
        fn = _providers.get("analysis")
        try:
            a, m = fn(args[0], market)
        except Exception as e:  # unknown code, no data
            return f"Tidak bisa membaca {messages.code(args[0].upper())}: {messages.escape(str(getattr(e, 'detail', e)))}"
        return messages.stock(a, m)
    if cmd == "id":
        return f"ID chat ini: <code>{get_config().get('chat_id')}</code>"
    return "Perintah tidak dikenal. /bantuan untuk daftar perintah."


# ── Poll loop ───────────────────────────────────────────────────────────────
def _loop() -> None:
    with _lock:
        _status["running"] = True
    prepared_for = None
    while not _stop.is_set():
        cfg = get_config()
        token = get_token()
        if not cfg["enabled"] or not token:
            prepared_for = None
            _stop.wait(15)
            continue
        try:
            if prepared_for != token:
                me = bot_api.get_me(token)
                with _lock:
                    _status["bot_username"] = me.get("username")
                bot_api.delete_webhook(token)
                bot_api.set_commands(token, messages.COMMANDS)
                prepared_for = token
            with _state_lock:
                offset = _state()["offset"]
            updates = bot_api.get_updates(token, offset, timeout=25)
            for u in updates:
                with _state_lock:
                    st = _state()
                    st["offset"] = u["update_id"] + 1
                    _save_state(st)
                    try:
                        handle_update(u)
                    except Exception as e:
                        _record("command", False, str(e))
            tick()
        except TelegramError as e:
            msg = str(e)
            if e.code == 409:
                msg = "Bot ini sedang dipakai instance SAHAM lain (desktop/server). Aktifkan Telegram di satu tempat saja."
            elif e.code == 401:
                msg = "Token bot tidak valid."
            _record("poll", False, msg)
            prepared_for = None if e.code in (401, 409) else prepared_for
            _stop.wait(30 if e.code in (401, 409) else 10)
        except Exception as e:
            _record("poll", False, str(e))
            _stop.wait(10)
    with _lock:
        _status["running"] = False


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="TelegramBot")
    _thread.start()
