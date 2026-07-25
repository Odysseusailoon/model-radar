"""Feishu GTM bot — the brain.

Design principle: **restraint over reach**. A GTM intel bot dies the moment it
becomes a muted firehose, so this module is deliberately strict about what is
allowed to *interrupt* a person versus what waits for the weekly digest versus
what only ever answers on demand. See `triage()` and `PushGate`.

Three delivery tiers:
  🔴 real-time push  — launches, partnership signals, genuinely viral hits only
  🟡 scheduled digest — everything else worth surfacing, batched
  🟢 pull (query)     — the command handlers below; never pushes

Transport (sending cards / receiving events) lives in feishu.py; this module is
pure logic so it is fully unit-testable without touching Feishu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .config import get_settings
from .digest import build_digest, engagement, impact
from .models import Evidence
from .queries import EvidenceFilter, query_evidence

# --------------------------------------------------------------------------
# Importance triage — the core judgement of "what deserves to interrupt"
# --------------------------------------------------------------------------
# Categories that are events (worth real-time) vs accumulation (worth digest).
_EVENT_CATEGORIES = {"partnership"}
# Words in a tweet that signal a model LAUNCH (time-sensitive competitive intel).
_LAUNCH_RX = re.compile(
    r"\b(launch(?:ing|ed|es)?|releas(?:e|ed|ing)|introduc(?:e|ing)|announc(?:e|ing|ed)|"
    r"now available|out now|unveil(?:ed|ing)?|drops?|shipping|open[- ]?sourc(?:e|ed|ing)|"
    r"weights? (?:are )?(?:out|available|released))\b",
    re.I,
)


def is_launch(ev: Evidence) -> bool:
    """A launch is a product/version release. High-signal, time-sensitive."""
    text = (ev.text or "")
    data = ev.classification or {}
    if not _LAUNCH_RX.search(text):
        return False
    # Must plausibly be about a tracked product, not a generic "we launched a blog".
    if not data.get("relevant", True) or ev.category == "irrelevant":
        return False
    # A launch is usually news/promo/partnership from an on-topic, non-trivial source.
    return ev.category in {"news", "promo", "partnership", "demo", "expert_review"}


@dataclass
class Verdict:
    tier: str            # "realtime" | "digest" | "drop"
    reason: str
    kind: str = ""       # "launch" | "partnership" | "viral" | "mega" | ""


def triage(ev: Evidence, settings=None) -> Verdict:
    """Decide the delivery tier for one piece of evidence. This is where the
    'know what's important' judgement lives — deliberately conservative so that
    real-time pushes stay rare and therefore respected."""
    s = settings or get_settings()
    followers = ev.author_followers or 0
    conf = ev.confidence or 0.0
    eng = engagement(ev)
    data = ev.classification or {}
    relevant = bool(data.get("relevant", True)) and ev.category != "irrelevant"

    if not relevant or ev.classification_failed:
        return Verdict("drop", "irrelevant or unclassified")

    # --- real-time bar: only launches, partnerships, mega reach, or true virality
    if is_launch(ev):
        return Verdict("realtime", "model launch / release", "launch")
    if ev.category == "partnership" and conf >= s.alert_min_confidence:
        return Verdict("realtime", "partnership / integration signal", "partnership")
    if followers >= s.alert_mega_followers:
        return Verdict("realtime", f"mega account ({followers:,} followers)", "mega")
    if eng >= s.bot_viral_engagement:
        return Verdict("realtime", f"viral ({eng:,} weighted engagement)", "viral")

    # --- digest bar: credible marketing evidence, batched not pushed
    if ev.category in {"demo", "customer_case", "expert_review"} and conf >= s.digest_min_confidence:
        if ev.category == "expert_review" and followers < s.digest_min_followers_expert and eng < s.digest_min_engagement:
            return Verdict("drop", "expert take from small account, not viral")
        return Verdict("digest", "credible evidence, batched to digest")
    if data.get("eval_signal"):
        return Verdict("digest", "benchmark / eval mention")

    return Verdict("drop", "below the bar")


# --------------------------------------------------------------------------
# Push gate — enforces the anti-spam guardrails on real-time pushes
# --------------------------------------------------------------------------
@dataclass
class PushGate:
    """Per-run guard that turns triage verdicts into an actual push decision:
    daily cap, quiet hours, and (via the caller) dedup. Overflow is meant to be
    folded into the digest, not dropped silently."""
    daily_cap: int
    quiet_start: int          # UTC hour inclusive
    quiet_end: int            # UTC hour exclusive
    sent_today: int = 0
    overflow: list = field(default_factory=list)

    def in_quiet_hours(self, now: datetime) -> bool:
        h = now.hour
        if self.quiet_start == self.quiet_end:
            return False
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= h < self.quiet_end
        return h >= self.quiet_start or h < self.quiet_end  # wraps midnight

    def allow(self, verdict: Verdict, now: datetime) -> bool:
        """True if this real-time push may go out now. Launches bypass quiet
        hours and the cap (a competitor launch at 3am still matters); everything
        else respects both. Non-allowed items are recorded as overflow."""
        if verdict.tier != "realtime":
            return False
        if verdict.kind == "launch":
            self.sent_today += 1
            return True
        if self.in_quiet_hours(now):
            self.overflow.append(verdict.reason)
            return False
        if self.sent_today >= self.daily_cap:
            self.overflow.append(verdict.reason)
            return False
        self.sent_today += 1
        return True


# --------------------------------------------------------------------------
# Command parsing (inbound queries)
# --------------------------------------------------------------------------
COMMANDS = ("digest", "partnership", "launch", "demo", "review", "kol", "leaderboard", "help")
# Natural-language aliases → canonical command.
_ALIASES = {
    "周报": "digest", "摘要": "digest",
    "合作": "partnership", "partnerships": "partnership",
    "发布": "launch", "launches": "launch", "新模型": "launch",
    "大佬评价": "review", "评价": "review", "reviews": "review",
    "demos": "demo", "demo": "demo",
    "谁在聊": "kol", "kol": "kol",
    "榜单": "leaderboard", "排名": "leaderboard",
    "帮助": "help", "?": "help",
}


def parse_command(text: str) -> tuple[str, str]:
    """Return (command, args). Accepts '/digest MiniMax', '@bot review GLM',
    or Chinese aliases. Unknown input maps to ('help', '')."""
    if not text:
        return "help", ""
    # strip a leading @bot mention and any leading slash
    t = re.sub(r"^\s*@\S+\s*", "", text).strip()
    t = t.lstrip("/").strip()
    if not t:
        return "help", ""
    parts = t.split(None, 1)
    head = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    if head in COMMANDS:
        return head, args
    if head in _ALIASES:
        return _ALIASES[head], args
    # Chinese head with no space (e.g. "周报MiniMax")
    for k, cmd in _ALIASES.items():
        if t.startswith(k):
            return cmd, t[len(k):].strip()
    return "help", ""


# --------------------------------------------------------------------------
# Query handlers — pull-only. Each returns a plain dict the transport renders.
# --------------------------------------------------------------------------
def _product_id(db: Session, name: str) -> Optional[int]:
    """Resolve a user-typed product reference. Matches the product name first,
    then its keywords — so aliases like 'Hailuo' resolve to the MiniMax product
    whose keyword list contains them."""
    if not name:
        return None
    from .crud import list_products
    name_l = name.strip().lower()
    products = list_products(db)
    for p in products:
        if name_l in p.name.lower():
            return p.id
    for p in products:
        for kw in (p.keywords or []):
            if name_l in str(kw).strip().strip('"').lower():
                return p.id
    return None


def _fmt_n(n) -> str:
    """Compact Chinese-style count: 316748 -> 31.7万, 4770 -> 4,770."""
    n = int(n or 0)
    if n >= 10_000:
        v = f"{n / 10_000:.1f}"
        return (v.rstrip("0").rstrip(".") or "0") + "万"
    return f"{n:,}"


def _line(ev: Evidence) -> str:
    """One evidence item as a card block: author + reach + engagement on the
    first line, the quotable bit on the second, inline link on the third."""
    data = ev.classification or {}
    q = (data.get("quotable_excerpt") or data.get("summary_zh") or (ev.text or ""))[:140]
    head = f"**@{ev.author_handle}**  {_fmt_n(ev.author_followers)}粉 · ❤{_fmt_n(ev.like_count)} 🔁{_fmt_n(ev.retweet_count)}"
    when = f" · {ev.posted_at.strftime('%m-%d')}" if ev.posted_at else ""
    link = f"\n[原推 ↗]({ev.tweet_url})" if ev.tweet_url else ""
    return f"{head}{when}\n{q}{link}"


from .feishu import ITEM_SEP


def handle_digest(db: Session, args: str) -> dict:
    pid = _product_id(db, args)
    dg = build_digest(db, days=7)
    products = [p for p in dg.products if (pid is None or p.id == pid)]
    blocks = [f"📅 {dg.start.strftime('%m-%d')} → {dg.end.strftime('%m-%d')} · 近 7 天"]
    for p in products:
        if p.is_quiet:
            continue
        arrow = "📈" if p.delta > 0 else ("📉" if p.delta < 0 else "➖")
        lines = [f"**{p.name}** — {p.total} 条 {arrow} 环比 {p.delta:+d}",
                 f"🤝 合作 {len(p.partnerships)} · 🎬 Demo {len(p.demos)} · 🗣 评价 {len(p.expert_reviews)} · 📊 评测 {len(p.eval_hits)}"]
        if p.top_quote:
            data = p.top_quote.classification or {}
            q = data.get("quotable_excerpt", "")[:110]
            if q:
                lines.append(f"💬 “{q}” — @{p.top_quote.author_handle}")
        blocks.append("\n".join(lines))
    if len(blocks) == 1:
        blocks.append("本周暂无新证据。")
    return {"title": "📊 GTM 周报", "template": "indigo", "text": ITEM_SEP.join(blocks)}


def _evidence_card(db: Session, title: str, template: str, f: EvidenceFilter, empty: str) -> dict:
    items = query_evidence(db, f)
    items = [e for e in items if (e.confidence or 0) >= 0.5]
    items.sort(key=impact, reverse=True)
    top = items[:8]
    blocks = [f"共 {len(items)} 条 · 按影响力(粉丝+互动)排序,展示前 {len(top)} 条"] if top else []
    blocks += [_line(e) for e in top]
    if not blocks:
        blocks = [empty]
    return {"title": title, "template": template, "text": ITEM_SEP.join(blocks)}


def handle_partnership(db: Session, args: str) -> dict:
    return _evidence_card(db, "🤝 近期合作/集成情报", "turquoise",
                          EvidenceFilter(product_id=_product_id(db, args), category="partnership", limit=40),
                          "近期无合作信号。")


def handle_demo(db: Session, args: str) -> dict:
    return _evidence_card(db, f"🎬 真实 Demo{(' · '+args) if args else ''}", "green",
                          EvidenceFilter(product_id=_product_id(db, args), category="demo", limit=40),
                          "近期无可引用 demo。")


def handle_review(db: Session, args: str) -> dict:
    s = get_settings()
    return _evidence_card(db, f"🗣 大佬评价{(' · '+args) if args else ''}", "orange",
                          EvidenceFilter(product_id=_product_id(db, args), category="expert_review",
                                         min_followers=s.digest_min_followers_expert, limit=40),
                          "近期无够格的大佬评价。")


def handle_launch(db: Session, args: str) -> dict:
    f = EvidenceFilter(product_id=_product_id(db, args), limit=120)
    items = [e for e in query_evidence(db, f) if is_launch(e)]
    items.sort(key=impact, reverse=True)
    top = items[:8]
    blocks = ([f"共 {len(items)} 条发布/上线信号,展示前 {len(top)} 条"] + [_line(e) for e in top]) if top else ["近期无发布动向。"]
    return {"title": "🚀 发布动向", "template": "red", "text": ITEM_SEP.join(blocks)}


def handle_kol(db: Session, args: str) -> dict:
    """Who (in the stored evidence) is talking about <topic>. For live X search
    across the full mutual list, the caller wires in the collector; this handler
    answers from already-collected evidence."""
    topic = args.strip()
    if not topic:
        return {"title": "用法", "text": "用法:/kol <话题>,例如 /kol flux"}
    items = query_evidence(db, EvidenceFilter(limit=400))
    tl = topic.lower()
    hits = [e for e in items if tl in (e.text or "").lower()]
    hits.sort(key=lambda e: e.author_followers or 0, reverse=True)
    seen, lines = set(), [f"🔎 在聊「{topic}」的人"]
    for e in hits:
        if e.author_handle in seen:
            continue
        seen.add(e.author_handle)
        lines.append(f"• {_line(e)}")
        if len(seen) >= 12:
            break
    if len(lines) == 1:
        lines.append(f"证据库里暂无提到「{topic}」的人(可跑一次实时搜索)。")
    return {"title": f"KOL · {topic}", "text": "\n".join(lines)}


def handle_help(db: Session, args: str) -> dict:
    return {"title": "Model Radar 指令", "text": (
        "🛰️ **Model Radar** — GTM 情报 bot\n"
        "`/digest [产品]` 本周周报\n"
        "`/partnership` 合作/集成动向\n"
        "`/launch` 发布/上线动向\n"
        "`/demo <产品>` 真实 demo\n"
        "`/review <产品>` 大佬评价\n"
        "`/kol <话题>` 谁在聊某话题\n"
        "`/leaderboard` 评测榜单\n"
        "中文也行:周报 / 合作 / 大佬评价 / 谁在聊 flux")}


def handle_leaderboard(db: Session, args: str) -> dict:
    return {"title": "评测榜单", "text": (
        "📊 评测榜单接入中(Artificial Analysis / LMArena)。当前从证据库聚合 `eval_signal`:\n"
        + handle_kol(db, "leaderboard")["text"])}


_HANDLERS = {
    "digest": handle_digest, "partnership": handle_partnership, "launch": handle_launch,
    "demo": handle_demo, "review": handle_review, "kol": handle_kol,
    "leaderboard": handle_leaderboard, "help": handle_help,
}


def dispatch(db: Session, text: str) -> dict:
    """Parse an inbound message and return the reply card dict."""
    cmd, args = parse_command(text)
    return _HANDLERS.get(cmd, handle_help)(db, args)
