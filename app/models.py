"""SQLAlchemy ORM models.

Three tables per spec:
  - products     : per-product configuration (multi-product reuse lives here)
  - evidence     : one row per collected tweet + LLM classification + review state
  - alerts_sent  : dedup ledger so we never push the same alert twice
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # List[str] of search keywords (Chinese + English supported).
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    # List[str] of official account handles (used to flag promo / self-posts).
    official_accounts: Mapped[list] = mapped_column(JSONB, default=list)
    # List[str] of seed KOL handles to poll directly each cycle.
    seed_kols: Mapped[list] = mapped_column(JSONB, default=list)
    launch_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Incremental-collection watermark: the max tweet_id we have already seen for
    # this product's keyword search. twitterapi.io tweet ids are snowflake ids
    # (monotonic with time), stored as strings to avoid precision loss.
    last_seen_tweet_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="product")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    tweet_id: Mapped[str] = mapped_column(String(40))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    # ---- Author snapshot (taken at collection time) ----
    author_handle: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    author_followers: Mapped[int] = mapped_column(BigInteger, default=0)
    author_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- Tweet content ----
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lang: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    tweet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # List[str] of media URLs (photos/video thumbnails). May be empty.
    media_urls: Mapped[list] = mapped_column(JSONB, default=list)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- Engagement snapshot at collection time ----
    like_count: Mapped[int] = mapped_column(BigInteger, default=0)
    retweet_count: Mapped[int] = mapped_column(BigInteger, default=0)
    reply_count: Mapped[int] = mapped_column(BigInteger, default=0)
    quote_count: Mapped[int] = mapped_column(BigInteger, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0)

    # ---- LLM classification (full JSON blob from the classifier) ----
    classification: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Denormalised copies of hot fields for cheap filtering/indexing.
    category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0)
    classification_failed: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- Human review ----
    # pending | approved | rejected
    review_status: Mapped[str] = mapped_column(String(20), default="pending")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="evidence")

    __table_args__ = (
        # tweet_id is globally unique across X, so a global unique index is the
        # simplest correct dedup guard (a tweet only ever matches one product's
        # ingestion path first; duplicates across products are rare and harmless
        # to drop). See collector.dedup for the application-level check.
        UniqueConstraint("tweet_id", name="uq_evidence_tweet_id"),
        Index("ix_evidence_product_created", "product_id", "created_at"),
        Index("ix_evidence_category", "category"),
        Index("ix_evidence_review_status", "review_status"),
    )


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id: Mapped[int] = mapped_column(primary_key=True)
    tweet_id: Mapped[str] = mapped_column(String(40))
    alert_type: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tweet_id", "alert_type", name="uq_alert_tweet_type"),
    )
