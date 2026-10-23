"""Telegram bot: messages, alert detection, scheduling, command access, token safety (offline)."""
from datetime import datetime

import pytest

from engine.telegram import bot_api, messages, service

LV = {"entry_low": 2930, "entry_high": 3020, "recommended_entry": 2970, "stop_loss": 2790, "target_tp1": 3150,
      "target_tp2": 3400, "risk_reward_ratio": 0.9, "flags": ["tight_room"], "as_of": "2026-10-23", "bar_final": True}


def row(ticker, score=60, levels=None, mode="NORMAL"):
    return {"ticker": ticker, "score": score, "verdict": "MILD_BULLISH", "price": 3000, "market_mode": mode,
            "levels": levels if levels is not None else dict(LV)}


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(service, "send", lambda text, kind="manual", chat_id=None, reply_to=None: out.append((kind, text, chat_id)) or True)
    service.set_token("123456:ABCDEFGHIJKLMNOPQRSTUV")
    service.save_config({"enabled": True, "chat_id": -1001, "markets": ["IDX"],
                         "send": {"daily_plan": True, "midday": True, "alerts": True, "weekly": True}})
    from engine.db import set_setting
    set_setting(service.STATE_KEY, "{}")
    yield out
    service.save_config({"enabled": False})


def test_numbers_and_daily_plan_text():
    assert messages.num(2930) == "2.930" and messages.num(142) == "142" and messages.num(57.5) == "57,50"
    text = messages.daily_plan([row("PTBA.JK")], "IDX", "2026-10-23", "Senin, 26/10/2026", "CRASH")
    assert "PTBA" in text and ".JK" not in text and "Beli 2.930–3.020" in text and "CL 2.790" in text
    assert "Pasar krisis" in text and "ruang naik sempit" in text and "bukan ajakan" in text


def test_html_is_escaped():
    a = {"ticker": "<b>X</b>", "technical": {"price": 100}, "composite": {"reasons": ["<script>"]}}
    assert "<script>" not in messages.stock(a, "IDX")


def test_detect_alerts_once_per_kind():
    live_zone = {"price": 2990, "status": "IN_ZONE", "day_low": 2960, "touched_stop": False, "touched_tp1": False}
    rows = [row("PTBA.JK", levels={**LV, "frozen": True, "live": live_zone}),
            row("ADRO.JK", levels={**LV, "frozen": True, "live": {**live_zone, "status": "BELOW_STOP", "touched_stop": True}}),
            row("BBCA.JK", levels={**LV, "frozen": True, "live": {**live_zone, "status": "ABOVE_ZONE", "day_low": 3050}})]
    ev = service.detect_alerts(rows, ["PTBA.JK", "ADRO.JK", "BBCA.JK"], {})
    assert {(e["ticker"], e["kind"]) for e in ev} == {("PTBA.JK", "entry_zone"), ("ADRO.JK", "stop")}
    assert service.detect_alerts(rows, ["PTBA.JK"], {"PTBA.JK": ["entry_zone"]}) == []
    # untracked tickers and plans that are not frozen (session over) never alert
    assert service.detect_alerts([row("PTBA.JK", levels={**LV, "live": live_zone})], ["PTBA.JK"], {}) == []
    # in the zone but the buy limit (recommended entry) was not reached: no alert
    assert service.detect_alerts([row("PTBA.JK", levels={**LV, "frozen": True, "live": {**live_zone, "day_low": 2980}})],
                                 ["PTBA.JK"], {}) == []
    # TP touched by a stock that never came down to the buy limit: no TP alert (could not have been bought)
    ran = {**live_zone, "status": "AT_TP1", "price": 3160, "day_low": 3050, "touched_tp1": True}
    assert service.detect_alerts([row("BBCA.JK", levels={**LV, "frozen": True, "live": ran})], ["BBCA.JK"], {}) == []
    dip_then_tp = {**ran, "day_low": 2960}
    ev = service.detect_alerts([row("BBCA.JK", levels={**LV, "frozen": True, "live": dip_then_tp})], ["BBCA.JK"], {})
    assert [e["kind"] for e in ev] == ["entry_zone", "tp"]


