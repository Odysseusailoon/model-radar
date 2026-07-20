"""Regression: the two tweet endpoints use different response envelopes.

advanced_search returns {tweets: [...]}; last_tweets returns
{data: {tweets: [...]}}. Reading the top level on last_tweets yields zero
tweets with no error, so seed-KOL polling reported success while collecting
nothing. Both shapes verified live 2026-07-20.
"""
from app.xclient import XDataClient, _tweets_from

RAW = {
    "type": "tweet",
    "id": "1",
    "url": "https://x.com/a/status/1",
    "text": "hello",
    "createdAt": "Fri Jul 17 21:37:09 +0000 2026",
    "likeCount": 1,
    "author": {"userName": "a", "id": "9", "followers": 5},
}


def test_tweets_from_reads_top_level_envelope():
    assert _tweets_from({"tweets": [RAW]}) == [RAW]


def test_tweets_from_reads_nested_data_envelope():
    assert _tweets_from({"data": {"tweets": [RAW], "pin_tweet": None}}) == [RAW]


def test_tweets_from_handles_empty_and_missing():
    assert _tweets_from({}) == []
    assert _tweets_from({"tweets": []}) == []
    assert _tweets_from({"data": None}) == []
    assert _tweets_from({"data": {"pin_tweet": None}}) == []


def test_user_last_tweets_yields_from_nested_envelope(monkeypatch):
    """The actual bug: this returned nothing for every seed KOL."""
    def fake_get(self, path, params):
        return {"data": {"tweets": [RAW], "pin_tweet": None}, "has_next_page": False}

    monkeypatch.setattr(XDataClient, "_get", fake_get)
    got = list(XDataClient("k").user_last_tweets(user_name="MiniMax_AI"))

    assert len(got) == 1, "seed-KOL polling must read the nested envelope"
    assert got[0].text == "hello"


def test_search_recent_still_reads_top_level(monkeypatch):
    def fake_get(self, path, params):
        return {"tweets": [RAW], "has_next_page": False}

    monkeypatch.setattr(XDataClient, "_get", fake_get)
    assert len(list(XDataClient("k").search_recent("MiniMax"))) == 1
