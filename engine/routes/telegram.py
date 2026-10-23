"""Telegram bot settings & manual sends (Pengaturan → Telegram)."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..telegram import bot_api, service
from ..telegram.bot_api import TelegramError

router = APIRouter()


class TelegramSettings(BaseModel):
    token: Optional[str] = None
    enabled: Optional[bool] = None
    chat_id: Optional[int] = None
    chat_title: Optional[str] = None
    markets: Optional[List[str]] = None
    send: Optional[Dict[str, bool]] = None
    commands: Optional[bool] = None


class TokenTest(BaseModel):
    token: Optional[str] = None


def _mask(token: str) -> str:
    return f"{token[:6]}…{token[-4:]}" if len(token) > 12 else ("***" if token else "")


def _view() -> Dict[str, Any]:
    token = service.get_token()
    return {"config": service.get_config(), "token_set": bool(token), "masked_token": _mask(token),
            "status": service.status(), "chats": service.detected_chats()}


@router.get("/api/telegram")
def get_telegram():
    return _view()


@router.post("/api/telegram")
def update_telegram(req: TelegramSettings):
    if req.token is not None and req.token.strip() and req.token.strip() != _mask(service.get_token()):
        service.set_token(req.token)
    changes = {k: v for k, v in req.model_dump(exclude_none=True).items() if k != "token"}
    if changes:
        service.save_config(changes)
    if service.get_config()["enabled"]:
        service.start()
    return _view()


@router.post("/api/telegram/test")
def test_token(req: TokenTest):
    token = (req.token or "").strip()
    if not token or token == _mask(service.get_token()):
        token = service.get_token()
    try:
        me = bot_api.get_me(token)
    except TelegramError as e:
        if e.code == 401:
            return {"ok": False, "message": "Token bot tidak valid — salin ulang token dari @BotFather."}
        return {"ok": False, "message": str(e)}
    return {"ok": True, "username": me.get("username"),
            "message": f"Token valid: @{me.get('username')}. Masukkan bot ke grup, lalu ketik /start di grup."}


SENDERS = {
    "test": lambda: "✅ Bot SAHAM terhubung ke grup ini. Ketik /bantuan untuk daftar perintah.",
    "daily_plan": lambda: service.build_daily_plan(service.get_config()["markets"][0]),
    "midday": lambda: service.build_midday(service.get_config()["markets"][0]),
    "weekly": lambda: service.build_weekly(service.get_config()["markets"][0]),
}


@router.post("/api/telegram/send/{kind}")
def send_now(kind: str):
    if kind not in SENDERS:
        raise HTTPException(status_code=404, detail="Jenis pesan tidak dikenal")
    text = SENDERS[kind]()
    if not text:
        return {"ok": False, "message": "Belum ada data untuk pesan ini (menunggu penutupan final / hasil scan)."}
    ok = service.send(text, f"manual:{kind}")
    return {"ok": ok, "message": "Terkirim." if ok else (service.status().get("last_error") or "Gagal mengirim.")}
