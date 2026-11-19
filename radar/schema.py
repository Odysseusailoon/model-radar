from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc(value: str | datetime) -> datetime:
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ScanOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: datetime
    until: datetime
    sources: list[Literal["x", "github", "huggingface"]] = Field(default_factory=lambda: ["x", "github", "huggingface"], min_length=1)
    max_requests: int = Field(default=60, ge=1, le=500)
    max_pages: int = Field(default=1, ge=1, le=10)
    page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("since", "until")
    @classmethod
    def timezone_aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def valid_window(self):
        if self.since >= self.until:
            raise ValueError("since must be before until (exclusive)")
        if (self.until - self.since).days > 366:
            raise ValueError("Scan windows are limited to 366 days")
        self.sources = list(dict.fromkeys(self.sources))
        return self


class Signal(BaseModel):
    id: str
    source: str
    source_id: str
    entity_ids: list[str]
    title: str
    text: str = ""
    url: str
    published_at: str
    observed_at: str
    event_kind: str
    evidence_kind: str
    topic_tags: list[str] = Field(default_factory=list)
    is_new: bool = True
    first_seen_at: str = ""
    metadata: dict = Field(default_factory=dict)


def signal_id(source: str, source_id: str) -> str:
    return source + ":" + hashlib.sha256(source_id.encode()).hexdigest()[:24]


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, limit: int):
        self.limit, self.used = limit, 0

    def consume(self):
        if self.used >= self.limit:
            raise BudgetExceeded("request_budget_exhausted")
        self.used += 1
