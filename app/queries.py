"""Evidence filtering — shared by the dashboard feed and the CSV export so both
always honour the exact same filter semantics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import Evidence


@dataclass
class EvidenceFilter:
    product_id: Optional[int] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    review_status: Optional[str] = None
    min_followers: Optional[int] = None
    limit: int = 200

    @classmethod
    def from_query(cls, params) -> "EvidenceFilter":
        def _int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def _clean(v):
            v = (v or "").strip()
            return v or None

        return cls(
            product_id=_int(params.get("product_id")),
            category=_clean(params.get("category")),
            sentiment=_clean(params.get("sentiment")),
            review_status=_clean(params.get("review_status")),
            min_followers=_int(params.get("min_followers")),
            limit=_int(params.get("limit")) or 200,
        )


def query_evidence(session: Session, f: EvidenceFilter) -> list[Evidence]:
    stmt = select(Evidence).options(joinedload(Evidence.product)).order_by(Evidence.created_at.desc())
    if f.product_id:
        stmt = stmt.where(Evidence.product_id == f.product_id)
    if f.category:
        stmt = stmt.where(Evidence.category == f.category)
    if f.sentiment:
        stmt = stmt.where(Evidence.sentiment == f.sentiment)
    if f.review_status:
        stmt = stmt.where(Evidence.review_status == f.review_status)
    if f.min_followers:
        stmt = stmt.where(Evidence.author_followers >= f.min_followers)
    stmt = stmt.limit(min(f.limit, 2000))
    return list(session.scalars(stmt))
