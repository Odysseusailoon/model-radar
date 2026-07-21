"""Weekly digest — the narrative deliverable the GTM team actually opens.

The overview dashboard (`stats.py`) answers "what does the whole corpus look
like." This module answers a different question: "what happened *this week* that
I should act on," rolled up per product into a small set of highlighted items
(new partnerships, fresh demos, notable expert takes, eval/benchmark moves) with
a week-over-week delta so a reader can skim it in a minute.

Rows for the window are pulled once and bucketed in Python — the window is small
and bounded, and it keeps the logic identical on Postgres and SQLite (tests),
just like the daily series in stats.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .models import Evidence, Product

SIGNAL_CATEGORIES = ("demo", "customer_case", "expert_review")
# How many items to surface per highlight list, per product.
TOP_N = 5


def _flag(ev: Evidence, key: str) -> bool:
    return bool((ev.classification or {}).get(key))


def engagement(ev: Evidence) -> int:
    """Weighted engagement: a retweet is a stronger endorsement than a like (it
    re-broadcasts to a new audience), so RTs are weighted 2x."""
    return ((ev.like_count or 0) + 2 * (ev.retweet_count or 0)
            + (ev.quote_count or 0) + (ev.reply_count or 0))


def impact(ev: Evidence) -> int:
    """Ranking score combining reach (followers) AND traction (engagement), so a
    smaller account's viral tweet can outrank a big account's ignored one.
    followers are divided down to sit on a comparable scale to engagement."""
    return engagement(ev) + (ev.author_followers or 0) // 100


def _passes_floor(ev: Evidence, settings) -> bool:
    """Quality gate for the digest highlight lists (the GTM deliverable).

    Keeps out the junk-small-account problem, but credits impact: an author is
    credible if they have real reach (follower floor) OR the tweet went viral
    (engagement floor) — a 50-follower account with a 5k-like tweet is worth
    surfacing. Category-specific: partnership is an event (no author gate), a
    demo is about the artifact (needs genuine product media). Non-English rows
    are excluded here too (belt-and-suspenders; collection already filters).
    Everything still lives in the DB / feed regardless of this gate.
    """
    if settings.collect_lang and ev.lang and ev.lang != settings.collect_lang:
        return False
    conf = ev.confidence or 0.0
    if conf < settings.digest_min_confidence:
        return False
    followers = ev.author_followers or 0
    viral = engagement(ev) >= settings.digest_min_engagement
    cat = ev.category
    if cat == "partnership":
        return True
    if cat == "expert_review":
        return followers >= settings.digest_min_followers_expert or viral
    if cat == "customer_case":
        return followers >= settings.digest_min_followers_case or viral
    if cat == "demo":
        return _flag(ev, "has_media_evidence")
    return True


def _benchmarks(ev: Evidence) -> list[str]:
    return [b for b in ((ev.classification or {}).get("benchmark_names") or []) if b]


@dataclass
class ProductDigest:
    id: int
    name: str
    total: int = 0
    prev_total: int = 0
    reach: int = 0
    by_category: dict = field(default_factory=dict)
    partnerships: list = field(default_factory=list)
    demos: list = field(default_factory=list)
    customer_cases: list = field(default_factory=list)
    expert_reviews: list = field(default_factory=list)
    eval_hits: list = field(default_factory=list)
    top_quote: Optional[Evidence] = None
    top_voice: Optional[Evidence] = None

    @property
    def signal(self) -> int:
        return sum(self.by_category.get(c, 0) for c in SIGNAL_CATEGORIES)

    @property
    def delta(self) -> int:
        return self.total - self.prev_total

    @property
    def is_quiet(self) -> bool:
        return self.total == 0

    @property
    def has_highlights(self) -> bool:
        return bool(
            self.partnerships or self.demos or self.customer_cases
            or self.expert_reviews or self.eval_hits
        )


@dataclass
class Digest:
    days: int
    start: datetime
    end: datetime
    products: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(p.total for p in self.products)

    @property
    def partnership_count(self) -> int:
        return sum(len(p.partnerships) for p in self.products)

    @property
    def eval_count(self) -> int:
        return sum(len(p.eval_hits) for p in self.products)

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def _rows_in_window(session: Session, start: datetime, end: datetime) -> list[Evidence]:
    """Evidence whose effective timestamp (posted_at, else created_at) falls in
    [start, end). Bucketed in Python by the caller."""
    stmt = (
        select(Evidence)
        .options(joinedload(Evidence.product))
        .where(func.coalesce(Evidence.posted_at, Evidence.created_at) >= start)
        .where(func.coalesce(Evidence.posted_at, Evidence.created_at) < end)
    )
    return list(session.scalars(stmt))


def build_digest(session: Session, days: int = 7) -> Digest:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    settings = get_settings()
    products = list(session.scalars(select(Product).order_by(Product.id)))
    pd = {p.id: ProductDigest(id=p.id, name=p.name) for p in products}

    # Previous-window totals (counts only) for the week-over-week delta.
    prev_rows = session.execute(
        select(Evidence.product_id, func.count(Evidence.id))
        .where(func.coalesce(Evidence.posted_at, Evidence.created_at) >= prev_start)
        .where(func.coalesce(Evidence.posted_at, Evidence.created_at) < start)
        .group_by(Evidence.product_id)
    ).all()
    for pid, n in prev_rows:
        if pid in pd:
            pd[pid].prev_total = int(n)

    for ev in _rows_in_window(session, start, now):
        d = pd.get(ev.product_id)
        if d is None:  # evidence for a deleted product — skip
            continue
        d.total += 1
        cat = ev.category or "unclassified"
        d.by_category[cat] = d.by_category.get(cat, 0) + 1  # raw volume (unfiltered)
        if cat in SIGNAL_CATEGORIES:
            d.reach += ev.author_followers or 0
        # Highlight lists apply the quality floor; eval_signal is benchmark-based
        # so it stands on its own.
        if _passes_floor(ev, settings):
            if cat == "partnership":
                d.partnerships.append(ev)
            elif cat == "demo":
                d.demos.append(ev)
            elif cat == "customer_case":
                d.customer_cases.append(ev)
            elif cat == "expert_review":
                d.expert_reviews.append(ev)
        if _flag(ev, "eval_signal"):
            d.eval_hits.append(ev)

    for d in pd.values():
        # Rank highlights by impact = reach + traction, so viral tweets surface.
        d.partnerships.sort(key=impact, reverse=True)
        d.demos.sort(key=impact, reverse=True)
        d.customer_cases.sort(key=impact, reverse=True)
        d.expert_reviews.sort(key=impact, reverse=True)
        d.eval_hits.sort(key=lambda e: (e.posted_at or e.created_at or start), reverse=True)

        marketable = [e for e in d.demos + d.customer_cases + d.expert_reviews
                      if _flag(e, "usable_for_marketing") and (e.classification or {}).get("quotable_excerpt")]
        d.top_quote = max(marketable, key=impact, default=None)
        signal_rows = d.demos + d.customer_cases + d.expert_reviews
        d.top_voice = max(signal_rows, key=impact, default=None)

        d.partnerships = d.partnerships[:TOP_N]
        d.demos = d.demos[:TOP_N]
        d.customer_cases = d.customer_cases[:TOP_N]
        d.expert_reviews = d.expert_reviews[:TOP_N]
        d.eval_hits = d.eval_hits[:TOP_N]

    ordered = [pd[p.id] for p in products]
    # Loudest week first; quiet products sink to the bottom.
    ordered.sort(key=lambda d: d.total, reverse=True)
    return Digest(days=days, start=start, end=now, products=ordered)
