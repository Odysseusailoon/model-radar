"""Shared ingestion pipeline: dedup -> classify -> store -> alert.

Both the APScheduler polling collector AND the reserved /webhook/tweets endpoint
funnel individual tweets through `process_tweet` so behaviour is identical.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Evidence, Product
from .xclient import Tweet

log = logging.getLogger(__name__)


def already_stored(session: Session, tweet_id: str) -> bool:
    """Dedup guard: has this tweet_id already been ingested?"""
    return session.scalar(select(Evidence.id).where(Evidence.tweet_id == tweet_id)) is not None


def process_tweet(session: Session, product: Product, tweet: Tweet, classifier) -> Evidence | None:
    """Classify + persist one tweet. Returns the stored Evidence, or None if it
    was a duplicate. Never raises for a single tweet's classification failure —
    those are stored with classification_failed=True so no data is lost."""
    if already_stored(session, tweet.id):
        return None

    result = classifier.classify(tweet, product)

    ev = Evidence(
        tweet_id=tweet.id,
        product_id=product.id,
        author_handle=tweet.author.handle,
        author_name=tweet.author.name,
        author_followers=tweet.author.followers,
        author_bio=tweet.author.bio,
        author_verified=tweet.author.verified,
        text=tweet.text,
        lang=tweet.lang,
        tweet_url=tweet.url,
        media_urls=tweet.media_urls,
        posted_at=tweet.created_at,
        like_count=tweet.like_count,
        retweet_count=tweet.retweet_count,
        reply_count=tweet.reply_count,
        quote_count=tweet.quote_count,
        view_count=tweet.view_count,
        classification=result.data,
        category=result.data.get("category"),
        sentiment=result.data.get("sentiment"),
        confidence=float(result.data.get("confidence", 0.0) or 0.0),
        classification_failed=result.failed,
        review_status="pending",
    )
    session.add(ev)
    try:
        session.commit()
    except Exception as exc:  # unique-constraint race between concurrent ingests
        session.rollback()
        log.warning("Insert for tweet %s failed (likely dup race): %s", tweet.id, exc)
        return None
    session.refresh(ev)
    return ev
