"""CSV export format — this file is the marketing team's deliverable, so its
columns and encoding must stay stable."""
import csv
import io
from datetime import datetime, timezone

from app.export import CSV_HEADER, build_csv, evidence_to_row
from app.models import Evidence


def _evidence():
    return Evidence(
        tweet_id="111",
        product_id=1,
        author_handle="karpathy",
        author_followers=1_000_000,
        text="full text",
        tweet_url="https://x.com/karpathy/status/111",
        posted_at=datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
        like_count=500, retweet_count=42, reply_count=7, quote_count=1, view_count=9999,
        category="expert_review", sentiment="positive", confidence=0.91,
        review_status="approved",
        classification={"summary_zh": "很强的评价", "quotable_excerpt": "this is SOTA"},
    )


def test_row_has_expected_columns_and_values():
    row = evidence_to_row(_evidence())
    assert len(row) == len(CSV_HEADER)
    assert row[1] == "@karpathy"
    assert row[2] == 1_000_000
    assert row[3] == "expert_review"
    assert row[5] == "0.91"                       # confidence formatted 2dp
    assert row[6] == "很强的评价"
    assert row[7] == "this is SOTA"
    assert row[8] == "https://x.com/karpathy/status/111"


def test_build_csv_has_bom_and_header_and_parses_back():
    text = build_csv([_evidence()])
    assert text.startswith("﻿")             # Excel-friendly UTF-8 BOM

    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0] == CSV_HEADER
    assert rows[1][1] == "@karpathy"


def test_build_csv_handles_missing_classification_fields():
    ev = _evidence()
    ev.classification = {}                        # no summary / excerpt
    text = build_csv([ev])
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[1][6] == ""                        # empty summary, no crash
