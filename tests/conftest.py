"""Test environment setup.

`app.db` builds its SQLAlchemy engine at import time from `get_settings()`,
which is `lru_cache`d. pytest imports every test module during collection, so
by the time any fixture runs the engine is already bound to whatever
DATABASE_URL was set then. Configuring the environment here — conftest is
imported before any test module — is what keeps the suite from trying to reach
a real Postgres.

Postgres is not available in CI, so we point at SQLite and teach the SQLite
dialect to render JSONB as JSON. The shim is test-only; it lets the real
models and lifespan handler run unmodified.
"""
import os
import tempfile

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

_DB_PATH = os.path.join(tempfile.mkdtemp(prefix="gtm-tests-"), "test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["DASHBOARD_USER"] = "smoke-user"
os.environ["DASHBOARD_PASSWORD"] = "smoke-pass"
# No collection cycles, no seeding, no outbound API calls during tests.
os.environ["SEED_PRODUCTS_FILE"] = ""
os.environ["COLLECT_INTERVAL_MINUTES"] = "60"
os.environ["TWITTERAPI_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["FEISHU_WEBHOOK_URL"] = ""


@compiles(JSONB, "sqlite")
def _render_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: D103
    return "JSON"
