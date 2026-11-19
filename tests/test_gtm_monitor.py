from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.gtm_monitor import collect, connect, normalize, summary, render
from app.xclient import Author, Tweet, TweetPage, XDataClient, XAPIResponseError

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def tweet(id="1", age=1, account="inferact", **kwargs):
    return Tweet(id=id, created_at=NOW-timedelta(days=age), author=Author(handle=account, followers=100), **kwargs)


class Client:
    def __init__(self, pages):
        self.pages = pages
    def user_tweet_pages(self, **kwargs):
        yield from self.pages[:kwargs["max_pages"]]


@pytest.fixture
def db(tmp_path):
    c = connect(tmp_path / 'monitor.db')
    yield c
    c.close()


def test_idempotent_collection_updates_metrics_and_marks_new(db):
    c = Client([TweetPage([tweet(like_count=10)], False, '')])
    first = collect(db, c, accounts=['inferact'], now=NOW)
    assert first['results']['inferact']['new'] == 1
    c.pages[0].tweets[0].like_count = 20
    second = collect(db, c, accounts=['inferact'], now=NOW)
    assert second['results']['inferact']['new'] == 0
    result = summary(db, ['inferact'], now=NOW)
    assert result['accounts'][0]['median_engagements'] == 20
    assert result['accounts'][0]['follower_delta'] is None
    assert len(result['posts']) == 1


def test_repost_metrics_are_not_attributed_to_watched_account(db):
    t = tweet(account='someone_else', like_count=9999)
    collect(db, Client([TweetPage([t], False, '')]), accounts=['inferact'], now=NOW)
    a = summary(db, ['inferact'], now=NOW)['accounts'][0]
    assert (a['originals'], a['reposts'], a['median_engagements']) == (0, 1, None)
    assert a['followers'] is None


def test_partial_failure_keeps_evidence_and_exposes_error(db):
    class Broken:
        def user_tweet_pages(self, **kwargs):
            yield TweetPage([tweet()], True, 'next')
            raise TimeoutError('no secret bodies')
    result = collect(db, Broken(), accounts=['inferact'], now=NOW)
    assert result['results']['inferact']['coverage'] == 'error'
    assert len(summary(db, ['inferact'], now=NOW)['posts']) == 1


def test_page_cap_and_missing_timestamp_are_visible(db):
    result = collect(db, Client([TweetPage([tweet()], True, 'next')]), accounts=['inferact'], max_pages=1, now=NOW)
    assert result['results']['inferact']['coverage'] == 'page_cap'
    result = collect(db, Client([TweetPage([Tweet(id='bad')], False, '')]), accounts=['inferact'], now=NOW)
    assert result['results']['inferact']['coverage'] == 'invalid_records'


def test_pinned_old_post_does_not_end_window_early(db):
    pages = [TweetPage([tweet('old', 100), tweet('1')], True, 'a'), TweetPage([tweet('2', 2)], False, '')]
    result = collect(db, Client(pages), accounts=['inferact'], now=NOW)
    assert result['results']['inferact']['pages'] == 2
    assert len(summary(db, ['inferact'], now=NOW)['posts']) == 2


def test_missing_views_is_not_zero_and_quotes_are_owned():
    p = normalize(tweet(raw={'isQuote':True}, quote_count=3), 'inferact')
    assert p['kind'] == 'quote' and p['engagements'] == 3
    assert p['engagement_per_view_pct'] is None


def test_html_escapes_untrusted_post_content(db):
    collect(db, Client([TweetPage([tweet(text='<script>alert(1)</script>')],False,'')]), accounts=['inferact'], now=NOW)
    html = render(summary(db, ['inferact'], now=NOW))
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html


def test_failed_envelope_is_not_empty_success(monkeypatch):
    monkeypatch.setattr(XDataClient, '_get', lambda *a, **k: {'status':'error', 'msg':'blocked'})
    with pytest.raises(XAPIResponseError):
        list(XDataClient('not-real').user_tweet_pages(user_name='inferact'))


def test_repeated_cursor_cannot_silently_truncate(monkeypatch):
    monkeypatch.setattr(XDataClient, '_get', lambda *a, **k: {'data':{'tweets':[]}, 'has_next_page':True,'next_cursor':'same'})
    with pytest.raises(XAPIResponseError):
        list(XDataClient('not-real').user_tweet_pages(user_name='inferact', max_pages=4))


def test_window_and_followers_over_time(db):
    c=Client([TweetPage([tweet()],False,'')])
    collect(db,c,accounts=['inferact'],now=NOW-timedelta(days=1))
    c.pages[0].tweets[0].author.followers=120
    collect(db,c,accounts=['inferact'],now=NOW)
    a=summary(db,['inferact'],now=NOW)['accounts'][0]
    assert a['follower_delta']==20
    assert a['coverage']['coverage']=='source_exhausted'
    assert summary(db,['inferact'],days=60,now=NOW)['accounts'][0]['coverage']['coverage']=='window_not_fully_scanned'
