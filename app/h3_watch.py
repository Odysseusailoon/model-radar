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
    r"randomly|doesn'?t (work|follow)|fail|issue|problem|error", re.I)

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
    text = (t.text or "").replace("\n", " ")[:80]
    return (f"❤{t.like_count or 0} · @{au.handle} ({_fmt_count(au.followers or 0)}) "
            f"{text} [post]({t.url})")


def build_h3_card(tweets: list) -> dict:
    """English digest: feature tally + posts grouped positive / negative / top showcase."""
    tweets = sorted(tweets, key=_eng, reverse=True)
    groups = {"pos": [], "neg": [], "mixed": [], "neutral": []}
    feat_tally: dict[str, int] = {}
    for t in tweets:
        groups[_sentiment(t.text)].append(t)
        for name, pat in _FEATURES:
            if pat.search(t.text or ""):
                feat_tally[name] = feat_tally.get(name, 0) + 1

    parts = []
    if feat_tally:
        top_feats = sorted(feat_tally.items(), key=lambda kv: -kv[1])[:6]
        parts.append("**📌 Feature mentions:** " + " · ".join(f"{k} ×{v}" for k, v in top_feats))

    pos = groups["pos"]
    if pos:
        parts.append(f"**🟢 Positive ({len(pos)})**")
        parts += [_line(t) for t in pos[:4]]

    neg = groups["neg"] + groups["mixed"]
    if neg:
        parts.append(f"**🔴 Negative / issues ({len(neg)})**")
        parts += [_line(t) for t in neg[:4]]

    rest = groups["neutral"]
    if rest:
        parts.append(f"**⚪ Top showcase / other ({len(rest)})**")
        parts += [_line(t) for t in rest[:3]]

    shown = min(len(pos), 4) + min(len(neg), 4) + min(len(rest), 3)
    extra = len(tweets) - shown
    if extra > 0:
        parts.append(f"… +{extra} more → full data in the *H3 X Buzz* Feishu table")

    return feishu.build_card(
        f"🎬 H3 Buzz · {len(tweets)} new posts", "\n".join(parts), template="red",
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
