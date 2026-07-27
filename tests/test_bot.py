"""Feishu GTM bot — comprehensive tests for the pure logic (parsing, triage,
push gate, launch detection, query handlers, card building). No Feishu network."""
from datetime import datetime, timezone

import pytest

from app import bot
from app.feishu import build_card
from app.models import Evidence


# ---------------------------------------------------------------------------
# command parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,cmd,args", [
    ("/digest", "digest", ""),
    ("/digest MiniMax", "digest", "MiniMax"),
    ("@_user_1 review GLM", "review", "GLM"),
    ("  /partnership  ", "partnership", ""),
    ("周报 MiniMax", "digest", "MiniMax"),
    ("大佬评价 Kimi", "review", "Kimi"),
    ("谁在聊 flux", "kol", "flux"),
    ("周报MiniMax", "digest", "MiniMax"),      # chinese head, no space
    ("/kol", "kol", ""),
    ("nonsense words", "help", ""),
    ("", "help", ""),
])
def test_parse_command(text, cmd, args):
    assert bot.parse_command(text) == (cmd, args)


# ---------------------------------------------------------------------------
# launch detection
# ---------------------------------------------------------------------------
def _ev(text="", cat="news", followers=1000, conf=0.9, likes=0, rt=0, relevant=True, failed=False):
    return Evidence(
        tweet_id="t", text=text, category=cat, author_followers=followers, confidence=conf,
        like_count=likes, retweet_count=rt, classification_failed=failed,
        classification={"relevant": relevant, "category": cat},
    )


def test_is_launch_positive():
    assert bot.is_launch(_ev("We just released MiniMax H3, open-source SOTA video!", cat="news"))
    assert bot.is_launch(_ev("Introducing Kling 3.0 — now available", cat="promo"))
    assert bot.is_launch(_ev("weights are out on HuggingFace", cat="news"))


def test_is_launch_negative():
    assert not bot.is_launch(_ev("this model is really good", cat="expert_review"))
    assert not bot.is_launch(_ev("launched my new blog", cat="irrelevant"))          # not relevant category
    assert not bot.is_launch(_ev("Kling launched", cat="news", relevant=False))       # not relevant


# ---------------------------------------------------------------------------
# triage — the core importance judgement
# ---------------------------------------------------------------------------
def test_triage_launch_is_realtime():
    v = bot.triage(_ev("Seedance 2.5 released, weights out", cat="news"))
    assert v.tier == "realtime" and v.kind == "launch"


def test_triage_partnership_is_realtime():
    v = bot.triage(_ev("We integrated GLM into our product", cat="partnership", conf=0.9))
    assert v.tier == "realtime" and v.kind == "partnership"


def test_triage_mega_account_is_realtime():
    v = bot.triage(_ev("nice model", cat="expert_review", followers=500_000))
    assert v.tier == "realtime" and v.kind == "mega"


def test_triage_viral_is_realtime():
    v = bot.triage(_ev("cool demo", cat="demo", followers=800, likes=5000, rt=900))
    assert v.tier == "realtime" and v.kind == "viral"


def test_triage_normal_demo_is_digest():
    v = bot.triage(_ev("made a video with it", cat="demo", followers=8000, likes=10))
    assert v.tier == "digest"


def test_triage_small_expert_dropped():
    v = bot.triage(_ev("increíble", cat="expert_review", followers=50, likes=1))
    assert v.tier == "drop"


def test_triage_irrelevant_dropped():
    assert bot.triage(_ev("k3 the car", cat="irrelevant", relevant=False)).tier == "drop"
    assert bot.triage(_ev("x", failed=True)).tier == "drop"


# ---------------------------------------------------------------------------
# push gate — anti-spam guardrails
# ---------------------------------------------------------------------------
def test_push_gate_daily_cap_and_overflow():
    g = bot.PushGate(daily_cap=2, quiet_start=0, quiet_end=0)
    now = datetime(2026, 7, 25, 18, tzinfo=timezone.utc)
    v = bot.Verdict("realtime", "viral", "viral")
    assert g.allow(v, now) is True
    assert g.allow(v, now) is True
    assert g.allow(v, now) is False          # over cap
    assert len(g.overflow) == 1              # overflow recorded for the digest


def test_push_gate_launch_bypasses_cap_and_quiet():
    g = bot.PushGate(daily_cap=0, quiet_start=0, quiet_end=23)   # capped + always-quiet
    now = datetime(2026, 7, 25, 3, tzinfo=timezone.utc)
    launch = bot.Verdict("realtime", "launch", "launch")
    assert g.allow(launch, now) is True      # launch always gets through


def test_push_gate_quiet_hours():
    g = bot.PushGate(daily_cap=10, quiet_start=8, quiet_end=15)
    v = bot.Verdict("realtime", "viral", "viral")
    assert g.allow(v, datetime(2026, 7, 25, 10, tzinfo=timezone.utc)) is False   # in quiet window
    assert g.allow(v, datetime(2026, 7, 25, 18, tzinfo=timezone.utc)) is True    # outside


