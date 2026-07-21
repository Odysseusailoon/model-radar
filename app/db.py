"""Database engine / session setup (SQLAlchemy 2.x)."""
from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .config import get_settings

log = logging.getLogger("gtm.db")


def _normalize_db_url(url: str) -> str:
    """Railway/Heroku hand out `postgres://...` URLs. SQLAlchemy 2.x needs a
    driver-qualified scheme. We standardise on psycopg (v3)."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


settings = get_settings()
engine = create_engine(
    _normalize_db_url(settings.database_url),
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(attempts: int = 6, base_delay: float = 1.0) -> None:
    """Create all tables if they do not exist (no migration framework, per spec).

    Retries with exponential backoff: on Railway the app container regularly
    wins the startup race against Postgres, and an unguarded failure here kills
    the container before it can serve the healthcheck. Since the restart policy
    allows only a limited number of retries, a slow database cold start could
    otherwise burn them all and fail the whole deploy.
    """
    from . import models  # noqa: F401  (register models on the metadata)

    for attempt in range(1, attempts + 1):
        try:
            models.Base.metadata.create_all(bind=engine)
            _migrate_tweet_dedup()
            return
        except OperationalError:
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning(
                "Database not ready (attempt %d/%d); retrying in %.1fs",
                attempt, attempts, delay,
            )
            time.sleep(delay)


def _migrate_tweet_dedup() -> None:
    """Idempotently move evidence dedup from global-on-tweet_id to
    (tweet_id, product_id). `create_all` only creates missing tables; it never
    alters the constraints of a table that already exists, so a database created
    before this change keeps the old global unique constraint and would still
    drop cross-product mentions. This runs the one-time swap in place.

    Postgres-only: fresh SQLite (tests) is always built from the current models,
    so there is nothing to migrate there.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE evidence DROP CONSTRAINT IF EXISTS uq_evidence_tweet_id"
        ))
        # ADD CONSTRAINT has no IF NOT EXISTS; guard on the catalog so re-runs
        # (and freshly-created tables that already have it) are no-ops.
        conn.execute(text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_evidence_tweet_product'
                ) THEN
                    ALTER TABLE evidence
                        ADD CONSTRAINT uq_evidence_tweet_product UNIQUE (tweet_id, product_id);
                END IF;
            END $$;
            """
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_evidence_tweet_id ON evidence (tweet_id)"
        ))
