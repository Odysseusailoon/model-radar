"""Dashboard aggregation, chart geometry, and the routes that render them."""
from datetime import datetime, timedelta, timezone

import pytest

from app.charts import PALETTE, assign_colors, build_line_chart, build_sentiment_bars
from app.stats import build_overview


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded(client):
    """Two products with evidence spread across categories and sentiments."""
    from app.db import SessionLocal
    from app.models import Evidence, Product

    s = SessionLocal()
    a = Product(name="ProdA", keywords=[], official_accounts=[], seed_kols=[])
    b = Product(name="ProdB", keywords=[], official_accounts=[], seed_kols=[])
    s.add_all([a, b])
    s.commit()

    now = datetime.now(timezone.utc)
    rows = [
        (a, "demo", "positive", 500_000, 0, "approved"),
        (a, "demo", "positive", 100_000, 1, "pending"),
        (a, "customer_case", "neutral", 20_000, 2, "pending"),
        (a, "irrelevant", "negative", 900, 3, "rejected"),
        (b, "expert_review", "negative", 300_000, 1, "pending"),
        (b, "news", "neutral", 5_000, 40, "pending"),  # outside a 14-day window
    ]
    for i, (prod, cat, sent, followers, days_ago, status) in enumerate(rows):
        s.add(Evidence(
            tweet_id=f"t{i}", product_id=prod.id, author_handle=f"user{i}",
            author_followers=followers, category=cat, sentiment=sent,
            confidence=0.9, review_status=status, text="x",
            posted_at=now - timedelta(days=days_ago), classification={},
            media_urls=[],
        ))
    s.commit()
    s.close()
    yield


def test_overview_counts_signal_categories_only(seeded):
    from app.db import SessionLocal

    s = SessionLocal()
    o = build_overview(s, days=14)
    s.close()
    assert o.total == 6
    # demo + demo + customer_case + expert_review; news and irrelevant excluded.
    assert o.signal == 4
    assert o.pending == 4
    assert o.failed == 0


def test_overview_reach_sums_only_signal_authors(seeded):
    from app.db import SessionLocal

    s = SessionLocal()
    o = build_overview(s, days=14)
    s.close()
    # 500k + 100k + 20k + 300k; the 900-follower irrelevant row is excluded.
    assert o.reach == 920_000


def test_overview_window_excludes_older_rows(seeded):
    """The 40-day-old row must not land in a 14-day series."""
    from app.db import SessionLocal

    s = SessionLocal()
    o = build_overview(s, days=14)
    s.close()
    assert len(o.days) == 14
    assert sum(o.series["ProdA"]) == 4
    assert sum(o.series["ProdB"]) == 1  # its 40-day-old row fell outside


def test_overview_product_filter_scopes_everything(seeded):
    from app.db import SessionLocal
    from app.models import Product

    s = SessionLocal()
    pid = s.query(Product).filter_by(name="ProdA").one().id
    o = build_overview(s, product_id=pid, days=14)
    s.close()
    assert o.total == 4
    assert o.signal == 3


def test_colors_follow_entity_not_rank():
    """A filter that drops a product must not repaint the survivors."""
    full = assign_colors(["ProdA", "ProdB", "ProdC"])
    assert full["ProdA"]["css"] == "var(--series-1)"
    assert full["ProdB"]["css"] == "var(--series-2)"
    # Re-assigning in the same configured order keeps each product's hue.
    again = assign_colors(["ProdA", "ProdB", "ProdC"])
    assert again["ProdB"]["css"] == full["ProdB"]["css"]


def test_colors_fold_tail_into_other_past_the_palette():
    """A 4th+ series is never a generated hue."""
    got = assign_colors([f"P{i}" for i in range(6)])
    assert got["P3"]["css"] == "var(--series-other)"
    assert len({c["css"] for c in got.values()}) == len(PALETTE) + 1


