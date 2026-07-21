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


def test_build_query_adds_lang_operator_only_when_requested():
    p = MagicMock(keywords=["MiniMax"])
    assert "lang:en" in build_query(p, lang="en")
    assert "lang:" not in build_query(p)


def test_kol_pool_skips_non_english_tweets():
    from collections import Counter
    from app import collector
    from app.xclient import Author, Tweet
    p = MagicMock(keywords=["MiniMax"], seed_kols=["k"]); p.name = "MiniMax"
    client = MagicMock()
    client.user_last_tweets.return_value = [
        Tweet(id="1", text="MiniMax es increíble", lang="es", author=Author(handle="k")),
        Tweet(id="2", text="MiniMax M2 is great", lang="en", author=Author(handle="k")),
    ]
    stored = []
    orig = collector.process_tweet
    collector.process_tweet = lambda s, pr, t, c: stored.append(t.id) or MagicMock(category="news")
    try:
        settings = MagicMock(max_seed_kols_per_cycle=15, collect_lang="en")
        collector._kol_phase(MagicMock(), client, MagicMock(), [p], 300,
                             {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0, "kol_attributed": 0},
                             Counter(), [], settings)
    finally:
        collector.process_tweet = orig
    assert stored == ["2"]  # Spanish tweet skipped, English kept


# ---- collector hardening: rotating KOL window + surfaced source failures ----
def test_kol_window_rotates_and_caps():
    from app import collector
    kols = [f"k{i}" for i in range(10)]
    collector._rotation = 0
    w0 = collector._kol_window(kols, 3)
    collector._rotation = 3
    w1 = collector._kol_window(kols, 3)
    assert len(w0) == 3 and len(w1) == 3
    assert w0 == ["k0", "k1", "k2"]
    assert w1 == ["k3", "k4", "k5"]            # window advanced -> different KOLs covered


def test_kol_window_returns_all_when_under_cap():
    from app import collector
    assert collector._kol_window(["a", "@b ", ""], 15) == ["a", "b"]


def test_keyword_phase_records_source_failures_instead_of_swallowing():
    from unittest.mock import MagicMock
    from app import collector
    client = MagicMock()
    client.search_recent.side_effect = RuntimeError("429 rate limited")
    product = MagicMock(keywords=["MiniMax"], seed_kols=[], last_seen_tweet_id=None)
    product.name = "MiniMax"
    settings = MagicMock(max_pages_per_query=5)
    errors = []
    budget = collector._keyword_phase(
        MagicMock(), client, MagicMock(), [product], 300,
        {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0}, __import__("collections").Counter(),
        errors, settings,
    )
    assert budget == 300  # nothing consumed
    assert len(errors) == 1 and errors[0]["source"] == "keyword_search"
    assert "429" in errors[0]["error"]


def test_tweet_matches_product_by_keyword():
    from unittest.mock import MagicMock
    from app.collector import _tweet_matches_product
    from app.xclient import Author, Tweet
    glm = MagicMock(keywords=['"GLM-5.2"', "Z.ai"])
    mini = MagicMock(keywords=["MiniMax", "Hailuo"])
    t = Tweet(id="1", text="Tried GLM-5.2 today, beats everything", author=Author())
    assert _tweet_matches_product(t, glm) is True
    assert _tweet_matches_product(t, mini) is False


def test_kol_pool_attributes_tweet_to_every_mentioned_product():
    """A shared KOL's comparison tweet must land under EACH model it names."""
    from collections import Counter
    from unittest.mock import MagicMock
    from app import collector
    from app.xclient import Author, Tweet

    glm = MagicMock(keywords=["GLM-5"], seed_kols=["karpathy"]); glm.name = "GLM"
    kimi = MagicMock(keywords=["Kimi K3"], seed_kols=[]); kimi.name = "Kimi"
    client = MagicMock()
    client.user_last_tweets.return_value = [
        Tweet(id="9", text="GLM-5 and Kimi K3 both improved a lot", author=Author(handle="karpathy"))
    ]
    stored = []
    # process_tweet returns a truthy evidence-like object for each (product) call
    import app.collector as C
    orig = C.process_tweet
    C.process_tweet = lambda s, p, t, c: stored.append(p.name) or MagicMock(category="expert_review")
    try:
        totals = {"fetched": 0, "processed": 0, "skipped_dup": 0, "alerts": 0, "kol_attributed": 0}
        settings = MagicMock(max_seed_kols_per_cycle=15)
        collector._kol_phase(MagicMock(), client, MagicMock(), [glm, kimi], 300,
                             totals, Counter(), [], settings)
    finally:
        C.process_tweet = orig
    assert sorted(stored) == ["GLM", "Kimi"]     # attributed to BOTH mentioned models
    assert totals["kol_attributed"] == 2
