"""CSV export helpers — pure functions so the export format is unit-testable
without spinning up FastAPI or a database."""
from __future__ import annotations

import csv
import io
from typing import Iterable

from .models import Evidence

CSV_HEADER = [
    "日期", "作者", "粉丝数", "分类", "情感", "置信度",
    "摘要", "可引用句", "链接", "点赞", "转发", "评论", "复核状态",
]


def evidence_to_row(ev: Evidence) -> list:
    data = ev.classification or {}
    return [
        ev.posted_at.isoformat() if ev.posted_at else "",
        f"@{ev.author_handle}",
        ev.author_followers,
        ev.category or "",
        ev.sentiment or "",
        f"{(ev.confidence or 0.0):.2f}",
        data.get("summary_zh", ""),
        data.get("quotable_excerpt", ""),
        ev.tweet_url or "",
        ev.like_count,
        ev.retweet_count,
        ev.reply_count,
        ev.review_status,
    ]


def build_csv(items: Iterable[Evidence]) -> str:
    """Return CSV text with a UTF-8 BOM so Excel renders Chinese correctly."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for ev in items:
        writer.writerow(evidence_to_row(ev))
    return "﻿" + buf.getvalue()
