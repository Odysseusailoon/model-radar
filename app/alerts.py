"""Feishu (Lark) alerting via custom-bot webhook.

Alert rules (per spec):
  * high_signal  : category in {demo, customer_case, expert_review}
                   AND confidence >= threshold AND author_followers >= min
  * mega_mention : author_followers >= mega threshold, regardless of category

Every send is deduped through the alerts_sent table (tweet_id + alert_type).
"""
from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AlertSent, Evidence, Product

log = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    "demo": "真实 Demo",
    "customer_case": "客户 Case",
    "expert_review": "大佬评价",
    "news": "资讯",
    "promo": "推广",
    "irrelevant": "无关",
}
_EVIDENCE_CATEGORIES = {"demo", "customer_case", "expert_review"}


def _already_sent(session: Session, tweet_id: str, alert_type: str) -> bool:
    return session.scalar(
        select(AlertSent.id).where(
            AlertSent.tweet_id == tweet_id, AlertSent.alert_type == alert_type
        )
    ) is not None


def _decide_alert_type(ev: Evidence, settings) -> str | None:
    followers = ev.author_followers or 0
    data = ev.classification or {}
    relevant = data.get("relevant", False) and ev.category != "irrelevant"

    if followers >= settings.alert_mega_followers and relevant:
        return "mega_mention"
    if (
        ev.category in _EVIDENCE_CATEGORIES
        and (ev.confidence or 0) >= settings.alert_min_confidence
        and followers >= settings.alert_min_followers
    ):
        return "high_signal"
    return None


def _build_card(product: Product, ev: Evidence, alert_type: str) -> dict:
    data = ev.classification or {}
    cat_label = _CATEGORY_LABELS.get(ev.category or "", ev.category or "未分类")
    header_title = (
        f"🚨 {product.name} · 高影响力提及" if alert_type == "mega_mention"
        else f"⭐ {product.name} · 新证据 [{cat_label}]"
    )
    sentiment = (ev.sentiment or "neutral")
    sent_emoji = {"positive": "🟢", "neutral": "⚪", "negative": "🔴"}.get(sentiment, "⚪")
    excerpt = data.get("quotable_excerpt") or ev.text or ""
    summary = data.get("summary_zh") or ""
    signals = "、".join(data.get("author_credibility_signals") or []) or "—"

    content_lines = [
        f"**作者**:@{ev.author_handle}（{ev.author_followers:,} 粉丝）",
        f"**可信度信号**:{signals}",
        f"**分类**:{cat_label}　**情感**:{sent_emoji}{sentiment}　**置信度**:{ev.confidence:.2f}",
        f"**摘要**:{summary}",
        f"**可引用**:“{excerpt}”",
        f"**互动**:❤{ev.like_count} 🔁{ev.retweet_count} 💬{ev.reply_count}",
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": "red" if alert_type == "mega_mention" else "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(content_lines)}},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看原推 ↗"},
                            "type": "primary",
                            "url": ev.tweet_url or "",
                        }
                    ],
                },
            ],
        },
    }


def _post_feishu(webhook_url: str, payload: dict, max_retries: int = 3) -> bool:
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.post(webhook_url, json=payload, timeout=10.0)
            resp.raise_for_status()
            body = resp.json()
            # Feishu returns {"code":0,...} on success, or StatusCode/StatusMessage.
            if body.get("code", 0) not in (0, None) and body.get("StatusCode", 0) != 0:
                log.error("Feishu rejected message: %s", body)
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
    log.error("Feishu send failed after %d attempts: %s", max_retries, last_exc)
    return False


def maybe_alert(session: Session, product: Product, ev: Evidence) -> bool:
    """Send an alert if this evidence qualifies and hasn't been alerted. Returns
    True if a card was sent."""
    settings = get_settings()
    if not settings.feishu_webhook_url:
        return False

    alert_type = _decide_alert_type(ev, settings)
    if alert_type is None:
        return False
    if _already_sent(session, ev.tweet_id, alert_type):
        return False

    ok = _post_feishu(settings.feishu_webhook_url, _build_card(product, ev, alert_type))
    if not ok:
        return False

    session.add(AlertSent(tweet_id=ev.tweet_id, alert_type=alert_type))
    session.commit()
    log.info("Alert sent (%s) for tweet %s by @%s", alert_type, ev.tweet_id, ev.author_handle)
    return True