def test_push_gate_ignores_non_realtime():
    g = bot.PushGate(daily_cap=10, quiet_start=0, quiet_end=0)
    assert g.allow(bot.Verdict("digest", "x"), datetime(2026, 7, 25, 12, tzinfo=timezone.utc)) is False


# ---------------------------------------------------------------------------
# query handlers — against the SQLite test DB
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seeded():
    from app.db import init_db, SessionLocal
    from app.models import Product
    init_db()
    s = SessionLocal()
    p = Product(name="MiniMax", keywords=[], official_accounts=[], seed_kols=[])
    s.add(p); s.commit()
    now = datetime.now(timezone.utc)
    rows = [
        ("bot-p", "partnership", "acme", 40000, "MiniMax now on AWS Bedrock", 30, {"quotable_excerpt": "MiniMax now on AWS Bedrock"}),
        ("bot-d", "demo", "maker", 60000, "made a full film with Hailuo", 200, {"has_media_evidence": True, "quotable_excerpt": "made a full film"}),
        ("bot-r", "expert_review", "bigvoice", 120000, "Hailuo physics is SOTA, beats Veo on fluids", 90, {"quotable_excerpt": "Hailuo physics is SOTA"}),
        ("bot-l", "news", "press", 20000, "MiniMax released H3, open-source weights out now", 300, {}),
        ("bot-junk", "expert_review", "tiny", 40, "increíble", 0, {}),
    ]
    for tid, cat, h, f, text, likes, extra in rows:
        s.add(Evidence(tweet_id=tid, product_id=p.id, author_handle=h, author_followers=f,
                       category=cat, confidence=0.9, like_count=likes, text=text, posted_at=now,
                       tweet_url=f"https://x.com/{h}/status/1", review_status="pending",
                       classification={"relevant": True, "category": cat, **extra}, media_urls=[]))
    s.commit(); s.close()
    yield
    # teardown: keep the shared SQLite evidence table clean for other test modules
    s = SessionLocal()
    s.query(Evidence).filter(Evidence.tweet_id.like("bot-%")).delete(synchronize_session=False)
    s.query(Product).filter_by(name="MiniMax").delete()
    s.commit(); s.close()


def _run(handler, args=""):
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        return handler(s, args)
    finally:
        s.close()


def test_handle_partnership(seeded):
    card = _run(bot.handle_partnership)
    assert "合作" in card["title"]
    assert "acme" in card["text"] and "Bedrock" in card["text"]


def test_handle_demo(seeded):
    assert "maker" in _run(bot.handle_demo, "MiniMax")["text"]


def test_handle_review_filters_small_accounts(seeded):
    text = _run(bot.handle_review)["text"]
    assert "bigvoice" in text          # 120k-follower expert kept
    assert "tiny" not in text          # 40-follower junk filtered by follower floor


def test_handle_launch(seeded):
    text = _run(bot.handle_launch)["text"]
    assert "press" in text and "H3" in text


def test_handle_kol(seeded):
    text = _run(bot.handle_kol, "Hailuo")["text"]
    assert "bigvoice" in text or "maker" in text


def test_handle_digest(seeded):
    card = _run(bot.handle_digest, "MiniMax")
    assert "周报" in card["title"] and "MiniMax" in card["text"]


def test_dispatch_routes(seeded):
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        assert "指令" in bot.dispatch(s, "help")["title"]
        assert "合作" in bot.dispatch(s, "/partnership")["title"]
        assert "周报" in bot.dispatch(s, "周报")["title"]
    finally:
        s.close()


# ---------------------------------------------------------------------------
# card building (pure)
# ---------------------------------------------------------------------------
def test_build_card_shape():
    c = build_card("T", "hello\nworld", template="red", url="https://x.com/a/1")
    assert c["header"]["template"] == "red"
    assert c["header"]["title"]["content"] == "T"
    assert c["elements"][0]["text"]["content"] == "hello\nworld"
    assert c["elements"][1]["actions"][0]["url"] == "https://x.com/a/1"
    assert c["elements"][-1]["tag"] == "note"          # branded footer on every card


def test_build_card_no_url():
    c = build_card("T", "x")
    assert len(c["elements"]) == 2     # div + footer note, no action button


def test_build_card_splits_item_blocks():
    from app.feishu import ITEM_SEP
    c = build_card("T", ITEM_SEP.join(["a", "b", "c"]))
    tags = [e["tag"] for e in c["elements"]]
    assert tags == ["div", "hr", "div", "hr", "div", "note"]   # sections + hairlines


def test_fmt_n_compact():
    assert bot._fmt_n(316748) == "31.7万"
    assert bot._fmt_n(65694) == "6.6万"
    assert bot._fmt_n(10000) == "1万"
    assert bot._fmt_n(4770) == "4,770"
    assert bot._fmt_n(None) == "0"


def test_handler_cards_carry_template(seeded):
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        assert bot.handle_partnership(s, "")["template"] == "turquoise"
        assert bot.handle_launch(s, "")["template"] == "red"
        assert bot.handle_digest(s, "")["template"] == "indigo"
    finally:
        s.close()


