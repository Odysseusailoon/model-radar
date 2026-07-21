"""Daily lab-watch: following snapshot/diff, baseline suppression, alert gating.
Uses a fake X client (no network) against the SQLite test DB."""
from collections import Counter

import pytest

from app.xclient import Author


class FakeClient:
    """Minimal stand-in for XDataClient for the follow-watch code paths."""
    def __init__(self, follows: dict):
        self._follows = follows

    def user_followings(self, watcher, max_pages=20):
        for a in self._follows.get(watcher, []):
            yield a

    def user_last_tweets(self, user_name=None, user_id=None, max_pages=1, include_replies=False):
        return iter([])


@pytest.fixture(scope="module", autouse=True)
def _tables():
    from app.db import init_db
    init_db()  # ensure follow_edges exists even if no app boot ran first


def _author(handle, followers, name=""):
    return Author(handle=handle, name=name or handle, followers=followers, bio=f"bio of {handle}")


def _new_product(name, watcher):
    """Fresh product with a unique name so each test is isolated."""
    from app.db import SessionLocal
    from app.models import Product
    s = SessionLocal()
    p = Product(name=name, keywords=[], official_accounts=[watcher], seed_kols=[])
    s.add(p)
    s.commit()
    return s, p


def test_baseline_snapshot_stores_all_without_alerting():
    from app.config import get_settings
    from app.follow_watch import _snapshot_follows
    from app.models import FollowEdge

    s, p = _new_product("LW-Alpha", "LabA")
    client = FakeClient({"LabA": [_author("alice", 5000), _author("bob", 2000)]})
    stats = Counter()

    baseline = _snapshot_follows(s, client, p, "LabA", get_settings(), stats)
    assert baseline is True
    assert stats["baselined"] == 1
    assert stats["new_follows"] == 0
    edges = list(s.query(FollowEdge).filter_by(watcher_handle="LabA"))
    assert len(edges) == 2
    assert all(e.alerted for e in edges)  # baseline edges must be pre-marked, never fire
    s.close()


def test_second_run_detects_only_new_follow():
    from app.config import get_settings
    from app.follow_watch import _snapshot_follows
    from app.models import FollowEdge

    s, p = _new_product("LW-Beta", "LabB")
    st = get_settings()

    _snapshot_follows(s, FakeClient({"LabB": [_author("alice", 5000)]}), p, "LabB", st, Counter())
    # next day: alice + a NEW follow carol
    stats = Counter()
    baseline = _snapshot_follows(
        s, FakeClient({"LabB": [_author("alice", 5000), _author("carol", 50000)]}),
        p, "LabB", st, stats,
    )
    assert baseline is False
    assert stats["new_follows"] == 1
    carol = s.query(FollowEdge).filter_by(watcher_handle="LabB", target_handle="carol").one()
    assert carol.alerted is False  # genuinely new → pending an alert
    s.close()


def test_alert_gating_skips_small_targets_and_marks_sent(monkeypatch):
    from app.config import get_settings
    from app import follow_watch
    from app.follow_watch import _alert_pending_follows, _snapshot_follows
    from app.models import FollowEdge

    s, p = _new_product("LW-Gamma", "LabC")
    st = get_settings()

    _snapshot_follows(s, FakeClient({"LabC": [_author("alice", 5000)]}), p, "LabC", st, Counter())
    # new follows: one big (alertable), one tiny (below the 1000 floor)
    _snapshot_follows(
        s, FakeClient({"LabC": [_author("alice", 5000), _author("bigcorp", 80000),
                                _author("tinyacct", 100)]}),
        p, "LabC", st, Counter(),
    )

    sent = []
    monkeypatch.setattr(follow_watch, "alert_new_follow",
                        lambda session, watcher, edge, prod: sent.append(edge.target_handle) or True)
    stats = Counter()
    _alert_pending_follows(s, "LabC", p, st, stats)

    assert sent == ["bigcorp"]              # tinyacct filtered by the follower floor
    assert stats["follow_alerts"] == 1
    big = s.query(FollowEdge).filter_by(target_handle="bigcorp").one()
    assert big.alerted is True              # marked so it won't re-fire tomorrow
    s.close()


def test_follow_card_shape():
    from app.alerts import _build_follow_card
    from app.models import FollowEdge

    edge = FollowEdge(watcher_handle="LabX", target_handle="acme",
                      target_name="Acme Inc", target_followers=12345, target_bio="we build X")
    card = _build_follow_card("LabX", edge, None)
    assert card["msg_type"] == "interactive"
    assert card["card"]["header"]["template"] == "turquoise"
    btn = card["card"]["elements"][1]["actions"][0]
    assert btn["url"] == "https://x.com/acme"


def test_follow_watch_endpoint_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.post("/debug/follow-watch").status_code == 401