def test_daily_plan_sent_once_per_final_close(sent):
    rows = [row("PTBA.JK"), row("BBCA.JK", 55)]
    service.configure(results=lambda m: rows, session=lambda m: {"trading_day_live": False, "next_open": "2026-10-26T09:00+07:00"},
                      expected_close=lambda m: "2026-10-23", history=lambda m, d: ({"total_predictions": 0}, []))
    service.tick()
    service.tick()
    kinds = [k for k, _, _ in sent]
    assert kinds.count("daily_plan") == 1 and "Senin, 26/10/2026" in sent[0][1]
    assert kinds.count("weekly") == 1           # 23 Oct 2026 is a Friday


def test_stale_plan_is_not_sent_and_requests_a_scan(sent, monkeypatch):
    asked = []
    monkeypatch.setattr(service, "_request_scan", lambda m, expected="": asked.append(m))
    service.configure(results=lambda m: [row("PTBA.JK", levels={**LV, "as_of": "2026-10-22"})],
                      session=lambda m: {"trading_day_live": False}, expected_close=lambda m: "2026-10-23")
    service.tick()
    assert sent == [] and asked == ["IDX"]


def test_midday_once_during_lunch(sent):
    service.configure(results=lambda m: [], session=lambda m: {"trading_day_live": True, "session": "lunch_break"},
                      checkpoint=lambda m: {"rows": [{"ticker": "PTBA.JK", "price": 2990, "status": "IN_ZONE",
                                                      "label": "Di zona beli", **LV}],
                                            "session": {"session": "lunch_break", "session_name": "Jeda siang",
                                                        "session_ends": "2026-10-23T13:30+07:00", "tz_label": "WIB"}})
    service.tick()
    service.tick()
    assert [k for k, _, _ in sent] == ["midday"] and "sesi 2 buka 13:30" in sent[0][1]


def test_alerts_go_out_after_a_scan(sent):
    live = {"price": 2990, "status": "IN_ZONE", "day_low": 2960, "touched_stop": False, "touched_tp1": False}
    rows = [row("PTBA.JK", levels={**LV, "frozen": True, "live": live})]
    service.configure(results=lambda m: rows, session=lambda m: {"trading_day_live": True, "session": "session_1"})
    service.on_scan_complete("IDX", rows, [])
    service.on_scan_complete("IDX", rows, [])
    alerts = [t for k, t, _ in sent if k == "alerts"]
    assert len(alerts) == 1 and "PTBA mencapai harga saran beli" in alerts[0]


def test_only_the_registered_group_gets_answers(sent):
    service.configure(results=lambda m: [row("PTBA.JK")])
    service.handle_update({"message": {"message_id": 5, "text": "/top10", "chat": {"id": -999, "type": "group", "title": "Lain"}}})
    assert sent == []                                     # unknown chat: silent
    service.handle_update({"message": {"message_id": 6, "text": "/start", "chat": {"id": -999, "type": "group", "title": "Lain"}}})
    assert sent[-1][2] == -999 and "-999" in sent[-1][1]  # but it learns its id
    assert any(c["id"] == -999 for c in service.detected_chats())
    service.handle_update({"message": {"message_id": 7, "text": "/top10@SomeOtherBot", "chat": {"id": -1001, "type": "group"}}})
    service._status["bot_username"] = "saham_bot"
    service.handle_update({"message": {"message_id": 8, "text": "/top10@saham_bot", "chat": {"id": -1001, "type": "group"}}})
    assert sent[-1][0] == "cmd:top10" and "PTBA" in sent[-1][1]


def test_token_is_scrubbed_and_long_text_split(monkeypatch):
    import requests

    def boom(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError(f"failed for {url}")
    monkeypatch.setattr(bot_api.requests, "post", boom)
    with pytest.raises(bot_api.TelegramError) as e:
        bot_api.call("123:SECRET", "getMe")
    assert "SECRET" not in str(e.value)
    parts = bot_api.split_text("\n".join(["x" * 100] * 100), limit=1000)
    assert len(parts) > 1 and all(len(p) <= 1000 for p in parts)


def test_settings_route_masks_the_token(client):
    r = client.post("/api/telegram", json={"token": "123456:ABCDEFGHIJKLMNOPQRSTUV", "enabled": False}).json()
    assert r["token_set"] and "ABCDEFGHIJKLMNOPQRSTUV" not in r["masked_token"]
    client.post("/api/telegram", json={"token": r["masked_token"]})          # masked value never overwrites
    assert service.get_token() == "123456:ABCDEFGHIJKLMNOPQRSTUV"


def test_frontend_route_does_not_leave_ui_dist(client):
    r = client.get("/..%2f..%2fengine%2fconfig.py")
    assert "DB_PATH" not in r.text
