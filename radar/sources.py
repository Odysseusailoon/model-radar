"""Bounded adapters. A post or benchmark claim is evidence, not verification."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import httpx

from app.xclient import XDataClient
from .catalog import Entity
from .schema import Budget, ScanOptions, Signal, signal_id, utc
from .topics import topic_tags


@dataclass
class Page:
    signals: list[Signal] = field(default_factory=list)
    has_more: bool = False
    invalid_records: int = 0


def x_query(entity: Entity, options: ScanOptions) -> str:
    stamp = lambda dt: dt.strftime("%Y-%m-%d_%H:%M:%S_UTC")
    return f"({entity.x_query}) since:{stamp(options.since)} until:{stamp(options.until)} -filter:retweets"


def jobs_for(entities: list[Entity], options: ScanOptions) -> list[dict]:
    jobs = []
    # Round-robin by source: cover every entity before adding extra repo jobs.
    for source in options.sources:
        for entity in entities:
            targets = ([entity.x_query] if source == "x" and entity.x_query else
                       entity.github_repos if source == "github" else
                       [entity.hf_author] if source == "huggingface" and entity.hf_author else [])
            for target in targets:
                jobs.append({"entity_id": entity.id, "source": source, "target": target,
                             "query": x_query(entity, options) if source == "x" else target})
    return jobs


class Sources:
    def __init__(self, budget: Budget, x_key="", github_token="", client=None, x_client=None):
        self.budget = budget
        self.x_key = x_key
        self.github_token = github_token
        self.http = client or httpx.Client(timeout=25, follow_redirects=False)
        self.owns_client = client is None
        self.x = x_client or XDataClient(x_key, before_request=budget.consume)

    def close(self):
        if self.owns_client:
            self.http.close()

    def _get(self, url, *, params=None, github=False):
        self.budget.consume()
        headers = {"User-Agent": "model-radar/1.0"}
        if github:
            headers["Accept"] = "application/vnd.github+json"
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
        response = self.http.get(url, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("expected_list_response")
        return payload, response.links.get("next", {}).get("url", "")

    def pages(self, entity: Entity, job: dict, options: ScanOptions):
        yield from getattr(self, "_" + job["source"])(entity, job, options)

    @staticmethod
    def _signal(entity, source, source_id, title, text, url, date, kind, evidence, metadata):
        return Signal(id=signal_id(source, source_id), source=source, source_id=source_id,
                      entity_ids=[entity.id], title=title, text=text[:4000], url=url,
                      published_at=utc(date).isoformat(), observed_at=datetime.now(timezone.utc).isoformat(),
                      event_kind=kind, evidence_kind=evidence, metadata=metadata,
                      topic_tags=topic_tags(title + " " + text))

    def _x(self, entity, job, options):
        cursor, cursors = "", set()
        for _ in range(options.max_pages):
            tweets, next_cursor, has_more = self.x.search_page(job["query"], cursor)
            page = Page(has_more=has_more)
            for tweet in tweets:
                if not tweet.id or not tweet.created_at:
                    page.invalid_records += 1
                    continue
                if not options.since <= utc(tweet.created_at) < options.until:
                    continue
                page.signals.append(self._signal(
                    entity, "x", tweet.id, tweet.text[:160], tweet.text,
                    f"https://x.com/i/status/{quote(tweet.id, safe='')}", tweet.created_at,
                    "social_mention", "unverified_social_post",
                    {"author": tweet.author.handle, "likes": tweet.like_count,
                     "reposts": tweet.retweet_count, "replies": tweet.reply_count,
                     "views": tweet.view_count}))
            yield page
            if not has_more:
                break
            if not next_cursor or next_cursor in cursors:
                raise ValueError("missing_or_repeated_cursor")
            cursors.add(next_cursor)
            cursor = next_cursor

    def _github(self, entity, job, options):
        repo = job["target"]
        for number in range(1, options.max_pages + 1):
            rows, next_url = self._get(f"https://api.github.com/repos/{repo}/releases",
                                       params={"per_page": options.page_size, "page": number}, github=True)
            page = Page(has_more=bool(next_url))
            for row in rows:
                if row.get("draft"):
                    continue
                date = row.get("published_at")
                if not row.get("id") or not date or not row.get("tag_name"):
                    page.invalid_records += 1
                    continue
                try:
                    inside = options.since <= utc(date) < options.until
                except ValueError:
                    page.invalid_records += 1
                    continue
                if not inside:
                    continue
                tag = row["tag_name"]
                page.signals.append(self._signal(
                    entity, "github", f"{repo}:{row['id']}", row.get("name") or tag,
                    row.get("body") or "", f"https://github.com/{repo}/releases/tag/{quote(tag, safe='')}",
                    date, "prerelease" if row.get("prerelease") else "software_release", "official_repository_release",
                    {"repository": repo, "tag": tag, "prerelease": bool(row.get("prerelease"))}))
            yield page
            if not next_url:
                break

    def _huggingface(self, entity, job, options):
        url = "https://huggingface.co/api/models"
        params = {"author": entity.hf_author, "sort": "lastModified", "direction": -1,
                  "limit": options.page_size, "full": "true", "cardData": "true"}
        seen_urls = set()
        for _ in range(options.max_pages):
            rows, next_url = self._get(url, params=params)
            page = Page(has_more=bool(next_url))
            reached_start = False
            for row in rows:
                model_id, date = row.get("id"), row.get("lastModified")
                if not model_id or not date:
                    page.invalid_records += 1
                    continue
                try:
                    changed = utc(date)
                except ValueError:
                    page.invalid_records += 1
                    continue
                reached_start |= changed < options.since
                if not options.since <= changed < options.until:
                    continue
                # Author filter is checked locally too; family filters avoid unrelated lab uploads.
                if model_id.split("/")[0].casefold() != entity.hf_author.casefold():
                    continue
                if entity.hf_families and not any(f.casefold() in model_id.split("/", 1)[-1].casefold() for f in entity.hf_families):
                    continue
                card = row.get("cardData") or {}
                license_value = card.get("license") or [t[8:] for t in row.get("tags", []) if t.startswith("license:")] or "unknown"
                files = [s.get("rfilename", "") for s in row.get("siblings", [])]
                weight_files = any(f.endswith((".safetensors", ".bin", ".gguf", ".pt", ".pth")) for f in files)
                page.signals.append(self._signal(
                    entity, "huggingface", f"{model_id}@{row.get('sha') or date}", model_id,
                    "Model repository updated. This may be a metadata edit; a new model release is not implied.",
                    f"https://huggingface.co/{quote(model_id, safe='/')}", date,
                    "model_repository_update", "official_model_metadata",
                    {"model_id": model_id, "revision": row.get("sha"), "license": license_value,
                     "gated": row.get("gated", "unknown"), "created_at": row.get("createdAt"),
                     "weight_files_listed": weight_files, "downloads": row.get("downloads"),
                     "pipeline_tag": row.get("pipeline_tag"), "license_verified": False}))
            if reached_start:
                page.has_more = False
            yield page
            if not page.has_more:
                break
            parsed = urlparse(next_url)
            if parsed.scheme != "https" or parsed.netloc != "huggingface.co" or parsed.path != "/api/models" or next_url in seen_urls:
                raise ValueError("invalid_pagination_url")
            seen_urls.add(next_url)
            url, params = next_url, None
