"""Feishu transport — the ONLY place that talks to the Feishu/Lark open API.

Handles: tenant-access-token auth (cached), sending interactive cards to a chat,
and inbound event verification. Kept separate from bot.py so the bot's logic
stays pure and unit-testable; card *building* is a pure function here too.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from .config import get_settings

log = logging.getLogger("gtm.feishu")

_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
_MESSAGE_PATH = "/open-apis/im/v1/messages"

_token_lock = threading.Lock()
_token_cache = {"value": "", "exp": 0.0}


def get_tenant_token() -> str:
    """Cached tenant_access_token for the app. Refreshed ~5 min before expiry."""
    s = get_settings()
    now = time.time()
    with _token_lock:
        if _token_cache["value"] and now < _token_cache["exp"]:
            return _token_cache["value"]
        resp = httpx.post(
            f"{s.feishu_base_url}{_TOKEN_PATH}",
            json={"app_id": s.feishu_app_id, "app_secret": s.feishu_app_secret},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token error: {data}")
        _token_cache["value"] = data["tenant_access_token"]
        _token_cache["exp"] = now + int(data.get("expire", 7200)) - 300
        return _token_cache["value"]


def build_card(title: str, text: str, template: str = "blue", url: str = "") -> dict:
    """A lark_md interactive card. `text` may contain markdown/newlines."""
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": text}}]
    if url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": "查看原推 ↗"},
            "type": "primary", "url": url,
        }]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def send_card(chat_id: str, card: dict) -> bool:
    """Send an interactive card to a chat. Returns True on success."""
    s = get_settings()
    if not (s.feishu_app_id and s.feishu_app_secret):
        log.warning("Feishu app credentials missing; cannot send card")
        return False
    chat_id = chat_id or s.feishu_bot_chat_id
    if not chat_id:
        log.warning("No target chat_id for Feishu card")
        return False
    try:
        import json as _json
        resp = httpx.post(
            f"{s.feishu_base_url}{_MESSAGE_PATH}",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {get_tenant_token()}"},
            json={"receive_id": chat_id, "msg_type": "interactive", "content": _json.dumps(card)},
            timeout=10.0,
        )
        body = resp.json()
        if body.get("code") != 0:
            log.error("Feishu send failed: %s", body)
            return False
        return True
    except Exception:
        log.exception("Feishu send_card failed")
        return False


def send_dict(chat_id: str, payload: dict, template: str = "blue") -> bool:
    """Convenience: send a {title, text[, url]} dict as a card."""
    return send_card(chat_id, build_card(payload.get("title", "Model Radar"),
                                         payload.get("text", ""), template, payload.get("url", "")))


def verify_event(token_from_event: str) -> bool:
    """Verify an inbound event's verification token (constant-time-ish)."""
    import hmac
    s = get_settings()
    if not s.feishu_verification_token:
        return False
    return hmac.compare_digest(token_from_event or "", s.feishu_verification_token)
