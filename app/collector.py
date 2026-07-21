"""Collection orchestration (called by APScheduler every N minutes).

Two phases per cycle:
  1. Keyword phase — for each active product, advanced-search its keywords
     (excluding retweets), incrementally via the snowflake watermark.
  2. KOL phase — the seed KOLs of ALL products form ONE global pool, each polled
     once per cycle (rotating window). Every KOL tweet is attributed to whichever
     product(s) its text mentions, so a single shared KOL list serves every model
     and a comparison tweet lands under each model it names. Off-topic KOL tweets
     are skipped with no LLM call.

Every new tweet is funneled through the shared pipeline (classify + store) and
high-signal hits fire alerts. A global per-cycle cap (max_tweets_per_cycle)
bounds LLM spend; a rate-budget-aware rotation keeps any one product/KOL from
being starved on the free tier (1 req/5s).
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


def build_query(product: Product, lang: str = "") -> str | None:
    """OR-join keywords; exclude retweets so we capture original evidence, not
    reshares. (Assumption: the spec's 'filter:retweets' means *exclude* RTs,
    since a retweet is not original social proof — noted in README.) When `lang`
    is set, add the `lang:<code>` operator so only that language is returned."""
    kws = [k.strip() for k in (product.keywords or []) if k and k.strip()]
    if not kws:
        return None
    joined = " OR ".join(kws)
    q = f"({joined}) -filter:retweets"
    if lang:
        q += f" lang:{lang}"
    return q


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
    """Run one full collection cycle. Two phases:
      1. Keyword search — per product, incremental via the snowflake watermark.
      2. KOL pool — the seed KOLs of ALL products form one global pool, polled
         once each (rotating window). Each KOL tweet is attributed to whichever
         product(s) its text mentions, so a KOL's take on GLM lands under GLM even
         though the KOL is listed under MiniMax. Off-topic KOL tweets are skipped
         with no LLM call.
    Returns stats, including per-source failures so they are visible, not dropped.
    """
    global _rotation
    settings = get_settings()
    client = XDataClient(
        api_key=settings.twitterapi_key,
        base_url=settings.twitterapi_base_url,
    )
    classifier = Classifier()
    budget = settings.max_tweets_per_cycle

    totals = {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0, "kol_attributed": 0}
    category_dist: Counter = Counter()
    errors: list[dict] = []

    session = SessionLocal()
    try:
        products = list_products(session, only_active=True)
        # Fair rotation: start each cycle at a different product so the same one
        # isn't always last (and thus first to starve on the rate limit).
        if products:
            off = _rotation % len(products)
            products = products[off:] + products[:off]
        _rotation += 1
        log.info("Collection cycle start: %d product(s), budget=%d, order=%s",
                 len(products), budget, [p.name for p in products])

        budget = _keyword_phase(session, client, classifier, products, budget,
                                totals, category_dist, errors, settings)
        budget = _kol_phase(session, client, classifier, products, budget,
                            totals, category_dist, errors, settings)

        if errors:
            log.warning("Collection cycle had %d source failure(s): %s", len(errors), errors)
        log.info(
            "Collection cycle done: fetched=%d processed=%d dup=%d alerts=%d "
            "kol_attributed=%d failed=%d dist=%s",
            totals["fetched"], totals["processed"], totals["skipped_dup"],
            totals["alerts"], totals["kol_attributed"], len(errors), dict(category_dist),
        )
    finally:
        session.close()

    totals["category_dist"] = dict(category_dist)
    totals["sources_failed"] = len(errors)
    totals["errors"] = errors  # surfaced so failures are visible, not silent
    return totals


def _handle_tweet(session, product, tweet, classifier, totals, category_dist) -> bool:
    """Classify + store one tweet under one product; count + alert. Returns True
    if it was newly stored (False on dedup)."""
    ev = process_tweet(session, product, tweet, classifier)
    if ev is None:
        totals["skipped_dup"] += 1
        return False
    totals["processed"] += 1
    category_dist[ev.category or "unknown"] += 1
    try:
        if maybe_alert(session, product, ev):
            totals["alerts"] += 1
    except Exception:
        log.exception("Alerting failed for tweet %s (non-fatal)", tweet.id)
    return True


def _keyword_phase(session, client, classifier, products, budget,
                   totals, category_dist, errors, settings) -> int:
    """Per-product keyword search, incremental via the snowflake watermark."""
    for product in products:
        if budget <= 0:
            break
        query = build_query(product, lang=settings.collect_lang)
        if not query:
            log.info("Product %s has no keywords; skipping keyword search.", product.name)
            continue
        try:
            tweets = list(client.search_recent(query, max_pages=settings.max_pages_per_query))
        except Exception as exc:
            log.exception("Keyword search failed for product %s", product.name)
            errors.append({"product": product.name, "source": "keyword_search", "error": str(exc)})
            continue

        watermark = _as_int(product.last_seen_tweet_id or "0")
        new_max = watermark
        for tweet in tweets:
            if budget <= 0:
                break
            totals["fetched"] += 1
            tid = _as_int(tweet.id)
            if watermark and tid and tid <= watermark:  # already seen
                continue
            budget -= 1
            _handle_tweet(session, product, tweet, classifier, totals, category_dist)
            if tid > new_max:
                new_max = tid
        if new_max > watermark:
            product.last_seen_tweet_id = str(new_max)
            session.commit()
    return budget


def _tweet_matches_product(tweet: Tweet, product: Product) -> bool:
    """Does the tweet text mention any of the product's keywords? (Same terms
    used to build the search query, so attribution is consistent with search.)"""
    text = (tweet.text or "").lower()
    for kw in (product.keywords or []):
        term = kw.strip().strip('"').strip("'").lower()
        if term and term in text:
            return True
    return False


def _kol_phase(session, client, classifier, products, budget,
               totals, category_dist, errors, settings) -> int:
    """Global KOL pool: the union of every product's seed_kols, polled once each
    (rotating window). Each KOL tweet is attributed to the product(s) it mentions
    — so one shared list serves all products, and a comparison tweet lands under
    each model it names. Off-topic KOL tweets cost nothing (no LLM call)."""
    pool: list[str] = []
    seen: set[str] = set()
    for p in products:
        for h in (p.seed_kols or []):
            hh = (h or "").lstrip("@").strip()
            if hh and hh.lower() not in seen:
                seen.add(hh.lower())
                pool.append(hh)
    if not pool:
        return budget

    window = _kol_window(pool, settings.max_seed_kols_per_cycle)
    log.info("KOL pool: %d unique, polling %d this cycle", len(pool), len(window))
    for handle in window:
        if budget <= 0:
            break
        try:
            tweets = list(client.user_last_tweets(user_name=handle, max_pages=1))
        except Exception as exc:
            log.exception("Seed-KOL poll failed for @%s", handle)
            errors.append({"product": "(kol-pool)", "source": f"kol:@{handle}", "error": str(exc)})
            continue
        for tweet in tweets:
            if budget <= 0:
                break
            # Language gate: only the configured language (default English).
            if settings.collect_lang and tweet.lang and tweet.lang != settings.collect_lang:
                continue
            matched = [p for p in products if _tweet_matches_product(tweet, p)]
            if not matched:
                continue  # off-topic — no LLM call, no storage
            totals["fetched"] += 1
            for product in matched:  # comparison tweet -> attach to each named model
                if budget <= 0:
                    break
                budget -= 1
                if _handle_tweet(session, product, tweet, classifier, totals, category_dist):
                    totals["kol_attributed"] += 1
    return budget


def _kol_window(kols: list[str], cap: int) -> list[str]:
    """A rotating slice of at most `cap` KOLs. Successive cycles advance the
    window so every KOL is covered over time without polling all at once (which
    would starve the rate budget on the free tier)."""
    kols = [k.lstrip("@").strip() for k in (kols or []) if k and k.strip()]
    if cap <= 0 or len(kols) <= cap:
        return kols
    start = _rotation % len(kols)
    return (kols + kols)[start:start + cap]
