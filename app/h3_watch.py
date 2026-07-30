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

# English digest card: posts grouped by sentiment, plus a feature-mention tally.
import re

_POS = re.compile(
    r"amazing|insane|incredible|mind.?blow|beast|cooked|epic|wow\b|wild|stunning|"
    r"is back|alive|love (it|this|the)|best|impressive|blown|next level|game.?chang|"
    r"awesome|fantastic|effortless|quite good|really g(ood|reat)|so good|🔥|凄い|最強", re.I)
_NEG = re.compile(
    r"blurry|disappoint|stuck|can'?t (generate|find|see)|bug\b|broken|inconsist|"
    r"artifact|mistakes|worse|not (good|great)|unsatisf|paid partnership|refund|"
    r"randomly|doesn'?t (work|follow)|(?<!never )fail(?!s? to (amaze|impress|deliver))|issue|problem|error", re.I)

_FEATURES = [
    ("Lipsync/Audio", re.compile(r"lip.?sync|audio\s?(ref|track|input)|voice|singing|sound", re.I)),
    ("Omni Reference", re.compile(r"omni|12[\s-]?(asset|ref)|image ref|reference", re.I)),
    ("Img2Video", re.compile(r"img\s?2\s?vid|image.to.video|first frame|last frame", re.I)),
    ("2K Quality", re.compile(r"\b2k\b|resolution|quality", re.I)),
    ("Multi-shot", re.compile(r"multi.?shot|consisten|across shots", re.I)),
    ("Instruction", re.compile(r"instruction|follow|adher|prompt control", re.I)),
    ("Music Video", re.compile(r"music video|\bmv\b|concert|song", re.I)),
    ("Cinematic", re.compile(r"cinematic|film|movie|documentary", re.I)),
    ("Anime/Style", re.compile(r"anime|stylized", re.I)),
    ("vs Seedance", re.compile(r"seedance|sd2", re.I)),
    ("vs Veo/Sora", re.compile(r"\bveo\b|\bsora\b|kling", re.I)),
    ("Pricing", re.compile(r"cheap|price|credit|cost", re.I)),
    ("Speed", re.compile(r"fastest|so fast|speed", re.I)),
    ("Multilingual", re.compile(r"arabic|japanese|bulgarian|chinese|multilingual", re.I)),
    ("Open weights", re.compile(r"open.?weight|open.?source|weights", re.I)),
]


def _eng(t) -> int:
    return (t.like_count or 0) + 2 * (t.retweet_count or 0) + (t.reply_count or 0)


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _sentiment(text: str) -> str:
    p, n = bool(_POS.search(text or "")), bool(_NEG.search(text or ""))
    if p and n:
        return "mixed"
    if p:
        return "pos"
    if n:
        return "neg"
    return "neutral"


def _line(t) -> str:
    au = t.author
    text = (t.text or "").replace("\n", " ")[:90]
    return (f"**❤{t.like_count or 0}** 🔁{t.retweet_count or 0} · "
            f"[@{au.handle}](https://x.com/{au.handle}) ({_fmt_count(au.followers or 0)})\n"
            f"{text} [view ↗]({t.url})")


def _quality(tweets: list) -> list:
    """Display floor: drop reply-noise and zero-signal posts, keep one (best)
    post per author. A post earns its card slot with either engagement (❤≥5)
    or a real audience (≥800 followers); @-prefixed reply text is dropped
    outright (belt-and-braces next to the query-level -filter:replies)."""
    best: dict[str, object] = {}
    for t in tweets:
        text = (t.text or "").strip()
        if text.startswith("@"):
            continue
        if (t.like_count or 0) < 5 and (t.author.followers or 0) < 800:
            continue
        key = (t.author.handle or "").lower()
        if key not in best or _eng(t) > _eng(best[key]):
            best[key] = t
    return sorted(best.values(), key=_eng, reverse=True)


_SENT_EMOJI = {"pos": "🟢", "neg": "🔴", "mixed": "🟡", "neutral": "⚪"}


def _themes(text: str) -> list:
    return [name for name, pat in _FEATURES if pat.search(text or "")]


def build_h3_card(tweets: list) -> dict:
    """English digest grouped BY THEME: each top theme is its own hairline
    section with sentiment tally and its best posts; theme-less posts fall
    into a Showcase section."""
    tweets = sorted(tweets, key=_eng, reverse=True)
    by_theme: dict[str, list] = {}
    themeless = []
    for t in tweets:
        ths = _themes(t.text)
        if not ths:
            themeless.append(t)
            continue
        for th in ths[:2]:  # a post counts toward its two strongest themes
            by_theme.setdefault(th, []).append(t)

    pos_n = sum(1 for t in tweets if _sentiment(t.text) == "pos")
    neg_n = sum(1 for t in tweets if _sentiment(t.text) in ("neg", "mixed"))
    sections = [f"**Overview:** 🟢 {pos_n} positive · 🔴 {neg_n} issues · {len(tweets)} total"]

    def _titem(t) -> str:
        return f"{_SENT_EMOJI[_sentiment(t.text)]} {_line(t)}"

    shown_ids = set()
    top_themes = sorted(by_theme.items(), key=lambda kv: -len(kv[1]))[:5]
    for th, items in top_themes:
        neg_in = sum(1 for t in items if _sentiment(t.text) in ("neg", "mixed"))
        flag = f" · 🔴{neg_in}" if neg_in else ""
        picks = items[:2]
        shown_ids.update(id(t) for t in picks)
        body = "\n".join(_titem(t) for t in picks)
        sections.append(f"**🎯 {th.upper()} — {len(items)}{flag}**\n{body}")

    if themeless:
        picks = [t for t in themeless[:2]]
        shown_ids.update(id(t) for t in picks)
        body = "\n".join(_titem(t) for t in picks)
        sections.append(f"**📎 SHOWCASE / OTHER — {len(themeless)}**\n{body}")

    extra = len(tweets) - len(shown_ids)
    if extra > 0:
        sections.append(f"➕ **{extra} more** → filter by 主题 in the **H3 X Buzz** Feishu table")

    card = feishu.build_card(
        f"🎬 H3 Buzz · {len(tweets)} new posts", feishu.ITEM_SEP.join(sections), template="red",
    )
    for el in card["elements"]:
        if el.get("tag") == "note":
            el["elements"] = [{"tag": "plain_text",
                               "content": "🛰️ Model Radar · H3 watch · theme-grouped digest"}]
    return card


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

    worthy = _quality(new)
    if not worthy:
        log.info("H3 watch: %d new post(s), all below quality floor — no push", len(new))
        return {"new": len(new), "pushed": False, "filtered_out": len(new)}

    pushed = feishu.send_card(s.feishu_bot_chat_id, build_h3_card(worthy))
    log.info("H3 watch: %d new, %d shown, pushed=%s", len(new), len(worthy), pushed)
    return {"new": len(new), "shown": len(worthy), "pushed": pushed}


def run_h3_demo() -> dict:
    """Push a digest of the whole current search window (ignores the
    watermark; does not advance it). For previewing the card format."""
    s = get_settings()
    client = XDataClient(api_key=s.twitterapi_key, base_url=s.twitterapi_base_url)
    tweets = list(client.search_recent(s.h3_watch_query, max_pages=MAX_PAGES))
    worthy = _quality(tweets)
    if not worthy:
        return {"seen": len(tweets), "pushed": False}
    pushed = feishu.send_card(s.feishu_bot_chat_id, build_h3_card(worthy))
    return {"seen": len(tweets), "shown": len(worthy), "pushed": pushed}