def test_product_alias_resolves_via_keywords(seeded):
    """'Hailuo' is a MiniMax keyword, not a product name — must still resolve."""
    from app.db import SessionLocal
    from app.crud import upsert_product
    s = SessionLocal()
    try:
        upsert_product(s, {"name": "MiniMax", "keywords": ["MiniMax", "Hailuo"],
                           "official_accounts": [], "seed_kols": []})
        pid = bot._product_id(s, "Hailuo")
        assert pid is not None
    finally:
        s.close()


def test_debug_bot_query_endpoint(seeded):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.post("/debug/bot-query?text=help").status_code == 401   # auth required
        r = c.post("/debug/bot-query?text=help", auth=("smoke-user", "smoke-pass"))
        assert r.status_code == 200 and "指令" in r.json()["title"]
        r = c.post("/debug/bot-query?text=/partnership", auth=("smoke-user", "smoke-pass"))
        assert "合作" in r.json()["title"]


# ---------------------------------------------------------------------------
# real-time pipeline push (maybe_bot_push)
# ---------------------------------------------------------------------------
def _push_ev(tid, text="MiniMax released H3, weights out now", cat="news", followers=50000):
    from datetime import datetime, timezone
    return Evidence(tweet_id=tid, text=text, category=cat, author_followers=followers,
                    confidence=0.9, like_count=100, retweet_count=10,
                    author_handle="press", tweet_url="https://x.com/press/1",
                    posted_at=datetime.now(timezone.utc),
                    classification={"relevant": True, "category": cat}, media_urls=[])


def test_maybe_bot_push_noop_without_config(monkeypatch, seeded):
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        # settings have no feishu app creds in tests -> must be a clean no-op
        assert bot.maybe_bot_push(s, type("P", (), {"name": "X"})(), _push_ev("push-0")) is False
    finally:
        s.close()


def test_maybe_bot_push_sends_and_dedupes(monkeypatch, seeded):
    from app.db import SessionLocal
    from app.models import AlertSent
    from app.config import get_settings
    s = SessionLocal()
    st = get_settings()
    monkeypatch.setattr(st, "feishu_app_id", "cli_x")
    monkeypatch.setattr(st, "feishu_app_secret", "sec")
    monkeypatch.setattr(st, "feishu_bot_chat_id", "oc_x")
    monkeypatch.setattr(st, "bot_quiet_start_utc", 0)
    monkeypatch.setattr(st, "bot_quiet_end_utc", 0)
    sent = []
    from app import feishu
    monkeypatch.setattr(feishu, "send_dict", lambda chat, payload: sent.append(payload) or True)
    p = type("P", (), {"name": "MiniMax"})()
    ev = _push_ev("push-1")
    try:
        assert bot.maybe_bot_push(s, p, ev) is True         # launch -> pushed
        assert "🚀" in sent[0]["title"]
        assert bot.maybe_bot_push(s, p, ev) is False        # dedup: same tweet never twice
        assert s.query(AlertSent).filter_by(tweet_id="push-1", alert_type="bot_push").count() == 1
        # a non-realtime item never pushes
        calm = _push_ev("push-2", text="just a nice thought", cat="expert_review", followers=500)
        assert bot.maybe_bot_push(s, p, calm) is False
    finally:
        s.query(AlertSent).filter(AlertSent.alert_type == "bot_push").delete()
        s.commit(); s.close()


def test_maybe_bot_push_respects_daily_cap(monkeypatch, seeded):
    from app.db import SessionLocal
    from app.models import AlertSent
    from app.config import get_settings
    s = SessionLocal()
    st = get_settings()
    monkeypatch.setattr(st, "feishu_app_id", "cli_x")
    monkeypatch.setattr(st, "feishu_app_secret", "sec")
    monkeypatch.setattr(st, "feishu_bot_chat_id", "oc_x")
    monkeypatch.setattr(st, "bot_daily_push_cap", 1)
    monkeypatch.setattr(st, "bot_quiet_start_utc", 0)
    monkeypatch.setattr(st, "bot_quiet_end_utc", 0)
    from app import feishu
    monkeypatch.setattr(feishu, "send_dict", lambda chat, payload: True)
    p = type("P", (), {"name": "MiniMax"})()
    try:
        # viral (non-launch) pushes respect the cap
        v1 = _push_ev("push-c1", text="insane demo", cat="demo", followers=500)
        v1.like_count = 5000; v1.retweet_count = 900
        v2 = _push_ev("push-c2", text="insane demo 2", cat="demo", followers=500)
        v2.like_count = 5000; v2.retweet_count = 900
        assert bot.maybe_bot_push(s, p, v1) is True
        assert bot.maybe_bot_push(s, p, v2) is False        # cap of 1 reached
        # ...but a LAUNCH bypasses the cap
        l = _push_ev("push-c3")
        assert bot.maybe_bot_push(s, p, l) is True
    finally:
        s.query(AlertSent).filter(AlertSent.alert_type == "bot_push").delete()
        s.commit(); s.close()
