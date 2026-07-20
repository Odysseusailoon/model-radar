"""Startup smoke tests.

The existing suite covers pure logic (classifier, dedup, export) but nothing
that actually boots the ASGI app. A deploy already failed on a startup-only
fault that unit tests could not have caught, so these tests exercise the
lifespan handler and the auth gate end-to-end.

Database/credential environment is configured in conftest.py.
"""
import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:  # `with` runs the lifespan handler
        yield c


def test_app_starts_and_health_is_ok(client):
    """Railway's healthcheckPath. If this 500s or the app fails to boot, the
    container never passes healthcheck and the deploy rolls back."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_dashboard_requires_auth(client):
    assert client.get("/").status_code == 401


def test_dashboard_rejects_wrong_password(client):
    assert client.get("/", auth=("smoke-user", "wrong")).status_code == 401


def test_dashboard_accepts_correct_credentials(client):
    assert client.get("/", auth=("smoke-user", "smoke-pass")).status_code == 200


def test_debug_collect_is_not_publicly_exposed(client):
    """/debug/collect spends real API credits; it must never be anonymous."""
    assert client.post("/debug/collect").status_code == 401
