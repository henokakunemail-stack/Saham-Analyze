"""Desktop window lifecycle: the engine must not shut down while the window is open."""
from engine import app_lifecycle as lc

T0 = 1_000_000.0


def reason(now, last_seen, bye_at=None, proc_exited_at=None):
    return lc.exit_reason(now, T0, last_seen, bye_at, proc_exited_at)


def test_launcher_exit_alone_does_not_close_while_ui_beats():
    # Edge handed the window to another process right away; UI keeps sending heartbeats
    now = T0 + 300
    assert reason(now, last_seen=now - 20, proc_exited_at=T0 + 1) is None


def test_throttled_minimized_window_survives():
    # Hidden pages may only fire timers once per minute
    now = T0 + 900
    assert reason(now, last_seen=now - 70, proc_exited_at=T0 + 1) is None
    assert reason(now, last_seen=now - 70) is None


def test_bye_beacon_closes_after_delay_but_reload_does_not():
    bye_at = T0 + 100
    assert reason(bye_at + 3, last_seen=bye_at - 5, bye_at=bye_at) is None          # still within reload window
    assert reason(bye_at + 9, last_seen=bye_at - 5, bye_at=bye_at) is not None      # really closed
    # reload: a heartbeat after the bye resets it
    lc.bye(); lc.touch()
    assert lc.snapshot()["bye_at"] is None


def test_safety_nets():
    now = T0 + 2000
    assert reason(now, last_seen=now - 200, proc_exited_at=T0 + 1) is not None       # browser gone + silent
    assert reason(now, last_seen=now - 700) is not None                               # silent 10+ min


def test_startup_grace():
    assert reason(T0 + 10, last_seen=T0 - 1000, proc_exited_at=T0 + 1) is None


def test_endpoints():
    from engine.main import app
    from starlette.testclient import TestClient
    c = TestClient(app)
    assert c.post("/api/app/bye").status_code == 200 and lc.snapshot()["bye_at"] is not None
    assert c.post("/api/app/heartbeat").status_code == 200 and lc.snapshot()["bye_at"] is None
