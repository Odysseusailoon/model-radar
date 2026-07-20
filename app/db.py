"""Database engine / session setup (SQLAlchemy 2.x)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings


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


def init_db() -> None:
    """Create all tables if they do not exist (no migration framework, per spec)."""
    from . import models  # noqa: F401  (register models on the metadata)

    models.Base.metadata.create_all(bind=engine)
