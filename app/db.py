"""Database engine / session setup (SQLAlchemy 2.x)."""
from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine
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
