"""H3 launch watch: watermark init (no flood), new-post push, card shape."""
from types import SimpleNamespace

import app.h3_watch as hw


def _tw(tid, likes=10, handle="alice", followers=1000, text="H3 is great"):
    return SimpleNamespace(
        id=str(tid), like_count=likes, retweet_count=0, reply_count=0,
        text=text, url=f"https://x.com/i/status/{tid}",
        author=SimpleNamespace(handle=handle, followers=followers),
    )


def test_first_cycle_initialises_without_pushing(monkeypatch):
    hw._watermark = 0
    monkeypatch.setattr(hw, "XDataClient",
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [_tw(100), _tw(99)]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    out = hw.run_h3_watch()
    assert out.get("initialised") is True
    assert hw._watermark == 100
    assert not sent


def test_second_cycle_pushes_only_new(monkeypatch):
    hw._watermark = 100
    monkeypatch.setattr(hw, "XDataClient",
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [_tw(103), _tw(101, handle="bob"), _tw(95)]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    out = hw.run_h3_watch()
    assert out == {"new": 2, "shown": 2, "pushed": True}
    assert hw._watermark == 103
    assert len(sent) == 1
    assert "2 new posts" in sent[0]["header"]["title"]["content"]


def test_no_new_posts_no_push(monkeypatch):
    hw._watermark = 200
    monkeypatch.setattr(hw, "XDataClient",
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [_tw(150)]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    assert hw.run_h3_watch() == {"new": 0}
    assert not sent


def test_card_groups_by_theme():
    tweets = [
        _tw(1, likes=50, text="the lipsync is amazing"),
        _tw(2, likes=30, text="quite blurry 2k, looks like 480p"),
        _tw(3, likes=10, text="Made with MiniMax H3"),
    ]
    card = hw.build_h3_card(tweets)
    body = "\n".join(el["text"]["content"] for el in card["elements"] if el.get("tag") == "div")
    assert "🟢 1 positive · 🔴 1 issues · 3 total" in body
    assert "LIPSYNC/AUDIO — 1" in body
    assert "2K QUALITY — 1 · 🔴1" in body
    assert "SHOWCASE / OTHER — 1" in body
    assert card["header"]["template"] == "red"


def test_card_overflow_counter():
    tweets = [_tw(i, likes=i, text="amazing lipsync") for i in range(1, 10)]
    card = hw.build_h3_card(tweets)
    body = "\n".join(el["text"]["content"] for el in card["elements"] if el.get("tag") == "div")
    assert "7 more" in body  # theme cap shows 2 per theme


def test_quality_floor_drops_reply_noise():
    noise = [
        _tw(1, likes=0, followers=200, text="@someone @Hailuo_AI amazing bro"),
        _tw(2, likes=0, followers=200, text="nice creativity dear"),
    ]
    real = _tw(3, likes=50, followers=200, text="H3 lipsync test results")
    kept = hw._quality(noise + [real])
    assert [t.id for t in kept] == ["3"]


def test_quality_floor_dedupes_author():
    a1 = _tw(1, likes=5, handle="same", text="first post ok")
    a2 = _tw(2, likes=90, handle="same", text="viral post wow")
    kept = hw._quality([a1, a2])
    assert len(kept) == 1 and kept[0].id == "2"


def test_all_filtered_means_no_push(monkeypatch):
    hw._watermark = 100
    junk = _tw(200, likes=0, followers=50, text="@x @Hailuo_AI cool")
    monkeypatch.setattr(hw, "XDataClient",
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [junk]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    out = hw.run_h3_watch()
    assert out == {"new": 1, "pushed": False, "filtered_out": 1}
    assert not sent
