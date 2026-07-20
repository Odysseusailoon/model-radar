"""Collection orchestration (called by APScheduler every N minutes).

For each active product:
  1. Build an advanced-search query from its keywords (excluding retweets).
  2. Pull recent tweets, incrementally (stop at last_seen_tweet_id watermark).
  3. Poll each seed KOL's latest tweets.
  4. Funnel every new tweet through the shared pipeline (classify+store).
  5. Fire alerts for high-signal hits.

A global per-cycle cap (settings.max_tweets_per_cycle) bounds LLM spend.
"""
from __future__ import annotations

import logging
from collections import Counter

from .alerts import maybe_alert
from .classifier import Classifier
from .config import get_settings
from .crud import list_products
from .db import SessionLocal
from .models import Product
from .pipeline import process_tweet
from .xclient import Tweet, XDataClient

log = logging.getLogger(__name__)


def build_query(product: Product) -> str | None:
    """OR-join keywords; exclude retweets so we capture original evidence, not
    reshares. (Assumption: the spec's 'filter:retweets' means *exclude* RTs,
    since a retweet is not original social proof — noted in README.)"""
    kws = [k.strip() for k in (product.keywords or []) if k and k.strip()]
    if not kws:
        return None
    joined = " OR ".join(kws)
    return f"({joined}) -filter:retweets"


def _as_int(tweet_id: str) -> int:
    try:
        return int(tweet_id)
    except (TypeError, ValueError):
        return 0


def collect_once() -> dict:
    """Run one full collection cycle across all active products. Returns stats."""
    settings = get_settings()
    client = XDataClient(
        api_key=settings.twitterapi_key,
        base_url=settings.twitterapi_base_url,
    )
    classifier = Classifier()
    budget = settings.max_tweets_per_cycle

    totals = {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0}
    category_dist: Counter = Counter()

    session = SessionLocal()
    try:
        products = list_products(session, only_active=True)
        log.info("Collection cycle start: %d active product(s), budget=%d", len(products), budget)

        for product in products:
            if budget <= 0:
                log.warning("Per-cycle tweet budget exhausted; stopping early.")
                break

            watermark = _as_int(product.last_seen_tweet_id or "0")
            new_max = watermark
            tweets = _gather_product_tweets(client, product, settings)

            for tweet in tweets:
                if budget <= 0:
                    log.warning("Budget hit mid-product %s; remaining tweets deferred to next cycle.", product.name)
                    break
                totals["fetched"] += 1

                tid = _as_int(tweet.id)
                # Incremental: skip anything at/below the watermark from keyword search.
                # (Seed-KOL tweets share the same guard; dedup in pipeline is the backstop.)
                if watermark and tid and tid <= watermark:
                    continue

                budget -= 1
                ev = process_tweet(session, product, tweet, classifier)
                if ev is None:
                    totals["skipped_dup"] += 1
                    if tid > new_max:
                        new_max = tid
                    continue

                totals["processed"] += 1
                category_dist[ev.category or "unknown"] += 1
                if tid > new_max:
                    new_max = tid

                try:
                    if maybe_alert(session, product, ev):
                        totals["alerts"] += 1
                except Exception:
                    log.exception("Alerting failed for tweet %s (non-fatal)", tweet.id)

            # Advance the watermark so next cycle only sees genuinely new tweets.
            if new_max > watermark:
                product.last_seen_tweet_id = str(new_max)
                session.commit()

        log.info(
            "Collection cycle done: fetched=%d processed=%d dup=%d alerts=%d dist=%s",
            totals["fetched"], totals["processed"], totals["skipped_dup"],
            totals["alerts"], dict(category_dist),
        )
    finally:
        session.close()

    totals["category_dist"] = dict(category_dist)
    return totals


def _gather_product_tweets(client: XDataClient, product: Product, settings) -> list[Tweet]:
    """Keyword search + seed-KOL polling, resilient to per-source failures."""
    collected: list[Tweet] = []

    query = build_query(product)
    if query:
        try:
            collected.extend(client.search_recent(query, max_pages=settings.max_pages_per_query))
        except Exception:
            log.exception("Keyword search failed for product %s (continuing)", product.name)
    else:
        log.info("Product %s has no keywords; skipping keyword search.", product.name)

    for handle in product.seed_kols or []:
        handle = handle.lstrip("@").strip()
        if not handle:
            continue
        try:
            collected.extend(client.user_last_tweets(user_name=handle, max_pages=1))
        except Exception:
            log.exception("Seed-KOL poll failed for @%s (continuing)", handle)

    return collected
