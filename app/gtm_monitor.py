"""Account GTM monitor: local SQLite, bounded collection, inspectable heuristics.

No LLM, Postgres, social writes, or outbound alerts. All X fields come from
xclient. The HTML/JSON are local research outputs, never source-control data.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from jinja2 import Environment, FileSystemLoader, select_autoescape
from .xclient import XDataClient, Tweet

CORE = ("inferact", "vllm_project", "radixark", "sgl_project")
PEERS = CORE + ("baseten", "modal", "PrimeIntellect", "NousResearch")
NAMES = dict(zip(PEERS, ("Inferact", "vLLM", "RadixArk", "SGLang", "Baseten", "Modal", "Prime Intellect", "Nous Research")))
# Multi-label discovery, not a semantic judgment or verified partnership.
PATTERNS = {
    "performance": r"benchmark|throughput|latency|tokens?/s|tok/s|faster|speedup|\d+[×x] |pareto",
    "release": r"day[ -]?0|day[ -]?zero|releas|launch|introduc|now available|support.*model|v\d+\.\d+",
    "customer / partner": r"partner|customer|collaborat|powered by|powers |in production|working with|work with",
    "education / code": r"tutorial|how to|deep dive|github|recipe|guide|blog|open.source|kernel",
    "community / event": r"summit|conference|meetup|join us|register|rsvp|community|workshop|consortium",
    "offer / conversion": r"try |get started|sign up|signup|free |credits|contact|talk to|start building|book a",
    "hiring": r"hiring|careers|join our team|open roles",
}


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS posts (
      account TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL,
      first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, payload TEXT NOT NULL,
      PRIMARY KEY(account,id));
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, since_at TEXT NOT NULL,
      accounts TEXT NOT NULL, results TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS snapshots (
      account TEXT NOT NULL, day TEXT NOT NULL, captured_at TEXT NOT NULL,
      followers INTEGER, bio TEXT, PRIMARY KEY(account,day));
    """)
    return db


def normalize(tweet: Tweet, account: str) -> dict | None:
    if not tweet.id or not tweet.created_at:
        return None
    raw = tweet.raw
    # Some timelines return the original author for a repost. Never count that
    # author's engagement as original content from the watched account.
    repost = bool(raw.get("isRetweet") or raw.get("retweeted_tweet") or tweet.text.startswith("RT @")
                  or tweet.author.handle.lower() != account.lower())
    kind = "repost" if repost else "reply" if raw.get("isReply") else "quote" if raw.get("isQuote") or raw.get("quoted_tweet") else "original"
    engagement = tweet.like_count + tweet.retweet_count + tweet.reply_count + tweet.quote_count
    # Zero/missing public views are unavailable, not a zero denominator.
    views = tweet.view_count if tweet.view_count > 0 else None
    return {
        "id": tweet.id, "account": account, "author": tweet.author.handle,
        "created_at": tweet.created_at.astimezone(timezone.utc).isoformat(),
        "url": f"https://x.com/{tweet.author.handle or account}/status/{tweet.id}",
        "text": tweet.text, "kind": kind, "likes": tweet.like_count,
        "reposts": tweet.retweet_count, "replies": tweet.reply_count, "quotes": tweet.quote_count,
        "engagements": engagement, "views": views,
        "engagement_per_view_pct": round(100 * engagement / views, 3) if views else None,
        "tags": [tag for tag, pattern in PATTERNS.items() if re.search(pattern, tweet.text, re.I)],
        "links": [u.get("expanded_url") or u.get("url") for u in (raw.get("entities") or {}).get("urls", [])],
        "mentions": [u.get("screen_name") for u in (raw.get("entities") or {}).get("user_mentions", [])],
        "has_media": bool(tweet.media_urls),
    }


