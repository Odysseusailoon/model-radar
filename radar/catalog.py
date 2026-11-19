"""Validated watchlists shared by the CLI, API and scheduled collector."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config/inference-radar.json"
GROUPS = ("engine", "platform", "neocloud", "us_models", "cn_models")
SOURCES = ("x", "github", "huggingface")


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1)
    group: Literal["engine", "platform", "neocloud", "us_models", "cn_models"]
    x_query: str = Field(default="", max_length=350)
    website: str
    github_repos: list[str] = Field(default_factory=list)
    hf_author: str = ""
    hf_families: list[str] = Field(default_factory=list)
    reference_urls: list[str] = Field(default_factory=list)
    reviewed_on: str = ""
    region_note: str = ""

    @field_validator("github_repos")
    @classmethod
    def repositories(cls, repos):
        import re
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", r) for r in repos):
            raise ValueError("github_repos must contain owner/repo identifiers")
        return repos

    @field_validator("hf_author")
    @classmethod
    def author(cls, value):
        import re
        if value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("hf_author must be an organization identifier")
        return value


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    description: str = ""
    entities: list[Entity] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [e.id for e in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate entity IDs")
        return self

    def select(self, ids=(), groups=()) -> list[Entity]:
        unknown = set(ids) - {e.id for e in self.entities}
        if unknown or set(groups) - set(GROUPS):
            raise ValueError(f"Unknown entities or groups: {sorted(unknown | (set(groups) - set(GROUPS)))}")
        selected = [e for e in self.entities if (not ids or e.id in ids) and (not groups or e.group in groups)]
        if not selected:
            raise ValueError("Selection contains no entities")
        return selected

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


def load_catalog(path=DEFAULT_CATALOG) -> Catalog:
    return Catalog.model_validate_json(Path(path).read_text())
