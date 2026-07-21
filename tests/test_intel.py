"""Competitive-intel changes: per-product dedup, partnership/eval classifier
fields, and the weekly digest. Uses the SQLite test DB from conftest."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.classifier import _default_failed, _normalize
from app.digest import build_digest
from app.pipeline import process_tweet
from app.xclient import Author, Tweet


def _fake_classifier(category="news"):
    """Stub with the real ClassificationResult shape process_tweet expects."""
    c = MagicMock()
    c.classify.return_value = MagicMock(
        data={"category": category, "sentiment": "neutral", "confidence": 0.9},
        failed=False,
    )
    return c


def _tweet(tid):
    return Tweet(id=tid, text="M2 beats GLM-5 and Kimi K3", author=Author(handle="a", followers=5000))


# ---------------------------------------------------------------------------
# #1 Cross-product attribution: one tweet may attach to several products.
# ---------------------------------------------------------------------------
def test_same_tweet_stores_once_per_product_but_not_twice_for_one():
    from app.db import SessionLocal
    from app.models import Product

    s = SessionLocal()
    a = Product(name="XP-Alpha", keywords=[], official_accounts=[], seed_kols=[])
    b = Product(name="XP-Beta", keywords=[], official_accounts=[], seed_kols=[])
    s.add_all([a, b])
    s.commit()
    clf = _fake_classifier()

    # A comparison tweet found under both products must land under BOTH.
    ev_a = process_tweet(s, a, _tweet("cross-1"), clf)
    ev_b = process_tweet(s, b, _tweet("cross-1"), clf)
    assert ev_a is not None and ev_b is not None
    assert ev_a.product_id == a.id and ev_b.product_id == b.id

    # But the same (tweet, product) pair is still deduped — no double-store, no
    # wasted LLM call.
    calls_before = clf.classify.call_count
    dup = process_tweet(s, a, _tweet("cross-1"), clf)
    assert dup is None
    assert clf.classify.call_count == calls_before  # dedup short-circuits before classify
    s.close()


# ---------------------------------------------------------------------------
# #2 Classifier schema: new intel fields are always present and coerced.
# ---------------------------------------------------------------------------
def test_normalize_carries_partnership_and_eval_fields():
    out = _normalize({
        "category": "partnership",
        "is_competitor_signal": True,
        "eval_signal": True,
        "benchmark_names": ["SWE-bench Verified", "LMArena"],
    })
    assert out["category"] == "partnership"
    assert out["is_competitor_signal"] is True
    assert out["eval_signal"] is True
    assert out["benchmark_names"] == ["SWE-bench Verified", "LMArena"]


def test_normalize_defaults_new_fields_when_missing():
    out = _normalize({"category": "news"})
    assert out["is_competitor_signal"] is False
    assert out["eval_signal"] is False
    assert out["benchmark_names"] == []


def test_failed_marker_has_new_fields():
    d = _default_failed("boom")
    for k in ("is_competitor_signal", "eval_signal", "benchmark_names"):
        assert k in d


# ---------------------------------------------------------------------------
# #3 Weekly digest: highlights, deltas, eval hits.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def digest_seed():
    from app.db import SessionLocal
    from app.models import Evidence, Product

    s = SessionLocal()
    p = Product(name="DG-Prod", keywords=[], official_accounts=[], seed_kols=[])
    s.add(p)
    s.commit()
    now = datetime.now(timezone.utc)
    rows = [
        ("partnership", {"is_competitor_signal": True, "summary_zh": "接入 Bedrock"}),
        ("demo", {"usable_for_marketing": True, "quotable_excerpt": "made a video",
                  "summary_zh": "x", "has_media_evidence": True}),
        ("expert_review", {"eval_signal": True, "benchmark_names": ["LMArena"], "summary_zh": "排名第二"}),
        ("news", {}),
    ]
    for i, (cat, data) in enumerate(rows):
        s.add(Evidence(
            tweet_id=f"dg-{i}", product_id=p.id, author_handle=f"u{i}",
            author_followers=(i + 1) * 10_000, category=cat, sentiment="positive",
            confidence=0.9, review_status="pending", text="x", posted_at=now,
            classification={"category": cat, **data}, media_urls=[],
        ))
    s.commit()
    pid = p.id
    s.close()
    return pid


def test_digest_buckets_highlights_and_eval(digest_seed):
    from app.db import SessionLocal

    s = SessionLocal()
    dg = build_digest(s, days=7)
    s.close()

    d = next(pd for pd in dg.products if pd.id == digest_seed)
    assert d.total == 4
    assert len(d.partnerships) == 1
    assert len(d.demos) == 1
    assert len(d.expert_reviews) == 1
    assert len(d.eval_hits) == 1           # the expert_review row carried eval_signal
    assert d.top_quote is not None         # the demo row is usable + quotable
    assert d.delta == 4                    # nothing in the prior window


def test_digest_floor_excludes_junk_small_accounts():
    """A 50-follower blue-check's empty praise must be counted but NOT headline
    the digest (the junk-small-account complaint)."""
    from datetime import datetime, timezone
    from app.db import SessionLocal
    from app.digest import build_digest
    from app.models import Evidence, Product

    s = SessionLocal()
    p = Product(name="DG-Floor", keywords=[], official_accounts=[], seed_kols=[])
    s.add(p); s.commit()
    now = datetime.now(timezone.utc)
    # junk: 50-follower "expert_review", plus a credible 80k-follower one
    s.add(Evidence(tweet_id="fl-junk", product_id=p.id, author_handle="tiny",
                   author_followers=50, category="expert_review", sentiment="positive",
                   confidence=0.9, review_status="pending", text="increíble", posted_at=now,
                   classification={"category": "expert_review"}, media_urls=[]))
    s.add(Evidence(tweet_id="fl-real", product_id=p.id, author_handle="big",
                   author_followers=80_000, category="expert_review", sentiment="positive",
                   confidence=0.9, review_status="pending", text="substantive", posted_at=now,
                   classification={"category": "expert_review", "quotable_excerpt": "real take"},
                   media_urls=[]))
    s.commit()
    dg = build_digest(s, days=7)
    d = next(pd for pd in dg.products if pd.id == p.id)
    s.close()

    assert d.by_category["expert_review"] == 2          # both counted (raw volume)
    assert [e.author_handle for e in d.expert_reviews] == ["big"]  # only the credible one headlines


def test_digest_route_renders(digest_seed):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.get("/digest?days=7", auth=("smoke-user", "smoke-pass"))
    assert r.status_code == 200
    assert "情报周报" in r.text
    assert "DG-Prod" in r.text


def test_digest_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        assert c.get("/digest").status_code == 401
