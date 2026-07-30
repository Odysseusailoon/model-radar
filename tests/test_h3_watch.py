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
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [_tw(103), _tw(101), _tw(95)]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    out = hw.run_h3_watch()
    assert out == {"new": 2, "pushed": True}
    assert hw._watermark == 103
    assert len(sent) == 1
    assert "新增 2 条" in sent[0]["header"]["title"]["content"]


def test_no_new_posts_no_push(monkeypatch):
    hw._watermark = 200
    monkeypatch.setattr(hw, "XDataClient",
                        lambda **kw: SimpleNamespace(search_recent=lambda q, max_pages: [_tw(150)]))
    sent = []
    monkeypatch.setattr(hw.feishu, "send_card", lambda cid, card: sent.append(card) or True)
    assert hw.run_h3_watch() == {"new": 0}
    assert not sent


def test_card_truncates_and_counts():
    n = hw.MAX_ITEMS_IN_CARD + 5
    card = hw.build_h3_card([_tw(i, likes=i) for i in range(1, n + 1)])
    body = card["elements"][0]["text"]["content"]
    assert "另有 5 条" in body
    assert card["header"]["template"] == "red"
