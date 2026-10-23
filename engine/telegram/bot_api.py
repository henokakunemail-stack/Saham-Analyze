"""Minimal Telegram Bot API client (plain HTTPS via requests; no extra dependency).

The bot token is part of every URL, so it is scrubbed from every error message before it can
reach a log line or the UI.
"""
from typing import Any, Dict, List, Optional

import requests

API = "https://api.telegram.org"
MAX_TEXT = 4000  # Telegram's limit is 4096 characters per message; keep a margin


class TelegramError(Exception):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def _scrub(text: str, token: str) -> str:
    return text.replace(token, "<token>") if token else text


def call(token: str, method: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 20) -> Any:
    if not token:
        raise TelegramError("Token bot belum diisi.")
    try:
        resp = requests.post(f"{API}/bot{token}/{method}", json=payload or {}, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise TelegramError(f"Tidak bisa menghubungi Telegram: {_scrub(str(e), token)}")
    try:
        data = resp.json()
    except ValueError:
        raise TelegramError(f"Respons Telegram tidak valid (HTTP {resp.status_code}).", resp.status_code)
    if not data.get("ok"):
        desc = _scrub(str(data.get("description", "")), token)
        raise TelegramError(desc or f"HTTP {resp.status_code}", data.get("error_code") or resp.status_code)
    return data.get("result")


def get_me(token: str) -> Dict[str, Any]:
    return call(token, "getMe", timeout=10)


def split_text(text: str, limit: int = MAX_TEXT) -> List[str]:
    """Split on line breaks so HTML tags (always within one line here) stay balanced."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            parts.append(cur.rstrip("\n"))
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur.rstrip("\n"))
    return parts


def send_message(token: str, chat_id: Any, text: str, reply_to: Optional[int] = None) -> None:
    for i, part in enumerate(split_text(text)):
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": part, "parse_mode": "HTML",
                                   "disable_web_page_preview": True}
        if reply_to and i == 0:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        call(token, "sendMessage", payload)


def get_updates(token: str, offset: Optional[int], timeout: int = 25) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    return call(token, "getUpdates", payload, timeout=timeout + 10) or []


def set_commands(token: str, commands: List[Dict[str, str]]) -> None:
    call(token, "setMyCommands", {"commands": commands})


def delete_webhook(token: str) -> None:
    """Long polling does not work while a webhook is set on the same bot."""
    call(token, "deleteWebhook", {"drop_pending_updates": False})
