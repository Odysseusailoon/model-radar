"""user_followings() paging/mapping, and the rate-limit handling around it.

Response shapes here mirror a live /twitter/user/followings response captured
2026-07-20 — notably the snake_case user fields, which differ from the
camelCase author objects on tweets.
"""
import httpx
import pytest

from app import xclient
from app.xclient import XDataClient, _is_rate_limited, _map_user


def _user(i, followers=1000):
    return {
        "id": str(i),
        "name": f"Name {i}",
        "screen_name": f"handle{i}",
        "userName": f"handle{i}",
        "description": f"bio {i}",
        "followers_count": followers,
        "verified": False,
    }


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Tests must not actually wait out the 5s rate-limit window."""
    monkeypatch.setattr(xclient.time, "sleep", lambda s: None)


def test_map_user_reads_snake_case_fields():
    """Regression guard: using the tweet-author key `followers` here yields 0,
    which would silently drop every KOL below the follower threshold."""
    author = _map_user(_user(1, followers=54321))
    assert author.handle == "handle1"
    assert author.followers == 54321
    assert author.bio == "bio 1"


def test_user_followings_walks_pages(monkeypatch):
    pages = [
        {"followings": [_user(1), _user(2)], "has_next_page": True, "next_cursor": "c1"},
        {"followings": [_user(3)], "has_next_page": False, "next_cursor": ""},
    ]
    seen_cursors = []

    def fake_get(self, path, params):
        seen_cursors.append(params["cursor"])
        return pages[len(seen_cursors) - 1]

    monkeypatch.setattr(XDataClient, "_get", fake_get)
    got = list(XDataClient("k").user_followings("Zai_org"))

    assert [a.handle for a in got] == ["handle1", "handle2", "handle3"]
    assert seen_cursors == ["", "c1"], "second page must pass the returned cursor"


def test_user_followings_respects_max_pages(monkeypatch):
    """Cost cap: these lists can be long and every page costs a rate-limited call."""
    calls = {"n": 0}

    def fake_get(self, path, params):
        calls["n"] += 1
        return {"followings": [_user(calls["n"])], "has_next_page": True, "next_cursor": "c"}

    monkeypatch.setattr(XDataClient, "_get", fake_get)
    got = list(XDataClient("k").user_followings("Zai_org", max_pages=3))

    assert calls["n"] == 3
    assert len(got) == 3


def test_rate_limited_retry_waits_at_least_the_qps_window(monkeypatch):
    """The generic 1s/2s/4s ladder is shorter than the provider's 5s window, so
    a 429 retry would land inside it and burn the next attempt."""
    waits = []
    monkeypatch.setattr(xclient.time, "sleep", lambda s: waits.append(s))

    attempts = {"n": 0}

    def fake_httpx_get(url, **kwargs):
        attempts["n"] += 1
        req = httpx.Request("GET", url)
        if attempts["n"] == 1:
            return httpx.Response(429, request=req, json={"error": "Too Many Requests"})
        return httpx.Response(200, request=req, json={"followings": [], "has_next_page": False})

    monkeypatch.setattr(xclient.httpx, "get", fake_httpx_get)

    client = XDataClient("k", min_interval=5.5)
    client._get("/twitter/user/followings", {"userName": "x", "cursor": ""})

    assert attempts["n"] == 2, "should have retried after the 429"
    assert max(waits) >= 5.5, f"429 backoff must cover the QPS window, waited {waits}"


def test_is_rate_limited_only_matches_429():
    req = httpx.Request("GET", "https://example.com")
    too_many = httpx.HTTPStatusError(
        "429", request=req, response=httpx.Response(429, request=req)
    )
    server_error = httpx.HTTPStatusError(
        "500", request=req, response=httpx.Response(500, request=req)
    )
    assert _is_rate_limited(too_many)
    assert not _is_rate_limited(server_error)
    assert not _is_rate_limited(ValueError("bad json"))
