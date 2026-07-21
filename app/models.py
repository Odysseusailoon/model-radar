"""SQLAlchemy ORM models.

  - products     : per-product configuration (multi-product reuse lives here)
  - evidence     : one row per collected tweet + LLM classification + review state
  - alerts_sent  : dedup ledger so we never push the same alert twice
  - follow_edges : daily snapshot of who each watched lab account follows, so the
                   lab-watch job can diff day-over-day and surface *new* follows
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
        # Dedup is per (tweet_id, product_id), NOT global on tweet_id. A single
        # tweet that names several tracked products ("M2 beats GLM-5 and Kimi K3")
        # is the highest-value competitive-intel signal we have; a global unique
        # on tweet_id would attribute it to whichever product's search hit it
        # first and silently drop it from the others. We want that comparison to
        # appear under every product it mentions. See pipeline.already_stored.
        UniqueConstraint("tweet_id", "product_id", name="uq_evidence_tweet_product"),
        Index("ix_evidence_tweet_id", "tweet_id"),
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


class FollowEdge(Base):
    """A single "watcher follows target" edge, snapshotted by the daily
    lab-watch job. We store the whole current following set per watcher so a
    day-over-day diff reveals *new* follows — a lab starting to follow a company
    or person is an early partnership / hiring / interest signal.

    `alerted` guards the day-1 baseline: the first snapshot of a watcher stores
    every edge with alerted=True (no alerts — we don't want to fire on the
    hundreds of accounts it already follows). Genuinely new edges thereafter are
    inserted with alerted=False and picked up by the alerter.
    """
    __tablename__ = "follow_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    watcher_handle: Mapped[str] = mapped_column(String(120))
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    target_handle: Mapped[str] = mapped_column(String(120))
    target_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    target_followers: Mapped[int] = mapped_column(BigInteger, default=0)
    target_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("watcher_handle", "target_handle", name="uq_follow_watcher_target"),
        Index("ix_follow_watcher", "watcher_handle"),
    )
