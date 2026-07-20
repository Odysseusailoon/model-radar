"""init_db() must survive a database that is not accepting connections yet.

On Railway the app container regularly boots before Postgres is ready. An
unguarded failure kills the container before it can serve the healthcheck, and
the restart policy allows only a limited number of retries.
"""
import pytest
from sqlalchemy.exc import OperationalError

from app import db


def _operational_error():
    return OperationalError("CREATE TABLE", {}, Exception("connection is bad"))


def test_init_db_retries_until_database_is_ready(monkeypatch):
    calls = {"n": 0}

    def flaky_create_all(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _operational_error()

    monkeypatch.setattr(db.engine, "dispose", lambda **k: None, raising=False)
    monkeypatch.setattr("app.models.Base.metadata.create_all", flaky_create_all)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)  # no real backoff waits

    db.init_db()

    assert calls["n"] == 3, "should have retried until the database accepted the connection"


def test_init_db_gives_up_after_exhausting_attempts(monkeypatch):
    calls = {"n": 0}

    def always_failing(**kwargs):
        calls["n"] += 1
        raise _operational_error()

    monkeypatch.setattr("app.models.Base.metadata.create_all", always_failing)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)

    with pytest.raises(OperationalError):
        db.init_db(attempts=4)

    assert calls["n"] == 4, "should stop after the configured number of attempts"


def test_init_db_does_not_swallow_programming_errors(monkeypatch):
    """A genuine schema bug must surface immediately, not be retried away."""
    def bad_schema(**kwargs):
        raise ValueError("bad column definition")

    monkeypatch.setattr("app.models.Base.metadata.create_all", bad_schema)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)

    with pytest.raises(ValueError):
        db.init_db()