def test_line_chart_geometry_scales_to_axis_max():
    days = [datetime(2026, 7, 1).date() + timedelta(days=i) for i in range(5)]
    chart = build_line_chart(days, {"A": [0, 2, 4, 3, 1]})
    assert not chart.empty
    assert chart.y_max >= 4
    pts = chart.series[0]["points"]
    assert len(pts) == 5
    # Zero sits on the baseline; the peak sits above it.
    assert pts[0][1] > pts[2][1]
    assert chart.series[0]["path"].startswith("M")


def test_line_chart_flags_empty_series():
    days = [datetime(2026, 7, 1).date() + timedelta(days=i) for i in range(3)]
    assert build_line_chart(days, {"A": [0, 0, 0]}).empty


def test_line_chart_survives_a_single_day():
    """max_pages=1-style edge case: one bucket must not divide by zero."""
    days = [datetime(2026, 7, 1).date()]
    chart = build_line_chart(days, {"A": [3]})
    assert len(chart.series[0]["points"]) == 1


def test_dashboard_renders_with_data(client, seeded):
    r = client.get("/", auth=("smoke-user", "smoke-pass"))
    assert r.status_code == 200
    assert "证据量趋势" in r.text
    assert "ProdA" in r.text


def test_dashboard_renders_empty_state_without_data(client):
    """The empty state must render rather than divide-by-zero on a fresh deploy."""
    r = client.get("/?product_id=999999", auth=("smoke-user", "smoke-pass"))
    assert r.status_code == 200


def test_dashboard_rejects_bad_query_params(client, seeded):
    """Hand-edited URLs must not 500 the overview."""
    for qs in ("?days=abc", "?days=-5", "?days=99999", "?product_id=xyz"):
        r = client.get(f"/{qs}", auth=("smoke-user", "smoke-pass"))
        assert r.status_code == 200, qs


def test_feed_moved_to_its_own_route(client, seeded):
    r = client.get("/feed", auth=("smoke-user", "smoke-pass"))
    assert r.status_code == 200
    assert "证据流" in r.text


def test_dashboard_requires_auth(client):
    assert client.get("/").status_code == 401
    assert client.get("/feed").status_code == 401


# ---------------------------------------------------------------------------
# Diverging sentiment bars
# ---------------------------------------------------------------------------
def test_sentiment_bars_center_on_neutral():
    """Neutral straddles the midline: half its width sits in each arm."""
    rows = build_sentiment_bars(
        {"positive": {"A": 5}, "neutral": {"A": 4}, "negative": {"A": 1}}, ["A"]
    )
    r = rows[0]
    assert r["total"] == 10
    # left arm = neg + neu/2 = 0.1 + 0.2; right arm = pos + neu/2 = 0.5 + 0.2
    assert r["left_arm"] == pytest.approx(0.3)
    assert r["right_arm"] == pytest.approx(0.7)


def test_sentiment_arms_never_overflow_their_half():
    """A positive-heavy row must still fit — percentage-of-own-total would not."""
    rows = build_sentiment_bars(
        {"positive": {"A": 99}, "neutral": {"A": 1}, "negative": {"A": 0}}, ["A"]
    )
    r = rows[0]
    assert r["pos_w"] + r["neu_half_w"] <= 100.0
    assert r["neg_w"] + r["neu_half_w"] <= 100.0


def test_sentiment_rows_share_one_scale():
    """Rows stay comparable: the widest arm across rows defines the scale."""
    rows = build_sentiment_bars(
        {"positive": {"A": 10, "B": 1}, "neutral": {"A": 0, "B": 0},
         "negative": {"A": 0, "B": 9}}, ["A", "B"]
    )
    a, b = rows
    assert a["pos_w"] == pytest.approx(100.0)   # widest arm fills its half
    assert b["neg_w"] == pytest.approx(90.0)    # scaled against the same max


def test_sentiment_skips_products_with_no_classified_rows():
    rows = build_sentiment_bars({"positive": {"A": 3}}, ["A", "B"])
    assert [r["name"] for r in rows] == ["A"]


def test_sentiment_handles_no_data_at_all():
    assert build_sentiment_bars({}, ["A"]) == []
