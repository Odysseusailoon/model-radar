"""One scan engine for CLI, API and scheduler; checkpoint every source job."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx

from .catalog import Catalog, Entity
from .schema import Budget, BudgetExceeded, ScanOptions
from .sources import Sources, jobs_for
from .store import Store


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_error(exc):
    # Never persist response bodies, request headers or exception text containing credentials.
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, BudgetExceeded):
        return "request_budget_exhausted"
    return type(exc).__name__


def scan(catalog: Catalog, entities: list[Entity], options: ScanOptions, store: Store,
         *, x_key="", github_token="", resume=None, sources_factory=Sources):
    with store.lock():
        if resume:
            run = store.get(resume)
            if run["catalog_hash"] != catalog.digest():
                raise ValueError("Catalog changed; start a new run instead of mixing configurations")
            options = ScanOptions.model_validate(run["options"])
            entities = [Entity.model_validate(e) for e in run["entities"]]
            run["attempts"] += 1
        else:
            run = {"schema_version": 1, "id": uuid4().hex, "started_at": now(), "attempts": 1,
                   "catalog_hash": catalog.digest(), "entities": [e.model_dump() for e in entities],
                   "options": options.model_dump(mode="json"), "signals": [], "coverage": [],
                   "requests_used": 0, "status": "running"}
        jobs = jobs_for(entities, options)
        if not jobs:
            raise ValueError("No configured sources for this selection")
        run["status"] = "running"
        run["completed_at"] = None
        store.save(run)
        budget = Budget(options.max_requests)
        adapters = sources_factory(budget, x_key=x_key, github_token=github_token)
        signals = {s["id"]: s for s in run["signals"]}
        seen = store.seen()
        key = lambda j: (j["entity_id"], j["source"], j["target"])
        previous = {key(c): c for c in run["coverage"]}
        by_id = {e.id: e for e in entities}
        coverage = []
        prior_requests = run["requests_used"]
        try:
            for job in jobs:
                prior = previous.get(key(job))
                # Capped sources are deliberate bounded results, not failed requests.
                if prior and prior["status"] in ("ok", "partial"):
                    coverage.append(prior)
                    continue
                result = {**job, "status": "ok", "pages": 0, "fetched": 0,
                          "truncated": False, "invalid_records": 0, "error": None}
                if job["source"] == "x" and not x_key:
                    result.update(status="skipped", error="missing_twitterapi_key")
                else:
                    try:
                        for page in adapters.pages(by_id[job["entity_id"]], job, options):
                            result["pages"] += 1
                            result["fetched"] += len(page.signals)
                            result["truncated"] = page.has_more
                            result["invalid_records"] += page.invalid_records
                            for item in page.signals:
                                row = item.model_dump()
                                first = seen.setdefault(row["id"], {"run_id": run["id"], "at": now()})
                                row["is_new"] = first["run_id"] == run["id"]
                                row["first_seen_at"] = first["at"]
                                if row["id"] in signals:
                                    row["entity_ids"] = sorted(set(row["entity_ids"] + signals[row["id"]]["entity_ids"]))
                                signals[row["id"]] = row
                        if result["truncated"] or result["invalid_records"]:
                            result["status"] = "partial"
                    except Exception as exc:
                        result.update(status="skipped" if isinstance(exc, BudgetExceeded) and not result["pages"] else "error",
                                      error=safe_error(exc))
                coverage.append(result)
                remaining = [previous[key(j)] for j in jobs[len(coverage):] if key(j) in previous]
                run.update(signals=list(signals.values()), coverage=coverage + remaining,
                           requests_used=prior_requests + budget.used)
                store.save(run)
                store.save_seen(seen)
        finally:
            adapters.close()
        run["signals"] = sorted(signals.values(), key=lambda s: s["published_at"], reverse=True)
        run["coverage"] = coverage
        run["requests_used"] = prior_requests + budget.used
        run["status"] = "complete" if all(c["status"] == "ok" for c in coverage) else "partial"
        if coverage and all(c["status"] in ("error", "skipped") for c in coverage) and not signals:
            run["status"] = "failed"
        run["completed_at"] = now()
        store.save(run)
        return run