def collect(db, client: XDataClient, accounts=CORE, days=30, max_pages=10, now=None, observed_at=None):
    if not 1 <= days <= 365 or not 1 <= max_pages <= 50:
        raise ValueError("days must be 1..365; max_pages must be 1..50")
    accounts = list(dict.fromkeys(accounts))
    if not accounts or any(h not in PEERS for h in accounts):
        raise ValueError("Choose accounts from the configured core or peer cohort")
    now = now or datetime.now(timezone.utc)
    observed_at = observed_at or now
    since = now - timedelta(days=days)
    results = {}
    # Hold a write transaction for the whole scan. This prevents concurrent
    # invocations from duplicating new-post notifications; reads still use WAL.
    db.execute("BEGIN IMMEDIATE")
    try:
        for account in accounts:
            result = {"pages": 0, "seen": 0, "new": 0, "invalid": 0,
                      "coverage": "page_cap", "error": None, "new_ids": []}
            seen = set()
            profile = None
            try:
                for page in client.user_tweet_pages(user_name=account, max_pages=max_pages, include_replies=True):
                    result["pages"] += 1
                    window_dates = []
                    for tweet in page.tweets:
                        if tweet.author.handle.lower() == account.lower() and profile is None:
                            profile = tweet.author
                        post = normalize(tweet, account)
                        if post is None:
                            result["invalid"] += 1
                            continue
                        # Reposted originals can be much older than their repost;
                        # do not let them prematurely end pagination.
                        if post["kind"] != "repost":
                            window_dates.append(tweet.created_at)
                        if tweet.created_at < since or tweet.created_at >= now or tweet.id in seen:
                            continue
                        seen.add(tweet.id)
                        exists = db.execute("SELECT 1 FROM posts WHERE account=? AND id=?", (account, tweet.id)).fetchone()
                        if not exists:
                            result["new"] += 1
                            result["new_ids"].append(tweet.id)
                        db.execute("""INSERT INTO posts VALUES (?,?,?,?,?,?)
                          ON CONFLICT(account,id) DO UPDATE SET last_seen=excluded.last_seen,payload=excluded.payload""",
                                   (account, tweet.id, post["created_at"], observed_at.isoformat(), observed_at.isoformat(), json.dumps(post)))
                        result["seen"] += 1
                    # Require a whole page of older owned posts (not one pinned
                    # post) before ending the chronological walk.
                    if window_dates and all(d < since for d in window_dates):
                        result["coverage"] = "window_reached"
                        break
                    if not page.has_next:
                        result["coverage"] = "source_exhausted"
                        break
                    if not page.tweets:
                        result["coverage"] = "empty_page_with_cursor"
                        break
                if result["invalid"]:
                    result["coverage"] = "invalid_records"
            except Exception as exc:
                # Partial progress persists, but is visibly unsuccessful.
                result["coverage"] = "error"
                result["error"] = type(exc).__name__
            if profile:
                db.execute("""INSERT INTO snapshots VALUES (?,?,?,?,?)
                  ON CONFLICT(account,day) DO UPDATE SET captured_at=excluded.captured_at,
                  followers=excluded.followers,bio=excluded.bio""",
                           (account, observed_at.date().isoformat(), observed_at.isoformat(), profile.followers, profile.bio))
            results[account] = result
        db.execute("INSERT INTO runs(started_at,since_at,accounts,results) VALUES (?,?,?,?)",
                   (now.isoformat(), since.isoformat(), json.dumps(accounts), json.dumps(results)))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {"as_of": now.isoformat(), "since": since.isoformat(), "results": results}


def summary(db, accounts=PEERS, days=30, now=None):
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    runs = db.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    latest = {}
    for run in runs:
        for account, result in json.loads(run["results"]).items():
            latest.setdefault(account, {**result, "as_of": run["started_at"], "since": run["since_at"]})
    report = {"as_of": now.isoformat(), "since": since.isoformat(), "days": days,
              "method": "Observed posts; originals and quotes only in performance metrics. Replies and reposts separate. E = likes + reposts + replies + quotes. Views are public, non-unique counts. Heuristic labels require review. No revenue attribution.",
              "accounts": [], "posts": []}
    for account in accounts:
        rows = db.execute("SELECT payload,last_seen FROM posts WHERE account=? AND created_at>=? AND created_at<? ORDER BY created_at DESC",
                          (account, since.isoformat(), now.isoformat())).fetchall()
        posts = [{**json.loads(r["payload"]), "observed_at": r["last_seen"]} for r in rows]
        owned = [p for p in posts if p["kind"] in ("original", "quote")]
        kinds = Counter(p["kind"] for p in posts)
        tags = Counter(t for p in owned for t in p["tags"])
        rates = [p["engagement_per_view_pct"] for p in owned if p["engagement_per_view_pct"] is not None]
        profile = db.execute("SELECT * FROM snapshots WHERE account=? ORDER BY day DESC LIMIT 1", (account,)).fetchone()
        prior = db.execute("SELECT * FROM snapshots WHERE account=? AND day<? ORDER BY day DESC LIMIT 1", (account, now.date().isoformat())).fetchone()
        coverage = latest.get(account, {"coverage": "not_collected"})
        if coverage.get("since") and coverage["since"] > since.isoformat():
            coverage = {**coverage, "coverage": "window_not_fully_scanned"}
        coverage = {**coverage, "stale": bool(coverage.get("as_of") and
                    now - datetime.fromisoformat(coverage["as_of"]) > timedelta(hours=36))}
        report["accounts"].append({
            "handle": account, "name": NAMES[account], "core": account in CORE,
            "followers": profile["followers"] if profile else None,
            "profile_observed_at": profile["captured_at"] if profile else None,
            "follower_delta": profile["followers"] - prior["followers"] if profile and prior and profile["day"] != prior["day"] else None,
            "follower_delta_since": prior["captured_at"] if prior else None,
            "bio": profile["bio"] if profile else "", "total": len(posts),
            "earliest_observed_post": min((p["created_at"] for p in posts), default=None),
            "originals": len(owned), "replies": kinds["reply"], "reposts": kinds["repost"],
            "observed_posts_per_week": round(len(owned) * 7 / days, 2),
            "median_engagements": median([p["engagements"] for p in owned]) if owned else None,
            "median_engagement_per_view_pct": median(rates) if rates else None,
            "posts_with_views": len(rates), "tags": dict(tags), "coverage": coverage,
            "top_posts": sorted(owned, key=lambda p: p["engagements"], reverse=True)[:5],
        })
        report["posts"].extend(posts)
    return report


def render(report: dict) -> str:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))
    return env.get_template("gtm_monitor.html").render(report=report)


def export(db, directory, accounts=PEERS, days=30, now=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    report = summary(db, accounts, days, now)
    # Replace finished files atomically; an interrupted export keeps the old one.
    for name, content in (("monitor.json", json.dumps(report, indent=2)), ("monitor.html", render(report))):
        target = directory / name
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content)
        tmp.replace(target)
    return report
