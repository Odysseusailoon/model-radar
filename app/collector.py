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
import threading
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

# One collection at a time. The APScheduler job and a manual /debug/collect both
# call collect_once; on the free tier (1 req/5s) two concurrent cycles double the
# request rate and trip 429s, which then silently starve whole products. This
# lock makes a second trigger a no-op instead of a rate-limit pile-up.
_collect_lock = threading.Lock()

# Rotates the seed-KOL window and the product start position across cycles so no
# single product (or KOL) is permanently starved when the rate budget runs out.
_rotation = 0


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
    """Run one full collection cycle. Serialized: a second concurrent trigger
    returns immediately rather than contending for the API rate budget."""
    if not _collect_lock.acquire(blocking=False):
        log.warning("collect_once already running; this trigger is a no-op")
        return {"skipped": "already_running"}
    try:
        return _collect_once_locked()
    finally:
        _collect_lock.release()


def _collect_once_locked() -> dict:
    """Run one full collection cycle across all active products. Returns stats,
    including any per-source failures so they are visible, not silently dropped."""
    global _rotation
    settings = get_settings()
    client = XDataClient(
        api_key=settings.twitterapi_key,
        base_url=settings.twitterapi_base_url,
    )
    classifier = Classifier()
    budget = settings.max_tweets_per_cycle

    totals = {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0}
    category_dist: Counter = Counter()
    errors: list[dict] = []

    session = SessionLocal()
    try:
        products = list_products(session, only_active=True)
        # Fair rotation: start the cycle at a different product each time so the
        # same product isn't always last (and thus first to starve on the rate
        # limit). Advances by one product per cycle.
        if products:
            off = _rotation % len(products)
            products = products[off:] + products[:off]
        _rotation += 1
        log.info("Collection cycle start: %d active product(s), budget=%d, order=%s",
                 len(products), budget, [p.name for p in products])

        for product in products:
            if budget <= 0:
                log.warning("Per-cycle tweet budget exhausted; stopping early.")
                break

            watermark = _as_int(product.last_seen_tweet_id or "0")
            new_max = watermark
            tweets = _gather_product_tweets(client, product, settings, errors)

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

        if errors:
            log.warning("Collection cycle had %d source failure(s): %s",
                        len(errors), errors)
        log.info(
            "Collection cycle done: fetched=%d processed=%d dup=%d alerts=%d failed=%d dist=%s",
            totals["fetched"], totals["processed"], totals["skipped_dup"],
            totals["alerts"], len(errors), dict(category_dist),
        )
    finally:
        session.close()

    totals["category_dist"] = dict(category_dist)
    totals["sources_failed"] = len(errors)
    totals["errors"] = errors  # surfaced so failures are visible, not silent
    return totals


def _kol_window(kols: list[str], cap: int) -> list[str]:
    """A rotating slice of at most `cap` seed KOLs. Successive cycles advance the
    window so every KOL is covered over time without polling all of them at once
    (which would starve the rate budget on the free tier)."""
    kols = [k.lstrip("@").strip() for k in (kols or []) if k and k.strip()]
    if cap <= 0 or len(kols) <= cap:
        return kols
    start = _rotation % len(kols)
    return (kols + kols)[start:start + cap]


def _gather_product_tweets(client: XDataClient, product: Product, settings,
                           errors: list[dict]) -> list[Tweet]:
    """Keyword search + seed-KOL polling. Per-source failures are recorded in
    `errors` (and logged) instead of being silently swallowed, so a rate-limited
    search shows up as a failure rather than looking like 'no data'."""
    collected: list[Tweet] = []

    query = build_query(product)
    if query:
        try:
            collected.extend(client.search_recent(query, max_pages=settings.max_pages_per_query))
        except Exception as exc:
            log.exception("Keyword search failed for product %s", product.name)
            errors.append({"product": product.name, "source": "keyword_search", "error": str(exc)})
    else:
        log.info("Product %s has no keywords; skipping keyword search.", product.name)

    for handle in _kol_window(product.seed_kols, settings.max_seed_kols_per_cycle):
        if not handle:
            continue
        try:
            collected.extend(client.user_last_tweets(user_name=handle, max_pages=1))
        except Exception as exc:
            log.exception("Seed-KOL poll failed for @%s", handle)
            errors.append({"product": product.name, "source": f"kol:@{handle}", "error": str(exc)})

    return collected
