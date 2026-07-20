"""XDataClient — the ONLY place that talks to twitterapi.io.

============================================================================
IF FIELDS DON'T LINE UP, EDIT THIS FILE AND NOTHING ELSE.
============================================================================
All endpoint paths, query-parameter names, and response field names are
mapped here in one place. They were verified against https://docs.twitterapi.io
on 2026-07-19. If the API changes, update the constants and the two mapping
functions (`_map_tweet`, `_extract_media`) below — the rest of the codebase
consumes the normalized dataclasses and never sees raw API JSON.

Verified from the docs:
  * Advanced Search : GET /twitter/tweet/advanced_search
      params: query, queryType ("Latest"|"Top"), cursor
      response envelope: { tweets: [...], has_next_page: bool, next_cursor: str }
  * User Last Tweets: GET /twitter/user/last_tweets
      params: userId | userName, cursor, includeReplies
      response envelope: { data: { tweets: [...], pin_tweet }, has_next_page,
                           next_cursor, status, msg, code }
      *** WARNING: tweets are nested under `data`, UNLIKE advanced_search which
      returns them at the top level. Verified live 2026-07-20. Reading the top
      level here yields zero tweets silently — seed-KOL polling looked healthy
      while collecting nothing. `_tweets_from` handles both shapes. ***
  * User Followings: GET /twitter/user/followings
      params: userName, cursor
      response envelope: { followings: [...], has_next_page, next_cursor, status, msg, code }
      NOTE: the user objects here use snake_case (`followers_count`,
      `screen_name`) — NOT the camelCase of tweet author objects. Verified
      against a live response 2026-07-20; `_map_user` handles the difference.
  * Auth header: X-API-Key

*** RATE LIMIT (verified live 2026-07-20): the free tier allows ONE request
    every 5 seconds. Exceeding it returns HTTP 429. `XDataClient` therefore
    enforces a client-side minimum interval between requests (`min_interval`)
    and uses a 429-aware backoff floor, because the generic 1s/2s/4s retry
    ladder is shorter than the limit window and would burn all attempts. ***
  * Tweet fields : id, text, url, createdAt, likeCount, retweetCount,
                   replyCount, quoteCount, viewCount, bookmarkCount, lang,
                   author, entities
  * Author fields: id, userName, name, description, followers, following,
                   isBlueVerified, profilePicture, location

*** UNCERTAIN — NOT in the OpenAPI docs, verify against a live response: ***
  * MEDIA: the docs do NOT document how photos/videos appear on a tweet.
    `_extract_media` therefore probes several commonly-seen shapes
    (extendedEntities.media[].media_url_https, entities.media[], media[]).
    If demo detection is missing media, dump one raw tweet (set XCLIENT_DEBUG=1)
    and adjust `_extract_media`.
  * createdAt FORMAT: assumed Twitter's "Wed Oct 10 20:19:24 +0000 2018" style
    with an ISO-8601 fallback. Adjust `_parse_created_at` if parsing warns.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Optional

import httpx

log = logging.getLogger(__name__)

# ---- Endpoint paths (verified 2026-07-19) --------------------------------
ADVANCED_SEARCH_PATH = "/twitter/tweet/advanced_search"
USER_LAST_TWEETS_PATH = "/twitter/user/last_tweets"
USER_FOLLOWINGS_PATH = "/twitter/user/followings"
AUTH_HEADER = "X-API-Key"

# ---- Response envelope keys ----------------------------------------------
KEY_TWEETS = "tweets"
KEY_FOLLOWINGS = "followings"
KEY_HAS_NEXT = "has_next_page"
KEY_NEXT_CURSOR = "next_cursor"

# Free tier: one request per 5 seconds. Leave headroom.
DEFAULT_MIN_INTERVAL = float(os.getenv("TWITTERAPI_MIN_INTERVAL", "5.5"))

_DEBUG = os.getenv("XCLIENT_DEBUG") == "1"


@dataclass
class Author:
    id: str = ""
    handle: str = ""          # userName
    name: str = ""
    followers: int = 0
    bio: str = ""             # description
    verified: bool = False


@dataclass
class Tweet:
    id: str
    text: str = ""
    url: str = ""
    lang: str = ""
    created_at: Optional[datetime] = None
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    media_urls: list[str] = field(default_factory=list)
    author: Author = field(default_factory=Author)
    raw: dict = field(default_factory=dict)


def _parse_created_at(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value)
    # Twitter classic format, e.g. "Wed Oct 10 20:19:24 +0000 2018".
    for fmt in ("%a %b %d %H:%M:%S %z %Y",):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    # ISO-8601 fallback.
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        log.warning("Could not parse createdAt=%r (update _parse_created_at)", value)
        return None


def _extract_media(tweet: dict) -> list[str]:
    """Best-effort media URL extraction. See UNCERTAIN note at top of file."""
    urls: list[str] = []

    def _pull(media_list):
        for m in media_list or []:
            if not isinstance(m, dict):
                continue
            # Photos: media_url_https / media_url. Videos: best variant url, else thumbnail.
            u = m.get("media_url_https") or m.get("media_url") or m.get("url")
            variants = (m.get("video_info") or {}).get("variants") or m.get("variants")
            if variants:
                mp4s = [v for v in variants if isinstance(v, dict) and str(v.get("content_type", "")).endswith("mp4")]
                best = max(mp4s, key=lambda v: v.get("bitrate", 0), default=None)
                if best and best.get("url"):
                    u = best["url"]
            if u:
                urls.append(u)

    ext = tweet.get("extendedEntities") or tweet.get("extended_entities") or {}
    _pull(ext.get("media"))
    if not urls:
        _pull((tweet.get("entities") or {}).get("media"))
    if not urls:
        _pull(tweet.get("media"))
    # De-dup, preserve order.
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _tweets_from(data: dict) -> list:
    """Pull the tweet list out of a response envelope.

    advanced_search returns `{tweets: [...]}` while last_tweets returns
    `{data: {tweets: [...]}}`. Accept either so a shape change on one endpoint
    cannot silently zero out collection.
    """
    top = data.get(KEY_TWEETS)
    if top:
        return top
    nested = data.get("data")
    if isinstance(nested, dict):
        return nested.get(KEY_TWEETS) or []
    return []


def _is_rate_limited(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None) == 429


def _map_user(raw: dict) -> Author:
    """Map a user object from /twitter/user/followings.

    Distinct from `_map_author`: this endpoint returns snake_case fields
    (`followers_count`, `screen_name`) rather than the tweet author object's
    camelCase (`followers`, `userName`). Verified live 2026-07-20.
    """
    return Author(
        id=str(raw.get("id", "") or ""),
        handle=raw.get("userName") or raw.get("screen_name") or "",
        name=raw.get("name", "") or "",
        followers=int(raw.get("followers_count", 0) or 0),
        bio=raw.get("description", "") or "",
        verified=bool(raw.get("verified", False)),
    )


def _map_author(raw: dict) -> Author:
    raw = raw or {}
    return Author(
        id=str(raw.get("id", "")),
        handle=raw.get("userName", "") or "",
        name=raw.get("name", "") or "",
        followers=int(raw.get("followers", 0) or 0),
        bio=raw.get("description", "") or "",
        verified=bool(raw.get("isBlueVerified", False)),
    )


def _map_tweet(raw: dict) -> Tweet:
    """Map one raw twitterapi.io tweet object to our normalized Tweet."""
    return Tweet(
        id=str(raw.get("id", "")),
        text=raw.get("text", "") or "",
        url=raw.get("url", "") or "",
        lang=raw.get("lang", "") or "",
        created_at=_parse_created_at(raw.get("createdAt")),
        like_count=int(raw.get("likeCount", 0) or 0),
        retweet_count=int(raw.get("retweetCount", 0) or 0),
        reply_count=int(raw.get("replyCount", 0) or 0),
        quote_count=int(raw.get("quoteCount", 0) or 0),
        view_count=int(raw.get("viewCount", 0) or 0),
        media_urls=_extract_media(raw),
        author=_map_author(raw.get("author")),
        raw=raw,
    )


class XDataClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twitterapi.io",
        timeout: float = 20.0,
        max_retries: int = 3,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        """Space requests out to respect the provider's QPS limit."""
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    # ---- low-level request with retry + exponential backoff --------------
    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._throttle()
                self._last_request_at = time.monotonic()
                resp = httpx.get(
                    url,
                    params=params,
                    headers={AUTH_HEADER: self.api_key},
                    timeout=self.timeout,
                )
                # Retry on 429 / 5xx; raise on other 4xx.
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                if _DEBUG and data.get(KEY_TWEETS):
                    log.info("XCLIENT_DEBUG raw tweet[0]=%s", data[KEY_TWEETS][0])
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = 2 ** (attempt - 1)
                    # A 429 means we are inside the provider's QPS window; a
                    # sub-window backoff would just burn the next attempt on
                    # another 429, so never wait less than the full interval.
                    if _is_rate_limited(exc):
                        backoff = max(backoff, self.min_interval)
                    log.warning("X API %s attempt %d/%d failed: %s; retry in %ss",
                                path, attempt, self.max_retries, exc, backoff)
                    time.sleep(backoff)
                else:
                    log.error("X API %s failed after %d attempts: %s", path, self.max_retries, exc)
        raise last_exc  # type: ignore[misc]

    # ---- Advanced search (keyword collection) ----------------------------
    def search_recent(
        self,
        query: str,
        max_pages: int = 5,
        query_type: str = "Latest",
    ) -> Iterator[Tweet]:
        """Yield tweets matching `query`, walking pages up to `max_pages`.

        Caller is responsible for building the `query` string (keywords,
        `filter:retweets` exclusion, `since_time:` etc). See collector.
        """
        cursor = ""
        for _ in range(max_pages):
            data = self._get(
                ADVANCED_SEARCH_PATH,
                {"query": query, "queryType": query_type, "cursor": cursor},
            )
            for raw in _tweets_from(data):
                yield _map_tweet(raw)
            if not data.get(KEY_HAS_NEXT):
                break
            cursor = data.get(KEY_NEXT_CURSOR) or ""
            if not cursor:
                break

    # ---- KOL discovery ---------------------------------------------------
    def user_followings(
        self,
        user_name: str,
        max_pages: int = 25,
    ) -> Iterator[Author]:
        """Yield the accounts `user_name` follows (200 per page).

        Who a product account follows is a high-signal KOL shortlist: unlike
        its followers (millions, mostly noise), the following list is small and
        hand-curated. `max_pages` is a hard cost cap — at the free tier's one
        request per 5s, each page costs ~5s of wall clock.
        """
        cursor = ""
        for _ in range(max_pages):
            data = self._get(USER_FOLLOWINGS_PATH, {"userName": user_name, "cursor": cursor})
            for raw in data.get(KEY_FOLLOWINGS, []) or []:
                yield _map_user(raw)
            if not data.get(KEY_HAS_NEXT):
                break
            cursor = data.get(KEY_NEXT_CURSOR) or ""
            if not cursor:
                break

    # ---- Seed KOL polling ------------------------------------------------
    def user_last_tweets(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        max_pages: int = 1,
        include_replies: bool = False,
    ) -> Iterator[Tweet]:
        """Yield a seed account's latest tweets. Docs recommend userId over
        userName (more stable/faster); we support either."""
        cursor = ""
        params_base = {"includeReplies": str(include_replies).lower()}
        if user_id:
            params_base["userId"] = user_id
        elif user_name:
            params_base["userName"] = user_name
        else:
            return
        for _ in range(max_pages):
            data = self._get(USER_LAST_TWEETS_PATH, {**params_base, "cursor": cursor})
            for raw in _tweets_from(data):
                yield _map_tweet(raw)
            if not data.get(KEY_HAS_NEXT):
                break
            cursor = data.get(KEY_NEXT_CURSOR) or ""
            if not cursor:
                break
