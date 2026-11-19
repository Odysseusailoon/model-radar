"""Read-only agent API and dashboard over the same snapshots as `python -m radar`."""
from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates

from radar.catalog import load_catalog
from radar.engine import scan
from radar.report import csv_export, summary
from radar.schema import ScanOptions
from radar.store import Store
from radar.topics import RULES
from .config import get_settings

router = APIRouter()
basic = HTTPBasic(auto_error=False)
bearer = HTTPBearer(auto_error=False)
templates = Jinja2Templates(directory="app/templates")


def read_auth(credentials: HTTPBasicCredentials | None = Depends(basic),
              token: HTTPAuthorizationCredentials | None = Depends(bearer)):
    s = get_settings()
    if token and s.radar_read_token and secrets.compare_digest(token.credentials, s.radar_read_token):
        return
    if credentials and secrets.compare_digest(credentials.username, s.dashboard_user) and secrets.compare_digest(credentials.password, s.dashboard_password):
        return
    raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})


def store():
    return Store(get_settings().inference_radar_data_dir)


def latest():
    runs = store().recent(1)
    return runs[0] if runs else None


def run_radar_once():
    s = get_settings()
    catalog = load_catalog(s.inference_radar_catalog)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    options = ScanOptions(since=end - timedelta(days=s.inference_radar_days), until=end,
                          max_requests=s.inference_radar_max_requests, max_pages=s.inference_radar_max_pages)
    return summary(scan(catalog, catalog.entities, options, store(), x_key=s.twitterapi_key,
                        github_token=s.radar_github_token))


def configure_radar_job(scheduler):
    s = get_settings()
    if s.inference_radar_enabled:
        scheduler.add_job(run_radar_once, "interval", minutes=s.inference_radar_interval_minutes,
                          id="inference_radar", max_instances=1, coalesce=True)


@router.get("/api/radar/catalog", dependencies=[Depends(read_auth)])
def radar_catalog():
    return load_catalog(get_settings().inference_radar_catalog).model_dump()


@router.get("/api/radar/runs", dependencies=[Depends(read_auth)])
def radar_runs(limit: int = Query(default=20, ge=1, le=100)):
    return {"runs": [summary(r) for r in store().recent(limit)]}


@router.get("/api/radar/latest", dependencies=[Depends(read_auth)])
def radar_latest():
    run = latest()
    if run is None:
        raise HTTPException(404, "No scans yet")
    return run


@router.get("/api/radar/runs/{run_id}", dependencies=[Depends(read_auth)])
def radar_run(run_id: str):
    try:
        return store().get(run_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Run not found")


@router.get("/api/radar/runs/{run_id}/export", dependencies=[Depends(read_auth)])
def radar_export(run_id: str):
    return PlainTextResponse(csv_export(radar_run(run_id)), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="inference-radar-{run_id}.csv"'})


@router.get("/inference", response_class=HTMLResponse, dependencies=[Depends(read_auth)])
def inference_dashboard(request: Request, group: str = "", entity: str = "", source: str = "", topic: str = ""):
    catalog = load_catalog(get_settings().inference_radar_catalog)
    run = latest()
    entities = [e for e in catalog.entities if not group or e.group == group]
    ids = {e.id for e in entities if not entity or e.id == entity}
    rows = [s for s in (run or {}).get("signals", [])
            if ids.intersection(s["entity_ids"]) and (not source or s["source"] == source)
            and (not topic or topic in s.get("topic_tags", []))]
    return templates.TemplateResponse(request, "inference.html", {
        "active": "inference", "catalog": catalog, "run": run, "rows": rows,
        "inference_only": getattr(request.app.state, "inference_only", False),
        "coverage_counts": dict(Counter(c["status"] for c in (run or {}).get("coverage", []))),
        "entities": entities, "group": group, "entity": entity, "source": source, "topic": topic, "topics": RULES,
        "names": {e.id: e.name for e in catalog.entities},
        "enabled": get_settings().inference_radar_enabled,
        "interval": get_settings().inference_radar_interval_minutes})
