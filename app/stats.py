"""Dashboard aggregations.

Kept separate from `queries.py`: that module filters individual evidence rows
for the feed and CSV export, this one rolls them up for the overview charts.

All aggregation runs through SQLAlchemy core functions that behave the same on
Postgres and SQLite, so the dashboard is testable without a Postgres instance.
The daily series is bucketed in Python rather than SQL because date truncation
is the one place the two dialects genuinely diverge.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Evidence, Product

# Categories that represent usable marketing evidence, as opposed to chaff.
SIGNAL_CATEGORIES = ("demo", "customer_case", "expert_review")


@dataclass
class Overview:
    total: int = 0
    signal: int = 0
    pending: int = 0
    approved: int = 0
    failed: int = 0
    reach: int = 0
    products: list = field(default_factory=list)
    days: list = field(default_factory=list)
    series: dict = field(default_factory=dict)
    by_category: dict = field(default_factory=dict)
    by_sentiment: dict = field(default_factory=dict)
    top_voices: list = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    @property
    def signal_rate(self) -> float:
        return (self.signal / self.total * 100) if self.total else 0.0


def _base(product_id: Optional[int]):
    stmt = select(Evidence)
    if product_id:
        stmt = stmt.where(Evidence.product_id == product_id)
    return stmt


def _count(session: Session, product_id: Optional[int], *where) -> int:
    stmt = select(func.count(Evidence.id))
    if product_id:
        stmt = stmt.where(Evidence.product_id == product_id)
    for w in where:
        stmt = stmt.where(w)
    return int(session.scalar(stmt) or 0)


def build_overview(session: Session, product_id: Optional[int] = None, days: int = 14) -> Overview:
    """Roll up everything the dashboard renders in a handful of queries."""
    o = Overview()
    o.products = list(session.scalars(select(Product).order_by(Product.id)))

    o.total = _count(session, product_id)
    o.signal = _count(session, product_id, Evidence.category.in_(SIGNAL_CATEGORIES))
    o.pending = _count(session, product_id, Evidence.review_status == "pending")
    o.approved = _count(session, product_id, Evidence.review_status == "approved")
    o.failed = _count(session, product_id, Evidence.classification_failed.is_(True))

    reach_stmt = select(func.sum(Evidence.author_followers))
    if product_id:
        reach_stmt = reach_stmt.where(Evidence.product_id == product_id)
    reach_stmt = reach_stmt.where(Evidence.category.in_(SIGNAL_CATEGORIES))
    o.reach = int(session.scalar(reach_stmt) or 0)

    # ---- daily series per product -----------------------------------------
    today = datetime.now(timezone.utc).date()
    o.days = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    index = {d: i for i, d in enumerate(o.days)}
    names = {p.id: p.name for p in o.products}

    buckets: dict[str, list[int]] = {p.name: [0] * days for p in o.products}
    rows = session.execute(
        _base(product_id).with_only_columns(
            Evidence.product_id, Evidence.posted_at, Evidence.created_at
        )
    ).all()
    for pid, posted_at, created_at in rows:
        when = posted_at or created_at
        if when is None:
            continue
        d = when.date() if isinstance(when, datetime) else when
        i = index.get(d)
        if i is None:
            continue  # outside the window
        name = names.get(pid)
        if name in buckets:
            buckets[name][i] += 1
    o.series = buckets

    # ---- category and sentiment breakdowns --------------------------------
    def _group(column):
        stmt = select(column, Evidence.product_id, func.count(Evidence.id))
        if product_id:
            stmt = stmt.where(Evidence.product_id == product_id)
        out: dict = defaultdict(lambda: defaultdict(int))
        for key, pid, n in session.execute(stmt.group_by(column, Evidence.product_id)).all():
            out[key or "unclassified"][names.get(pid, "?")] = int(n)
        return {k: dict(v) for k, v in out.items()}

    o.by_category = _group(Evidence.category)
    o.by_sentiment = _group(Evidence.sentiment)

    # ---- top voices --------------------------------------------------------
    voices = _base(product_id).where(
        Evidence.category.in_(SIGNAL_CATEGORIES)
    ).order_by(Evidence.author_followers.desc()).limit(10)
    o.top_voices = list(session.scalars(voices))
    return o
