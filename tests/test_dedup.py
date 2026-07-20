"""Dedup logic — we must never double-store a tweet, and a duplicate must not
waste an LLM call. Uses fakes, no DB/network."""
from unittest.mock import MagicMock

from app.collector import _as_int, build_query
from app.pipeline import process_tweet
from app.xclient import Author, Tweet


def _tweet(tid="123"):
    return Tweet(id=tid, text="hi", author=Author(handle="a", followers=5))


def test_process_tweet_skips_duplicate_without_classifying():
    session = MagicMock()
    # already_stored -> True (scalar returns a truthy id)
    session.scalar.return_value = 999
    classifier = MagicMock()

    result = process_tweet(session, MagicMock(id=1), _tweet(), classifier)

    assert result is None
    classifier.classify.assert_not_called()   # no wasted LLM spend on dupes
    session.add.assert_not_called()


def test_process_tweet_classifies_and_stores_new_tweet():
    session = MagicMock()
    session.scalar.return_value = None         # not stored yet
    classifier = MagicMock()
    classifier.classify.return_value = MagicMock(
        data={"category": "demo", "sentiment": "positive", "confidence": 0.9},
        failed=False,
    )
    product = MagicMock(id=7)

    result = process_tweet(session, product, _tweet("456"), classifier)

    classifier.classify.assert_called_once()
    session.add.assert_called_once()
    session.commit.assert_called_once()
    assert result is not None


def test_as_int_handles_garbage():
    assert _as_int("123") == 123
    assert _as_int(None) == 0
    assert _as_int("not-a-number") == 0


def test_build_query_excludes_retweets_and_ors_keywords():
    product = MagicMock(keywords=["K3", "K3 大模型"])
    q = build_query(product)
    assert "-filter:retweets" in q
    assert " OR " in q
    assert "K3 大模型" in q


def test_build_query_returns_none_without_keywords():
    assert build_query(MagicMock(keywords=[])) is None
