"""Desktop window lifecycle: decide when the desktop runner may shut the engine down.

The UI sends a heartbeat every 20 s and a "bye" beacon when the page is closed. The
launcher process of Edge is NOT a reliable signal: Edge often hands the window to an
already running browser process and exits immediately, and hidden/minimized pages get
their timers throttled to about once per minute. So the runner exits only when:
  - the window said bye and no new heartbeat arrived within BYE_DELAY (a reload sends
    bye and then heartbeats again, so it does not count as a close), or
  - the browser process is gone AND the UI has been silent for PROC_GONE_SILENCE, or
  - the UI has been silent for MAX_SILENCE (crash/kill safety net).
"""
import threading
import time
from typing import Dict, Optional

STARTUP_GRACE = 45          # seconds before any exit rule applies
BYE_DELAY = 8               # reload window after a bye beacon
PROC_GONE_SILENCE = 150     # > throttled timer interval of hidden pages (~60 s)
MAX_SILENCE = 600

_lock = threading.Lock()
_state: Dict[str, Optional[float]] = {"last_seen": time.time(), "bye_at": None}


def touch() -> None:
    """Called only by the UI heartbeat endpoint. Other HTTP clients (scripts, a second
    browser tab polling /api/health) must not keep a closed desktop window "alive"."""
    with _lock:
        _state["last_seen"] = time.time()
        _state["bye_at"] = None


def bye() -> None:
    with _lock:
        _state["bye_at"] = time.time()


def snapshot() -> Dict[str, Optional[float]]:
    with _lock:
        return dict(_state)


def exit_reason(now: float, started: float, last_seen: float, bye_at: Optional[float],
                proc_exited_at: Optional[float]) -> Optional[str]:
    """Pure decision function used by the desktop runner (None = keep running)."""
    if now - started < STARTUP_GRACE:
        return None
    if bye_at is not None and now - bye_at >= BYE_DELAY and last_seen <= bye_at:
        return "Jendela ditutup (beacon pamit diterima)."
    silent = now - last_seen
    if proc_exited_at is not None and silent >= PROC_GONE_SILENCE:
        return "Proses browser sudah berhenti dan UI tidak mengirim detak."
    if silent >= MAX_SILENCE:
        return "UI tidak mengirim detak selama 10 menit."
    return None
