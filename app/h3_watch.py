"""H3 launch watch — near-real-time X buzz stream for the launch window.

Every `h3_watch_interval_min` minutes, search X for the H3 launch tags
(@Hailuo_AI mention / #MiniMaxH3) and push ONE digest card of the new posts to
the GTM group. This intentionally bypasses the bot's PushGate (daily caps and
quiet hours): it exists only for the launch window and is switched off with
H3_WATCH_ENABLED=false when the window is over.

Watermark is in-memory (max snowflake id seen). On process start the first
cycle only establishes the watermark and pushes nothing, so a redeploy never
floods the chat with old posts.
"""
from __future__ import annotations

import logging

from . import feishu
from .config import get_settings
from .xclient import XDataClient

log = logging.getLogger(__name__)

_watermark: int = 0  # max tweet id already reported (0 = not initialised)

MAX_ITEMS_IN_CARD = 10
MAX_PAGES = 3


def _eng(t) -> int:
    return (t.like_count or 0) + 2 * (t.retweet_count or 0) + (t.reply_count or 0)


def _fmt_count(n: int) -> str:
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


def build_h3_card(tweets: list) -> dict:
    """One digest card for a batch of new posts (newest cycle only)."""
    tweets = sorted(tweets, key=_eng, reverse=True)
    lines = []
    for t in tweets[:MAX_ITEMS_IN_CARD]:
        au = t.author
        text = (t.text or "").replace("\n", " ")[:80]
        lines.append(
            f"❤{t.like_count or 0} · @{au.handle}({_fmt_count(au.followers or 0)}粉) "
            f"{text} [原帖]({t.url})"
        )
    body = "\n".join(lines)
    extra = len(tweets) - MAX_ITEMS_IN_CARD
    if extra > 0:
        body += f"\n… 另有 {extra} 条(全量见 H3 X舆情表)"
    return feishu.build_card(
        f"🚀 H3 舆情 · 新增 {len(tweets)} 条", body, template="red",
    )


def run_h3_watch() -> dict:
    """One watch cycle. Returns stats (also used by /debug/h3-watch)."""
    global _watermark
    s = get_settings()
    if not s.h3_watch_enabled:
        return {"skipped": "disabled"}
    client = XDataClient(api_key=s.twitterapi_key, base_url=s.twitterapi_base_url)

    try:
        tweets = list(client.search_recent(s.h3_watch_query, max_pages=MAX_PAGES))
    except Exception as exc:
        log.exception("H3 watch search failed")
        return {"error": str(exc)}

    def _tid(t) -> int:
        try:
            return int(t.id)
        except (TypeError, ValueError):
            return 0

    max_id = max((_tid(t) for t in tweets), default=0)

    if _watermark == 0:
        # First cycle after (re)start: establish the watermark, never flood.
        _watermark = max_id
        log.info("H3 watch initialised, watermark=%d (%d posts seen)", max_id, len(tweets))
        return {"initialised": True, "seen": len(tweets)}

    new = [t for t in tweets if _tid(t) > _watermark]
    if max_id > _watermark:
        _watermark = max_id
    if not new:
        return {"new": 0}

    pushed = feishu.send_card(s.feishu_bot_chat_id, build_h3_card(new))
    log.info("H3 watch: %d new post(s), pushed=%s", len(new), pushed)
    return {"new": len(new), "pushed": pushed}
