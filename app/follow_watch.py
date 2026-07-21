"""Daily lab-watch job.

Once a day, for every active product, for each of its OFFICIAL accounts (the
OSS labs — MiniMax_AI, Kimi_Moonshot, Zai_org, …):

  1. New posts   — poll the lab's own latest tweets through the shared pipeline.
                   Partnership / integration announcements the lab makes about
                   itself now classify as `partnership` and fire the Lark card.
                   (The 10-min collector polls seed_kols + keyword search but not
                   the official accounts themselves, so this closes that gap.)
  2. New follows — snapshot the lab's following list and diff it against
                   yesterday's. A lab starting to follow a company/person is an
                   early partnership / hiring / interest signal → Lark card.

Detection (snapshot) and alerting are separate so a failed Feishu send simply
retries next run, and the day-1 baseline never alerts (see FollowEdge.alerted).
"""
from __future__ import annotations

import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .alerts import alert_new_follow, maybe_alert
from .classifier import Classifier
from .config import get_settings
from .crud import list_products
from .db import SessionLocal
from .models import FollowEdge, Product
from .pipeline import process_tweet
from .xclient import XDataClient

log = logging.getLogger(__name__)


def _collect_official_posts(session: Session, client: XDataClient, product: Product,
                            classifier: Classifier, stats: Counter) -> None:
    for handle in product.official_accounts or []:
        handle = handle.lstrip("@").strip()
        if not handle:
            continue
        try:
            tweets = list(client.user_last_tweets(user_name=handle, max_pages=1))
        except Exception:
            log.exception("Official-account post poll failed for @%s (continuing)", handle)
            continue
        for tweet in tweets:
            try:
                ev = process_tweet(session, product, tweet, classifier)
            except Exception:
                log.exception("Pipeline failed for official tweet %s (continuing)", tweet.id)
                continue
            if ev is None:
                continue
            stats["new_posts"] += 1
            try:
                if maybe_alert(session, product, ev):
                    stats["post_alerts"] += 1
            except Exception:
                log.exception("Alerting failed for official tweet %s (non-fatal)", tweet.id)


def _snapshot_follows(session: Session, client: XDataClient, product: Product,
                      watcher: str, settings, stats: Counter) -> bool:
    """Fetch the watcher's current followings and insert any not seen before.
    Returns True if this was the baseline (first-ever) snapshot for the watcher,
    in which case new edges are stored pre-marked `alerted` (no alerts fire)."""
    watcher = watcher.lstrip("@").strip()
    stored = {
        h.lower()
        for h in session.scalars(
            select(FollowEdge.target_handle).where(FollowEdge.watcher_handle == watcher)
        )
    }
    is_baseline = len(stored) == 0

    try:
        current = list(client.user_followings(watcher, max_pages=settings.follow_watch_max_pages))
    except Exception:
        log.exception("Followings fetch failed for @%s (continuing)", watcher)
        return is_baseline

    added = 0
    for author in current:
        th = (author.handle or "").strip()
        if not th or th.lower() in stored:
            continue
        stored.add(th.lower())  # guard against dupes within the same fetch
        session.add(FollowEdge(
            watcher_handle=watcher,
            product_id=product.id if product is not None else None,
            target_handle=th,
            target_name=author.name,
            target_followers=author.followers,
            target_bio=author.bio,
            alerted=is_baseline,  # baseline: never alert on the pre-existing set
        ))
        added += 1
    session.commit()
    if is_baseline:
        stats["baselined"] += 1
        log.info("Baseline snapshot for @%s: %d follows stored (no alerts)", watcher, added)
    else:
        stats["new_follows"] += added
        if added:
            log.info("@%s has %d new follow(s)", watcher, added)
    return is_baseline


def _alert_pending_follows(session: Session, watcher: str, product: Product,
                           settings, stats: Counter) -> None:
    """Alert edges not yet alerted and above the follower-noise floor. Runs after
    the snapshot so a Feishu failure leaves alerted=False and retries next run."""
    watcher = watcher.lstrip("@").strip()
    pending = session.scalars(
        select(FollowEdge)
        .where(FollowEdge.watcher_handle == watcher)
        .where(FollowEdge.alerted.is_(False))
        .where(FollowEdge.target_followers >= settings.follow_watch_min_target_followers)
        .order_by(FollowEdge.target_followers.desc())
    ).all()
    for edge in pending:
        try:
            if alert_new_follow(session, watcher, edge, product):
                edge.alerted = True
                session.commit()
                stats["follow_alerts"] += 1
        except Exception:
            log.exception("New-follow alert failed for @%s -> @%s (non-fatal)",
                          watcher, edge.target_handle)


def run_daily_watch() -> dict:
    """One daily pass across all active products' official accounts. Returns stats."""
    settings = get_settings()
    if not settings.follow_watch_enabled:
        return {"skipped": "disabled"}

    client = XDataClient(api_key=settings.twitterapi_key, base_url=settings.twitterapi_base_url)
    classifier = Classifier()
    stats: Counter = Counter()

    session = SessionLocal()
    try:
        products = list_products(session, only_active=True)
        watchers = sum(len(p.official_accounts or []) for p in products)
        log.info("Daily lab-watch start: %d product(s), %d official account(s)",
                 len(products), watchers)

        for product in products:
            _collect_official_posts(session, client, product, classifier, stats)
            for watcher in product.official_accounts or []:
                stats["accounts"] += 1
                baseline = _snapshot_follows(session, client, product, watcher, settings, stats)
                if not baseline:
                    _alert_pending_follows(session, watcher, product, settings, stats)

        log.info("Daily lab-watch done: %s", dict(stats))
    finally:
        session.close()

    return dict(stats)
