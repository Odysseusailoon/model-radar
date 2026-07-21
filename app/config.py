"""Central configuration loaded from environment variables.

Every product-specific value (keywords, official accounts, seed KOLs, launch
date) lives in the database `products` table, NOT here. This file holds only
infrastructure / secret configuration that is the same across products.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- X / twitterapi.io ----
    twitterapi_key: str = ""
    # Base URL for twitterapi.io. Verified against https://docs.twitterapi.io
    # (Advanced Search: GET /twitter/tweet/advanced_search).
    twitterapi_base_url: str = "https://api.twitterapi.io"

    # ---- LLM (Anthropic SDK, via aihubmix Anthropic-compatible gateway) ----
    # aihubmix exposes an Anthropic-compatible endpoint, so we point the
    # Anthropic SDK's base_url at it and pass the aihubmix key as the API key.
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://aihubmix.com"
    classifier_model: str = "claude-haiku-4-5-20251001"

    # ---- Database ----
    # Railway injects DATABASE_URL automatically at deploy time.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/gtm"

    # ---- Dashboard ----
    dashboard_password: str = "changeme"
    dashboard_user: str = "marketing"

    # ---- Feishu alerting ----
    feishu_webhook_url: str = ""

    # ---- Inbound webhook (reserved) ----
    webhook_secret: str = ""

    # ---- Collector behaviour / cost guardrails ----
    collect_interval_minutes: int = 10
    # Hard cap on tweets processed (classified) per collection cycle. Prevents a
    # mis-configured keyword from triggering a runaway LLM bill.
    max_tweets_per_cycle: int = 300
    # Max pages to pull per keyword query per cycle (secondary guardrail).
    max_pages_per_query: int = 5
    # Cap on seed KOLs polled per product per cycle. On the free tier (1 req/5s)
    # polling dozens of KOLs starves later products of the rate budget, so we poll
    # a rotating window of this size and cover the rest over subsequent cycles.
    max_seed_kols_per_cycle: int = 15

    # ---- Digest quality floor (Issue: junk small accounts on the deliverable) ----
    # The weekly digest is the GTM-facing artifact, so it only surfaces credible
    # evidence. All rows still live in the DB / feed; this gates the highlights.
    # expert_review needs a real audience OR the classifier's credibility signals;
    # customer_case needs a lower floor + confidence. partnership / eval / demo are
    # gated on their own merits (event / benchmark / has-media), not follower count.
    digest_min_followers_expert: int = 10_000
    digest_min_followers_case: int = 2_000
    digest_min_confidence: float = 0.6

    # ---- Alert thresholds ----
    alert_min_followers: int = 10_000
    alert_mega_followers: int = 100_000
    alert_min_confidence: float = 0.75

    # ---- Daily lab-watch job (new posts from official accounts + new follows) ----
    follow_watch_enabled: bool = True
    # UTC hour to run the daily job (0-23). One run per day is plenty: following
    # lists change slowly and this is the expensive call (one request / 5s).
    follow_watch_hour_utc: int = 1
    # Cost cap: max pages of followings to pull per watched account per run
    # (200 handles/page). Bounds a lab that follows thousands.
    follow_watch_max_pages: int = 20
    # Skip firing new-follow alerts for accounts below this size, to cut noise
    # (a lab following a 200-follower throwaway is rarely a partnership signal).
    follow_watch_min_target_followers: int = 1_000

    # ---- Seeding ----
    # If set, on startup seed the products table from this JSON file when the
    # table is empty. Handy for local/dev bootstrapping.
    seed_products_file: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
