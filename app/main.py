"""FastAPI application: dashboard, review actions, CSV export, admin, webhook,
health — plus the APScheduler collection loop. Single-service deployment.
"""
from __future__ import annotations

import hmac
import io
import logging
import secrets
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from .classifier import Classifier
from .collector import collect_once
from .config import get_settings
from .crud import delete_product, get_product, list_products, seed_from_file, upsert_product
from .db import SessionLocal, init_db
from .export import build_csv
from .models import Evidence
from .pipeline import process_tweet
from .queries import EvidenceFilter, query_evidence
from .xclient import _map_tweet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("gtm")

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
security = HTTPBasic()

CATEGORIES = ["demo", "customer_case", "expert_review", "news", "promo", "irrelevant"]
SENTIMENTS = ["positive", "neutral", "negative"]
REVIEW_STATES = ["pending", "approved", "rejected"]
CATEGORY_LABELS = {
    "demo": "真实Demo", "customer_case": "客户Case", "expert_review": "大佬评价",
    "news": "资讯", "promo": "推广", "irrelevant": "无关", None: "未分类",
}

scheduler = BackgroundScheduler(timezone="UTC")


def _run_collection():
    try:
        stats = collect_once()
        log.info("Scheduled collection stats: %s", stats)
    except Exception:
        log.exception("Scheduled collection cycle crashed (will retry next interval)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.seed_products_file:
        s = SessionLocal()
        try:
            seed_from_file(s, settings.seed_products_file)
        except Exception:
            log.exception("Seeding failed (non-fatal)")
        finally:
            s.close()
    scheduler.add_job(
        _run_collection,
        "interval",
        minutes=settings.collect_interval_minutes,
        id="collect",
        next_run_time=None,  # first run after one interval; call /debug/collect to run now
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("Scheduler started: collecting every %d min", settings.collect_interval_minutes)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="GTM Evidence Radar", lifespan=lifespan)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, settings.dashboard_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------
# Health & debug
# --------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/debug/collect")
def debug_collect(_: str = Depends(require_auth)):
    """Manually trigger one collection cycle (handy right after deploy)."""
    return collect_once()


# --------------------------------------------------------------------------
# Evidence feed (/)
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def feed(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    f = EvidenceFilter.from_query(request.query_params)
    items = query_evidence(db, f)
    products = list_products(db)
    return templates.TemplateResponse(
        "feed.html",
        {
            "request": request,
            "items": items,
            "products": products,
            "categories": CATEGORIES,
            "sentiments": SENTIMENTS,
            "review_states": REVIEW_STATES,
            "category_labels": CATEGORY_LABELS,
            "filters": request.query_params,
            "qs": request.url.query,
        },
    )


@app.post("/evidence/{evidence_id}/review")
def review(evidence_id: int, action: str = Form(...), qs: str = Form(""),
           _: str = Depends(require_auth), db=Depends(get_db)):
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise HTTPException(404, "evidence not found")
    if action in ("approve", "approved"):
        ev.review_status = "approved"
    elif action in ("reject", "rejected"):
        ev.review_status = "rejected"
    else:
        raise HTTPException(400, "invalid action")
    db.commit()
    return RedirectResponse(f"/?{qs}", status_code=303)


# --------------------------------------------------------------------------
# CSV export (/export) — the deliverable for the marketing team
# --------------------------------------------------------------------------
@app.get("/export")
def export_csv(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    f = EvidenceFilter.from_query(request.query_params)
    f.limit = 2000
    items = query_evidence(db, f)
    data = build_csv(items)
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gtm_evidence.csv"},
    )


# --------------------------------------------------------------------------
# Admin: product config (/admin/products)
# --------------------------------------------------------------------------
@app.get("/admin/products", response_class=HTMLResponse)
def admin_products(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    products = list_products(db)
    return templates.TemplateResponse(
        "admin_products.html", {"request": request, "products": products}
    )


def _split_lines(text: str) -> list[str]:
    """Accept newline- or comma-separated lists from the textarea."""
    if not text:
        return []
    parts = []
    for chunk in text.replace(",", "\n").splitlines():
        c = chunk.strip().lstrip("@")
        if c:
            parts.append(c)
    return parts


@app.post("/admin/products")
def admin_save(
    name: str = Form(...),
    keywords: str = Form(""),
    official_accounts: str = Form(""),
    seed_kols: str = Form(""),
    launch_date: str = Form(""),
    active: str = Form("on"),
    _: str = Depends(require_auth),
    db=Depends(get_db),
):
    upsert_product(db, {
        "name": name,
        "keywords": _split_lines(keywords),
        "official_accounts": _split_lines(official_accounts),
        "seed_kols": _split_lines(seed_kols),
        "launch_date": launch_date or None,
        "active": active in ("on", "true", "1", "yes"),
    })
    return RedirectResponse("/admin/products", status_code=303)


@app.post("/admin/products/{product_id}/delete")
def admin_delete(product_id: int, _: str = Depends(require_auth), db=Depends(get_db)):
    delete_product(db, product_id)
    return RedirectResponse("/admin/products", status_code=303)


# --------------------------------------------------------------------------
# Reserved webhook (/webhook/tweets) — shares the pipeline with polling.
# --------------------------------------------------------------------------
@app.post("/webhook/tweets")
async def webhook_tweets(request: Request, db=Depends(get_db)):
    # Shared-secret check (constant-time). twitterapi.io filter-rule webhooks
    # deliver a batch of tweets; we normalize + funnel each through the pipeline.
    provided = request.headers.get("X-Webhook-Secret", "")
    if not settings.webhook_secret or not hmac.compare_digest(provided, settings.webhook_secret):
        raise HTTPException(401, "bad webhook secret")

    payload = await request.json()
    raw_tweets = payload.get("tweets") or payload.get("data") or []
    # A webhook payload should indicate which product it maps to. We accept an
    # explicit product_id/product_name, else fall back to the first active one.
    products = list_products(db, only_active=True)
    by_name = {p.name.lower(): p for p in products}
    target = None
    if payload.get("product_id"):
        target = get_product(db, int(payload["product_id"]))
    elif payload.get("product_name"):
        target = by_name.get(str(payload["product_name"]).lower())
    if target is None:
        target = products[0] if products else None
    if target is None:
        raise HTTPException(400, "no active product to attribute webhook tweets to")

    classifier = Classifier()
    processed = 0
    for raw in raw_tweets:
        try:
            if process_tweet(db, target, _map_tweet(raw), classifier) is not None:
                processed += 1
        except Exception:
            log.exception("Webhook tweet processing failed (continuing)")
    return {"received": len(raw_tweets), "processed": processed, "product": target.name}
